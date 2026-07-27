"""Label-blind NIfTI preparation for the frozen LLD-MMRI v23 cohort."""
from __future__ import annotations

import json
import math
import os
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path
from pathlib import PurePosixPath
from typing import Any, Callable

import numpy as np
import SimpleITK as sitk

from dtwin.benchmark.lld_mmri_v23_download import (
    PHASE_SUFFIXES,
    _load_and_validate_protocol,
    validate_lld_mmri_v23_download,
)
from dtwin.benchmark.openswisshcc_alignment import _sha256
from dtwin.benchmark.openswisshcc_v20_fusion import _canonical_sha
from dtwin.core import PipelineError
from dtwin.medgemma_screening import _write_json_atomic


INPUT_SCHEMA = "argos-public-liver-mri-input-v1"
PREPARATION_SCHEMA = "argos-lld-mmri-v23-blind-preparation-v1"
MASK_ROLE = "liver_mask_venous"
MINIMUM_LIVER_VOXELS = 300
DYNAMIC_LIVER_SUPPORT_THRESHOLD = 0.99
FORBIDDEN_SOURCE_TERMS = ("label", "mask", "bbox", "annotation", "ground_truth", "lesion")
LiverSegmenter = Callable[[Path, Path], dict[str, Any] | None]


def _checkpoint_payload(values: list[dict[str, Any]]) -> str:
    return "".join(
        json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n"
        for value in values
    )


def _valid_jsonl_checkpoint(path: Path) -> bool:
    if not path.is_file():
        return False
    try:
        values = [
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    except (OSError, UnicodeError, json.JSONDecodeError):
        return False
    return all(isinstance(value, dict) for value in values)


def _replace_checkpoint_file(
    source: Path,
    target: Path,
    *,
    attempts: int = 10,
    initial_delay_seconds: float = 0.05,
) -> None:
    """Replace a checkpoint file despite brief Windows reader/AV locks."""

    for attempt in range(attempts):
        try:
            source.replace(target)
            return
        except PermissionError:
            if attempt == attempts - 1:
                raise
            time.sleep(min(initial_delay_seconds * (2**attempt), 0.5))


def _write_jsonl_checkpoint_atomic(
    path: Path, values: list[dict[str, Any]]
) -> None:
    """Persist one preparation generation with fsync and a valid backup."""

    payload = _checkpoint_payload(values)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex[:8]}.tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    if not _valid_jsonl_checkpoint(temporary) or temporary.stat().st_size != len(
        payload.encode("utf-8")
    ):
        temporary.unlink(missing_ok=True)
        raise PipelineError("Nova geracao do checkpoint de preparacao e invalida.")
    backup = path.with_name(f"{path.stem}.backup{path.suffix}")
    if _valid_jsonl_checkpoint(path):
        backup_temporary = backup.with_name(
            f".{backup.name}.{uuid.uuid4().hex[:8]}.tmp"
        )
        shutil.copyfile(path, backup_temporary)
        with backup_temporary.open("r+b") as handle:
            os.fsync(handle.fileno())
        if not _valid_jsonl_checkpoint(backup_temporary):
            backup_temporary.unlink(missing_ok=True)
            temporary.unlink(missing_ok=True)
            raise PipelineError("Backup do checkpoint de preparacao e invalido.")
        _replace_checkpoint_file(backup_temporary, backup)
    _replace_checkpoint_file(temporary, path)


def _load_jsonl_checkpoint(path: Path) -> list[dict[str, Any]]:
    if not _valid_jsonl_checkpoint(path):
        backup = path.with_name(f"{path.stem}.backup{path.suffix}")
        if not _valid_jsonl_checkpoint(backup):
            raise PipelineError("Checkpoint de preparacao ausente ou invalido.")
        recovery = path.with_name(f".{path.name}.{uuid.uuid4().hex[:8]}.recovery")
        shutil.copyfile(backup, recovery)
        with recovery.open("r+b") as handle:
            os.fsync(handle.fileno())
        if not _valid_jsonl_checkpoint(recovery):
            recovery.unlink(missing_ok=True)
            raise PipelineError("Backup da preparacao nao pode ser recuperado.")
        _replace_checkpoint_file(recovery, path)
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def isolated_total_mr_liver_segmenter(
    source_image: Path,
    output_mask: Path,
    *,
    device: str = "gpu",
    fast: bool = False,
    timeout_seconds: int = 75,
    python_executable: str | None = None,
    worker_path: Path | None = None,
) -> dict[str, Any]:
    """Run one NIfTI segmentation in a killable process with a hard timeout."""

    if isinstance(timeout_seconds, bool) or int(timeout_seconds) < 1:
        raise PipelineError("Timeout isolado LLD-MMRI invalido.")
    source_image = Path(source_image).resolve()
    output_mask = Path(output_mask).resolve()
    output_mask.parent.mkdir(parents=True, exist_ok=True)
    repo_root = Path(__file__).resolve().parents[2]
    worker = (
        Path(worker_path).resolve()
        if worker_path is not None
        else repo_root / "tools" / "lld_mmri_v23_segment_worker.py"
    )
    if not worker.is_file():
        raise PipelineError("Worker isolado LLD-MMRI ausente.")
    receipt_path = output_mask.parent / f".{output_mask.name}.{uuid.uuid4().hex[:8]}.receipt.json"
    command = [
        python_executable or sys.executable,
        str(worker),
        "--source", str(source_image),
        "--output", str(output_mask),
        "--receipt", str(receipt_path),
        "--device", str(device),
    ]
    if fast:
        command.append("--fast")
    creationflags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
    process = subprocess.Popen(
        command,
        cwd=repo_root,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        creationflags=creationflags,
    )
    try:
        stdout, stderr = process.communicate(timeout=int(timeout_seconds))
    except subprocess.TimeoutExpired as exc:
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                capture_output=True,
                text=True,
                check=False,
            )
        else:  # pragma: no cover - Windows is the qualification host
            process.kill()
        process.communicate()
        output_mask.unlink(missing_ok=True)
        receipt_path.unlink(missing_ok=True)
        raise PipelineError(
            f"Segmentacao LLD-MMRI excedeu timeout tecnico de {int(timeout_seconds)} s."
        ) from exc
    try:
        if process.returncode != 0:
            detail = (stderr or stdout or "worker sem detalhe").strip()[-1000:]
            raise PipelineError(f"Worker isolado LLD-MMRI falhou: {detail}")
        try:
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise PipelineError("Receipt do worker isolado LLD-MMRI invalido.") from exc
        if not isinstance(receipt, dict) or not output_mask.is_file():
            raise PipelineError("Worker isolado LLD-MMRI nao produziu mascara e receipt.")
        return {
            **receipt,
            "execution_isolation": "subprocess_tree_timeout_v1",
            "timeout_seconds": int(timeout_seconds),
        }
    finally:
        receipt_path.unlink(missing_ok=True)


def _geometry(image: sitk.Image) -> dict[str, Any]:
    return {
        "size_xyz": list(image.GetSize()),
        "spacing_xyz": [float(value) for value in image.GetSpacing()],
        "origin_xyz": [float(value) for value in image.GetOrigin()],
        "direction": [float(value) for value in image.GetDirection()],
    }


def _same_geometry(left: sitk.Image, right: sitk.Image) -> bool:
    return (
        left.GetDimension() == right.GetDimension() == 3
        and left.GetSize() == right.GetSize()
        and np.allclose(left.GetSpacing(), right.GetSpacing(), rtol=0, atol=1e-5)
        and np.allclose(left.GetOrigin(), right.GetOrigin(), rtol=0, atol=1e-4)
        and np.allclose(left.GetDirection(), right.GetDirection(), rtol=0, atol=1e-6)
    )


def _read_valid_nifti(path: Path, *, role: str) -> sitk.Image:
    try:
        image = sitk.ReadImage(str(path))
    except RuntimeError as exc:
        raise PipelineError(f"NIfTI LLD-MMRI invalido para {role}.") from exc
    spacing = tuple(float(value) for value in image.GetSpacing())
    if (
        image.GetDimension() != 3
        or len(spacing) != 3
        or any(not math.isfinite(value) or value <= 0 for value in spacing)
        or any(int(value) < 2 for value in image.GetSize())
    ):
        raise PipelineError(f"Geometria NIfTI LLD-MMRI invalida para {role}.")
    return image


def _link_or_copy(source: Path, destination: Path) -> str:
    try:
        os.link(source, destination)
        return "hardlink"
    except OSError:
        shutil.copyfile(source, destination)
        return "copy"


def total_mr_liver_segmenter(
    source_venous: Path,
    output_mask: Path,
    *,
    device: str = "gpu",
    fast: bool = False,
) -> dict[str, Any]:
    """Run only the automatic TotalSegmentator MRI liver class."""

    try:
        from totalsegmentator.python_api import totalsegmentator
    except ImportError as exc:  # pragma: no cover - environment dependent
        raise PipelineError("TotalSegmentator ausente para preparar LLD-MMRI.") from exc
    configured_weights = os.environ.get("TOTALSEG_WEIGHTS_PATH")
    weights_dir = (
        Path(configured_weights).expanduser().resolve()
        if configured_weights
        else (Path.home() / ".totalsegmentator" / "nnunet" / "results").resolve()
    )
    if not weights_dir.is_dir():
        raise PipelineError("Pesos locais do TotalSegmentator nao encontrados.")
    started = time.perf_counter()
    with (
        tempfile.TemporaryDirectory(prefix="argos-lld-v23-totalseg-home-") as home_folder,
        tempfile.TemporaryDirectory(prefix="argos-lld-v23-totalseg-output-") as output_folder,
    ):
        runtime_home = Path(home_folder)
        output_dir = Path(output_folder)
        _write_json_atomic(
            runtime_home / "config.json",
            {
                "totalseg_id": "argos_lld_mmri_v23_ephemeral",
                "send_usage_stats": False,
                "prediction_counter": 0,
                "statistics_disclaimer_shown": True,
            },
        )
        previous_home = os.environ.get("TOTALSEG_HOME_DIR")
        previous_weights = os.environ.get("TOTALSEG_WEIGHTS_PATH")
        os.environ["TOTALSEG_HOME_DIR"] = str(runtime_home)
        os.environ["TOTALSEG_WEIGHTS_PATH"] = str(weights_dir)
        try:
            try:
                totalsegmentator(
                    input=str(Path(source_venous).resolve()),
                    output=str(output_dir),
                    task="total_mr",
                    roi_subset=["liver"],
                    device=device,
                    fast=bool(fast),
                    quiet=True,
                )
            except Exception as exc:  # noqa: BLE001
                raise PipelineError(f"Falha TotalSegmentator total_mr/liver: {exc}") from exc
        finally:
            if previous_home is None:
                os.environ.pop("TOTALSEG_HOME_DIR", None)
            else:
                os.environ["TOTALSEG_HOME_DIR"] = previous_home
            if previous_weights is None:
                os.environ.pop("TOTALSEG_WEIGHTS_PATH", None)
            else:
                os.environ["TOTALSEG_WEIGHTS_PATH"] = previous_weights
        produced = output_dir / "liver.nii.gz"
        if not produced.is_file():
            raise PipelineError("TotalSegmentator nao produziu liver.nii.gz.")
        output_mask.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(produced, output_mask)
    return {
        "engine": "TotalSegmentator",
        "task": "total_mr",
        "roi_subset": ["liver"],
        "device": device,
        "fast": bool(fast),
        "runtime_config": "ephemeral_isolated_v1",
        "usage_stats_enabled": False,
        "elapsed_seconds": time.perf_counter() - started,
    }


def liver_segments_mr_union_segmenter(
    source_image: Path,
    output_mask: Path,
    *,
    device: str = "gpu",
) -> dict[str, Any]:
    """Run the dedicated MRI Couinaud model and union its eight liver segments."""

    try:
        from totalsegmentator.python_api import totalsegmentator
    except ImportError as exc:  # pragma: no cover - environment dependent
        raise PipelineError("TotalSegmentator ausente para preparar LLD-MMRI.") from exc
    configured_weights = os.environ.get("TOTALSEG_WEIGHTS_PATH")
    weights_dir = (
        Path(configured_weights).expanduser().resolve()
        if configured_weights
        else (Path.home() / ".totalsegmentator" / "nnunet" / "results").resolve()
    )
    if not weights_dir.is_dir():
        raise PipelineError("Pesos locais do TotalSegmentator nao encontrados.")
    started = time.perf_counter()
    segment_names = [f"liver_segment_{index}" for index in range(1, 9)]
    with (
        tempfile.TemporaryDirectory(prefix="argos-lld-v23-totalseg-home-") as home_folder,
        tempfile.TemporaryDirectory(prefix="argos-lld-v23-liver-segments-") as output_folder,
    ):
        runtime_home = Path(home_folder)
        output_dir = Path(output_folder)
        _write_json_atomic(
            runtime_home / "config.json",
            {
                "totalseg_id": "argos_lld_mmri_v23_ephemeral",
                "send_usage_stats": False,
                "prediction_counter": 0,
                "statistics_disclaimer_shown": True,
            },
        )
        previous_home = os.environ.get("TOTALSEG_HOME_DIR")
        previous_weights = os.environ.get("TOTALSEG_WEIGHTS_PATH")
        os.environ["TOTALSEG_HOME_DIR"] = str(runtime_home)
        os.environ["TOTALSEG_WEIGHTS_PATH"] = str(weights_dir)
        try:
            try:
                totalsegmentator(
                    input=str(Path(source_image).resolve()),
                    output=str(output_dir),
                    task="liver_segments_mr",
                    device=device,
                    quiet=True,
                )
            except Exception as exc:  # noqa: BLE001
                raise PipelineError(
                    f"Falha TotalSegmentator liver_segments_mr: {exc}"
                ) from exc
        finally:
            if previous_home is None:
                os.environ.pop("TOTALSEG_HOME_DIR", None)
            else:
                os.environ["TOTALSEG_HOME_DIR"] = previous_home
            if previous_weights is None:
                os.environ.pop("TOTALSEG_WEIGHTS_PATH", None)
            else:
                os.environ["TOTALSEG_WEIGHTS_PATH"] = previous_weights
        produced = [output_dir / f"{name}.nii.gz" for name in segment_names]
        if any(not path.is_file() for path in produced):
            raise PipelineError("TotalSegmentator nao produziu os oito segmentos hepaticos.")
        images = [_read_valid_nifti(path, role=path.stem) for path in produced]
        reference = images[0]
        if any(not _same_geometry(reference, image) for image in images[1:]):
            raise PipelineError("Segmentos hepaticos TotalSegmentator divergiram em geometria.")
        union = np.zeros(tuple(reversed(reference.GetSize())), dtype=np.uint8)
        for image in images:
            union |= (np.asarray(sitk.GetArrayFromImage(image)) > 0).astype(np.uint8)
        union_image = sitk.GetImageFromArray(union)
        union_image.CopyInformation(reference)
        output_mask.parent.mkdir(parents=True, exist_ok=True)
        sitk.WriteImage(union_image, str(output_mask), useCompression=True)
    return {
        "engine": "TotalSegmentator",
        "task": "liver_segments_mr",
        "union_classes": segment_names,
        "device": device,
        "runtime_config": "ephemeral_isolated_v1",
        "usage_stats_enabled": False,
        "elapsed_seconds": time.perf_counter() - started,
    }


def prepare_lld_mmri_v23_blind_inputs(
    *,
    protocol_root: Path,
    download_root: Path,
    geometry_audit_root: Path | None,
    output_root: Path,
    segment_liver: LiverSegmenter,
    failed_audit_root: Path | None = None,
    harmonization_root: Path | None = None,
    segmentation_audit_root: Path | None = None,
    expected_segmentation_audit_signature: str | None = None,
    technical_amendment_root: Path | None = None,
    expected_technical_amendment_signature: str | None = None,
    config_path: Path | None = None,
    profile_path: Path | None = None,
) -> dict[str, Any]:
    """Materialize anonymous eight-phase inputs plus an automatic liver mask."""

    protocol_root = Path(protocol_root).resolve()
    download_root = Path(download_root).resolve()
    output_root = Path(output_root).resolve()
    if output_root.exists():
        raise PipelineError("Preparacao LLD-MMRI v23 existente; sobrescrita recusada.")
    # Local imports avoid module cycles: both gates reuse geometry helpers above.
    from dtwin.benchmark.lld_mmri_v23_geometry_audit import (
        verify_lld_mmri_v23_geometry_audit,
    )
    from dtwin.benchmark.lld_mmri_v23_harmonization import (
        DYNAMIC_ROLES,
        LIVER_SUPPORT_THRESHOLD,
        dynamic_liver_support_fractions,
        verify_lld_mmri_v23_harmonization,
    )
    download = validate_lld_mmri_v23_download(
        protocol_root=protocol_root,
        destination=download_root,
    )
    harmonized_by_id: dict[str, dict[str, Any]] = {}
    if harmonization_root is not None or failed_audit_root is not None:
        if harmonization_root is None or failed_audit_root is None or geometry_audit_root is not None:
            raise PipelineError("Preparacao LLD-MMRI exige harmonizacao+auditoria falha ou auditoria aprovada.")
        source_gate = verify_lld_mmri_v23_harmonization(
            protocol_root=protocol_root,
            download_root=download_root,
            failed_audit_root=failed_audit_root,
            harmonization_root=harmonization_root,
        )
        harmonized_rows = [
            json.loads(line)
            for line in (Path(harmonization_root).resolve() / "cases.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        harmonized_by_id = {str(row["case_id"]): row for row in harmonized_rows}
        source_gate_type = "verified_dynamic_t1_harmonization"
        source_gate_signature = source_gate["harmonization_signature"]
    else:
        if geometry_audit_root is None:
            raise PipelineError("Preparacao LLD-MMRI exige gate geometrico aprovado.")
        source_gate = verify_lld_mmri_v23_geometry_audit(
            protocol_root=protocol_root,
            download_root=download_root,
            audit_root=geometry_audit_root,
        )
        source_gate_type = "passed_original_geometry_audit"
        source_gate_signature = source_gate["audit_signature"]
    segmentation_audit: dict[str, Any] | None = None
    segmentation_audit_rows: dict[str, dict[str, Any]] = {}
    if segmentation_audit_root is not None:
        from dtwin.benchmark.lld_mmri_v23_segmentation_pilot import (
            verify_lld_mmri_v23_segmentation_pilot,
        )

        segmentation_audit_root = Path(segmentation_audit_root).resolve()
        segmentation_audit = verify_lld_mmri_v23_segmentation_pilot(
            protocol_root=protocol_root,
            download_root=download_root,
            pilot_root=segmentation_audit_root,
            geometry_audit_root=geometry_audit_root,
            failed_audit_root=failed_audit_root,
            harmonization_root=harmonization_root,
            expected_pilot_signature=expected_segmentation_audit_signature,
        )
        if (
            segmentation_audit.get("case_count") != len(download["cases"])
            or segmentation_audit.get("case_ids")
            != [str(case["case_id"]) for case in download["cases"]]
            or segmentation_audit.get("selection")
            != "first_n_frozen_protocol_order_no_labels"
        ):
            raise PipelineError(
                "Somente auditoria completa dos 335 casos pode fornecer mascaras preparadas."
            )
        try:
            audit_rows = [
                json.loads(line)
                for line in (segmentation_audit_root / "cases.jsonl")
                .read_text(encoding="utf-8")
                .splitlines()
                if line.strip()
            ]
        except (OSError, json.JSONDecodeError) as exc:
            raise PipelineError("Registros da auditoria de segmentacao ausentes.") from exc
        segmentation_audit_rows = {str(row["case_id"]): row for row in audit_rows}
    technical_amendment: dict[str, Any] | None = None
    technical_failure_case_ids: list[str] = []
    if technical_amendment_root is not None:
        if (
            segmentation_audit_root is None
            or harmonization_root is None
            or failed_audit_root is None
            or config_path is None
            or profile_path is None
        ):
            raise PipelineError(
                "Adendo tecnico LLD-MMRI exige auditoria integral, harmonizacao, config e profile."
            )
        from dtwin.benchmark.lld_mmri_v23_technical_amendment import (
            verify_lld_mmri_v23_technical_amendment,
        )

        technical_amendment_root = Path(technical_amendment_root).resolve()
        technical_amendment = verify_lld_mmri_v23_technical_amendment(
            protocol_root=protocol_root,
            download_root=download_root,
            failed_audit_root=failed_audit_root,
            harmonization_root=harmonization_root,
            segmentation_audit_root=segmentation_audit_root,
            config_path=config_path,
            profile_path=profile_path,
            amendment_root=technical_amendment_root,
            expected_amendment_signature=expected_technical_amendment_signature,
        )
        failure_contract = technical_amendment.get("technical_failures", {})
        technical_failure_case_ids = list(failure_contract.get("case_ids", []))
        if (
            failure_contract.get("case_count") != len(technical_failure_case_ids)
            or failure_contract.get("excluded_from_inference") is not True
            or failure_contract.get("count_as_primary_metric_errors") is not True
            or failure_contract.get("mask_fabrication_allowed") is not False
            or len(set(technical_failure_case_ids)) != len(technical_failure_case_ids)
        ):
            raise PipelineError("Contrato de falhas tecnicas LLD-MMRI invalido.")
    technical_failure_case_id_set = set(technical_failure_case_ids)
    audited_failure_case_ids = {
        case_id
        for case_id, audit_row in segmentation_audit_rows.items()
        if audit_row.get("segmentation_status")
        == "technical_failure_no_valid_liver_mask"
    }
    if technical_failure_case_id_set != audited_failure_case_ids:
        raise PipelineError("Falhas tecnicas preparadas divergiram da auditoria integral.")
    eligible_cases = [
        case
        for case in download["cases"]
        if str(case["case_id"]) not in technical_failure_case_id_set
    ]
    eligible_case_ids = [str(case["case_id"]) for case in eligible_cases]
    output_root.parent.mkdir(parents=True, exist_ok=True)
    staging = output_root.with_name(f".{output_root.name}.incomplete")
    checkpoint_context = {
        "schema": "argos-lld-mmri-v23-preparation-checkpoint-v1",
        "protocol_signature": download["protocol_signature"],
        "source_gate_type": source_gate_type,
        "source_gate_signature": source_gate_signature,
        "segmentation_audit_signature": (
            segmentation_audit["pilot_signature"] if segmentation_audit else None
        ),
        "technical_amendment_signature": (
            technical_amendment["amendment_signature"] if technical_amendment else None
        ),
        "eligible_case_ids": eligible_case_ids,
        "technical_failure_case_ids": technical_failure_case_ids,
        "ground_truth_read": False,
        "lesion_masks_read": 0,
    }
    checkpoint_context["checkpoint_signature"] = _canonical_sha(checkpoint_context)
    checkpoint_cases_path = staging / "checkpoint_cases.jsonl"
    if staging.exists():
        try:
            persisted_context = json.loads(
                (staging / "checkpoint_context.json").read_text(encoding="utf-8")
            )
            checkpoint_cases = _load_jsonl_checkpoint(checkpoint_cases_path)
            if any(
                set(item) != {"row", "receipt"}
                or not isinstance(item["row"], dict)
                or not isinstance(item["receipt"], dict)
                for item in checkpoint_cases
            ):
                raise PipelineError("Checkpoint de casos preparados e invalido.")
            rows = [item["row"] for item in checkpoint_cases]
            case_receipts = [item["receipt"] for item in checkpoint_cases]
        except (OSError, json.JSONDecodeError) as exc:
            raise PipelineError("Checkpoint da preparacao LLD-MMRI invalido.") from exc
        if persisted_context != checkpoint_context:
            raise PipelineError("Checkpoint da preparacao pertence a outro protocolo.")
        if (
            len(rows) != len(case_receipts)
            or [row.get("case_id") for row in rows]
            != eligible_case_ids[: len(rows)]
            or [receipt.get("case_id") for receipt in case_receipts]
            != eligible_case_ids[: len(case_receipts)]
        ):
            raise PipelineError("Ordem do checkpoint da preparacao foi adulterada.")
        for row, receipt in zip(rows, case_receipts, strict=True):
            row_unsigned = dict(row)
            row_signature = row_unsigned.pop("case_signature", None)
            case_id = str(row.get("case_id", ""))
            files = row.get("files")
            case_dir = (staging / "inputs" / case_id).resolve()
            if (
                row_signature != _canonical_sha(row_unsigned)
                or receipt.get("case_signature") != row_signature
                or not case_dir.is_relative_to(staging)
                or not case_dir.is_dir()
                or not isinstance(files, list)
            ):
                raise PipelineError("Checkpoint preparado LLD-MMRI foi adulterado.")
            expected_names = {Path(str(item.get("relative_path", ""))).name for item in files}
            if set(path.name for path in case_dir.iterdir()) != expected_names:
                raise PipelineError("Arquivos do checkpoint preparado foram alterados.")
            for item in files:
                path = case_dir / Path(str(item["relative_path"])).name
                if (
                    not path.is_file()
                    or path.stat().st_size != item.get("bytes")
                    or _sha256(path) != item.get("sha256")
                ):
                    raise PipelineError("Hash do checkpoint preparado divergiu.")
    else:
        staging.mkdir()
        (staging / "inputs").mkdir()
        _write_json_atomic(staging / "checkpoint_context.json", checkpoint_context)
        rows = []
        case_receipts = []
        _write_jsonl_checkpoint_atomic(checkpoint_cases_path, [])
    try:
        inputs_root = staging / "inputs"
        current_case_id: str | None = None
        for case in eligible_cases[len(rows):]:
            case_started = time.perf_counter()
            case_id = str(case["case_id"])
            current_case_id = case_id
            images = case["images"]
            if not case_id.startswith("anon-lld-") or set(images) != set(PHASE_SUFFIXES):
                raise PipelineError("Caso LLD-MMRI inseguro na preparacao cega.")
            audit_row = segmentation_audit_rows.get(case_id)
            audit_is_failure = (
                audit_row is not None
                and audit_row.get("segmentation_status")
                == "technical_failure_no_valid_liver_mask"
            )
            if audit_is_failure or case_id in technical_failure_case_id_set:
                raise PipelineError(
                    "Caso inelegivel alcancou a materializacao LLD-MMRI."
                )
            source_paths: dict[str, Path] = {}
            source_images: dict[str, sitk.Image] = {}
            harmonized = harmonized_by_id.get(case_id)
            harmonized_items = (
                {str(item["role"]): item for item in harmonized["files"]}
                if harmonized is not None else {}
            )
            for role, original_item in images.items():
                item = harmonized_items.get(role, original_item)
                relative = str(item["relative_path"])
                if any(term in relative.lower() for term in FORBIDDEN_SOURCE_TERMS):
                    raise PipelineError("Ground truth detectado na preparacao LLD-MMRI.")
                source_root = Path(harmonization_root).resolve() if role in harmonized_items else download_root
                source = (source_root / relative).resolve()
                if not source.is_relative_to(source_root) or _sha256(source) != item["sha256"]:
                    raise PipelineError("Fonte LLD-MMRI mudou durante a preparacao.")
                source_paths[role] = source
                source_images[role] = _read_valid_nifti(source, role=role)

            reference = source_images["t1_venous"]
            for role in ("t1_native", "t1_arterial", "t1_delayed"):
                if not _same_geometry(reference, source_images[role]):
                    raise PipelineError(
                        "Fases T1 dinamicas LLD-MMRI nao estao na mesma geometria; "
                        "registro explicito e necessario antes do v23."
                    )

            case_dir = inputs_root / case_id
            if case_dir.exists():
                if not case_dir.resolve().is_relative_to(inputs_root.resolve()):
                    raise PipelineError("Diretorio parcial inseguro na preparacao.")
                shutil.rmtree(case_dir)
            case_dir.mkdir()
            files: list[dict[str, Any]] = []
            materialization: set[str] = set()
            for role in PHASE_SUFFIXES:
                destination = case_dir / f"{role}.nii.gz"
                materialization.add(_link_or_copy(source_paths[role], destination))
                files.append(
                    {
                        "role": role,
                        "relative_path": f"{case_id}/{destination.name}",
                        "bytes": destination.stat().st_size,
                        "sha256": _sha256(destination),
                        "source_geometry": _geometry(source_images[role]),
                    }
                )

            mask_path = case_dir / f"{MASK_ROLE}.nii.gz"
            if segmentation_audit is not None:
                source_mask = (
                    Path(segmentation_audit_root) / case_id / "liver_mask_venous.nii.gz"
                ).resolve()
                if (
                    audit_row is None
                    or not source_mask.is_relative_to(Path(segmentation_audit_root))
                    or not source_mask.is_file()
                    or audit_row.get("mask_sha256") != _sha256(source_mask)
                ):
                    raise PipelineError("Mascara da auditoria LLD-MMRI mudou antes da preparacao.")
                materialization.add(_link_or_copy(source_mask, mask_path))
                segment_receipt = {
                    "engine": "verified_full_cohort_segmentation_audit",
                    "source_pilot_signature": segmentation_audit["pilot_signature"],
                    "source_mask_sha256": audit_row["mask_sha256"],
                    "elapsed_seconds": 0.0,
                    "resegmented": False,
                }
            else:
                segment_receipt = segment_liver(case_dir / "t1_venous.nii.gz", mask_path) or {}
            if not mask_path.is_file():
                raise PipelineError("Segmentador LLD-MMRI nao produziu mascara hepatica.")
            mask_image = _read_valid_nifti(mask_path, role=MASK_ROLE)
            if not _same_geometry(reference, mask_image):
                raise PipelineError("Mascara hepatica automatica divergiu da grade venosa.")
            mask = np.asarray(sitk.GetArrayFromImage(mask_image)) > 0
            liver_voxels = int(mask.sum())
            if liver_voxels < MINIMUM_LIVER_VOXELS:
                raise PipelineError("Mascara hepatica automatica vazia ou pequena demais.")
            support_fractions = (
                dynamic_liver_support_fractions(harmonized, mask_image)
                if harmonized is not None
                else {role: 1.0 for role in DYNAMIC_ROLES}
            )
            minimum_support = min(support_fractions.values())
            if minimum_support < LIVER_SUPPORT_THRESHOLD and technical_amendment is None:
                raise PipelineError(
                    "Fase dinamica LLD-MMRI cobre menos de 99% da mascara hepatica automatica."
                )
            files.append(
                {
                    "role": MASK_ROLE,
                    "relative_path": f"{case_id}/{mask_path.name}",
                    "bytes": mask_path.stat().st_size,
                    "sha256": _sha256(mask_path),
                    "source_geometry": _geometry(mask_image),
                }
            )
            row = {
                "schema": INPUT_SCHEMA,
                "case_id": case_id,
                "files": files,
                "dynamic_t1_same_geometry": True,
                "reference_grid": "t1_venous",
                "automatic_liver_mask": True,
                "automatic_liver_mask_voxels": liver_voxels,
                "dynamic_liver_support_fraction": support_fractions,
                "minimum_dynamic_liver_support_fraction": minimum_support,
                "all_dynamic_liver_support_at_least_99_percent": (
                    minimum_support >= LIVER_SUPPORT_THRESHOLD
                ),
                "lesion_mask_present": False,
                "pathology_label_present": False,
                "ground_truth_read": False,
                "research_only": True,
                "clinical_use_allowed": False,
                "requires_human_review": True,
            }
            row["case_signature"] = _canonical_sha(row)
            rows.append(row)
            case_receipts.append(
                {
                    "case_id": case_id,
                    "case_signature": row["case_signature"],
                    "materialization": sorted(materialization),
                    "segmentation": segment_receipt,
                    "elapsed_seconds": time.perf_counter() - case_started,
                }
            )
            _write_jsonl_checkpoint_atomic(
                checkpoint_cases_path,
                [
                    {"row": row, "receipt": receipt}
                    for row, receipt in zip(rows, case_receipts, strict=True)
                ],
            )

        amendment_sha256: str | None = None
        if technical_amendment is not None:
            amendment_source = technical_amendment_root / "amendment.json"
            amendment_destination = staging / "technical_amendment.json"
            shutil.copyfile(amendment_source, amendment_destination)
            amendment_sha256 = _sha256(amendment_destination)
        manifest_path = staging / "inputs.jsonl"
        manifest_path.write_text(
            "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows),
            encoding="utf-8",
        )
        base = {
            "schema": PREPARATION_SCHEMA,
            "status": "complete_label_blind_inputs_with_automatic_liver_masks",
            "protocol_signature": download["protocol_signature"],
            "download_manifest_signature": download["manifest_signature"],
            "source_gate_type": source_gate_type,
            "source_gate_signature": source_gate_signature,
            "segmentation_source_type": (
                "verified_full_cohort_segmentation_audit"
                if segmentation_audit is not None
                else "on_demand_automatic_liver"
            ),
            "segmentation_audit_signature": (
                segmentation_audit["pilot_signature"] if segmentation_audit is not None else None
            ),
            "technical_amendment_signature": (
                technical_amendment["amendment_signature"]
                if technical_amendment is not None
                else None
            ),
            "technical_amendment_sha256": amendment_sha256,
            "protocol_case_count": len(download["cases"]),
            "case_count": len(rows),
            "technical_failure_case_count": len(technical_failure_case_ids),
            "technical_failure_case_ids": technical_failure_case_ids,
            "technical_failures_excluded_from_inference": True,
            "technical_failures_count_as_primary_metric_errors": True,
            "image_count": len(rows) * len(PHASE_SUFFIXES),
            "automatic_liver_mask_count": len(rows),
            "case_ids": [row["case_id"] for row in rows],
            "inputs_sha256": _sha256(manifest_path),
            "case_receipts": case_receipts,
            "dynamic_t1_geometry_gate": "exact_same_physical_grid_or_abort",
            "dynamic_liver_support_threshold": LIVER_SUPPORT_THRESHOLD,
            "minimum_dynamic_liver_support_fraction": min(
                row["minimum_dynamic_liver_support_fraction"] for row in rows
            ),
            "all_dynamic_liver_support_at_least_99_percent": all(
                row["all_dynamic_liver_support_at_least_99_percent"] for row in rows
            ),
            "labels_read": False,
            "lesion_masks_read": 0,
            "lesion_masks_copied": False,
            "research_only": True,
            "clinical_use_allowed": False,
            "requires_human_review": True,
        }
        summary = dict(base)
        summary["preparation_signature"] = _canonical_sha(base)
        _write_json_atomic(staging / "summary.json", summary)
        (staging / "checkpoint_context.json").unlink(missing_ok=True)
        checkpoint_cases_path.unlink(missing_ok=True)
        (staging / "checkpoint_cases.backup.jsonl").unlink(missing_ok=True)
        (staging / "failure.json").unlink(missing_ok=True)
        staging.replace(output_root)
        return summary
    except Exception as exc:
        _write_json_atomic(
            staging / "failure.json",
            {
                "schema": "argos-lld-mmri-v23-preparation-checkpoint-failure-v1",
                "case_id": current_case_id,
                "completed_case_count": len(rows),
                "error_type": type(exc).__name__,
                "error": str(exc),
                "ground_truth_read": False,
                "lesion_masks_read": 0,
                "resumable_after_root_cause_review": True,
            },
        )
        raise


def verify_lld_mmri_v23_blind_inputs(
    *,
    protocol_root: Path,
    prepared_root: Path,
    expected_preparation_signature: str | None = None,
) -> dict[str, Any]:
    """Verify every prepared NIfTI and safety invariant before panel generation."""

    protocol, _ = _load_and_validate_protocol(protocol_root)
    prepared_root = Path(prepared_root).resolve()
    summary_path = prepared_root / "summary.json"
    manifest_path = prepared_root / "inputs.jsonl"
    inputs_root = prepared_root / "inputs"
    try:
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        rows = [
            json.loads(line)
            for line in manifest_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    except (OSError, json.JSONDecodeError) as exc:
        raise PipelineError("Preparacao LLD-MMRI ausente ou invalida.") from exc
    unsigned = dict(summary) if isinstance(summary, dict) else {}
    signature = unsigned.pop("preparation_signature", None)
    receipts = summary.get("case_receipts") if isinstance(summary, dict) else None
    amendment_signature = summary.get("technical_amendment_signature")
    partial_fov_authorized = amendment_signature is not None
    technical_failure_case_ids: list[str] = []
    amendment_path = prepared_root / "technical_amendment.json"
    if partial_fov_authorized:
        try:
            amendment = json.loads(amendment_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise PipelineError("Adendo tecnico preparado LLD-MMRI ausente.") from exc
        amendment_unsigned = dict(amendment) if isinstance(amendment, dict) else {}
        persisted_amendment_signature = amendment_unsigned.pop("amendment_signature", None)
        if (
            persisted_amendment_signature != amendment_signature
            or persisted_amendment_signature != _canonical_sha(amendment_unsigned)
            or summary.get("technical_amendment_sha256") != _sha256(amendment_path)
            or amendment.get("segmentation_audit_signature")
            != summary.get("segmentation_audit_signature")
            or amendment.get("case_ids") != protocol["case_ids"]
            or amendment.get("ground_truth_read") is not False
            or amendment.get("lesion_masks_read") != 0
            or amendment.get("policy", {}).get("reference_phase") != "t1_venous"
            or amendment.get("policy", {}).get(
                "reference_phase_requires_full_liver_coverage"
            )
            is not True
            or amendment.get("policy", {}).get("panel_partial_fov_policy")
            != "venous_grayscale"
            or amendment.get("policy", {}).get("partial_fov_cases_excluded_from_primary_metrics")
            is not False
        ):
            raise PipelineError("Adendo tecnico preparado LLD-MMRI adulterado.")
        failure_contract = amendment.get("technical_failures", {})
        technical_failure_case_ids = list(failure_contract.get("case_ids", []))
        if (
            failure_contract.get("case_count") != len(technical_failure_case_ids)
            or failure_contract.get("excluded_from_inference") is not True
            or failure_contract.get("count_as_primary_metric_errors") is not True
            or failure_contract.get("mask_fabrication_allowed") is not False
            or len(set(technical_failure_case_ids)) != len(technical_failure_case_ids)
        ):
            raise PipelineError("Falhas tecnicas do adendo preparado sao invalidas.")
    elif summary.get("technical_amendment_sha256") is not None or amendment_path.exists():
        raise PipelineError("Adendo tecnico preparado LLD-MMRI inconsistente.")
    expected_case_ids = [
        case_id
        for case_id in protocol["case_ids"]
        if case_id not in set(technical_failure_case_ids)
    ]
    if (
        summary.get("schema") != PREPARATION_SCHEMA
        or summary.get("status") != "complete_label_blind_inputs_with_automatic_liver_masks"
        or signature != _canonical_sha(unsigned)
        or (expected_preparation_signature is not None and signature != expected_preparation_signature)
        or summary.get("protocol_signature") != protocol["protocol_signature"]
        or summary.get("protocol_case_count") != protocol["case_count"]
        or summary.get("case_count") != len(expected_case_ids)
        or summary.get("technical_failure_case_count") != len(technical_failure_case_ids)
        or summary.get("technical_failure_case_ids") != technical_failure_case_ids
        or summary.get("technical_failures_excluded_from_inference") is not True
        or summary.get("technical_failures_count_as_primary_metric_errors") is not True
        or summary.get("image_count") != len(expected_case_ids) * len(PHASE_SUFFIXES)
        or summary.get("automatic_liver_mask_count") != len(expected_case_ids)
        or summary.get("case_ids") != expected_case_ids
        or summary.get("inputs_sha256") != _sha256(manifest_path)
        or summary.get("source_gate_type") not in {
            "passed_original_geometry_audit", "verified_dynamic_t1_harmonization"
        }
        or not isinstance(summary.get("source_gate_signature"), str)
        or len(summary["source_gate_signature"]) != 64
        or summary.get("segmentation_source_type") not in {
            "on_demand_automatic_liver", "verified_full_cohort_segmentation_audit"
        }
        or (
            summary.get("segmentation_source_type") == "on_demand_automatic_liver"
            and summary.get("segmentation_audit_signature") is not None
        )
        or (
            summary.get("segmentation_source_type")
            == "verified_full_cohort_segmentation_audit"
            and (
                not isinstance(summary.get("segmentation_audit_signature"), str)
                or len(summary["segmentation_audit_signature"]) != 64
            )
        )
        or summary.get("dynamic_liver_support_threshold") != DYNAMIC_LIVER_SUPPORT_THRESHOLD
        or isinstance(summary.get("minimum_dynamic_liver_support_fraction"), bool)
        or not isinstance(summary.get("minimum_dynamic_liver_support_fraction"), (int, float))
        or not (
            (0.0 if partial_fov_authorized else DYNAMIC_LIVER_SUPPORT_THRESHOLD)
            <= float(summary["minimum_dynamic_liver_support_fraction"])
            <= 1.0
        )
        or summary.get("all_dynamic_liver_support_at_least_99_percent")
        is not (
            float(summary["minimum_dynamic_liver_support_fraction"])
            >= DYNAMIC_LIVER_SUPPORT_THRESHOLD
        )
        or summary.get("labels_read") is not False
        or summary.get("lesion_masks_read") != 0
        or summary.get("lesion_masks_copied") is not False
        or summary.get("research_only") is not True
        or summary.get("clinical_use_allowed") is not False
        or not isinstance(receipts, list)
        or len(receipts) != len(expected_case_ids)
        or len(rows) != len(expected_case_ids)
    ):
        raise PipelineError("Resumo preparado LLD-MMRI adulterado ou inseguro.")
    expected_roles = set(PHASE_SUFFIXES) | {MASK_ROLE}
    seen_paths: set[str] = set()
    for index, (row, receipt) in enumerate(zip(rows, receipts, strict=True)):
        case_id = expected_case_ids[index]
        files = row.get("files") if isinstance(row, dict) else None
        support = row.get("dynamic_liver_support_fraction") if isinstance(row, dict) else None
        row_unsigned = dict(row) if isinstance(row, dict) else {}
        row_signature = row_unsigned.pop("case_signature", None)
        if (
            row.get("schema") != INPUT_SCHEMA
            or row.get("case_id") != case_id
            or row_signature != _canonical_sha(row_unsigned)
            or receipt.get("case_id") != case_id
            or receipt.get("case_signature") != row_signature
            or isinstance(receipt.get("elapsed_seconds"), bool)
            or not isinstance(receipt.get("elapsed_seconds"), (int, float))
            or not math.isfinite(float(receipt["elapsed_seconds"]))
            or float(receipt["elapsed_seconds"]) < 0
            or row.get("dynamic_t1_same_geometry") is not True
            or row.get("reference_grid") != "t1_venous"
            or row.get("automatic_liver_mask") is not True
            or not isinstance(support, dict)
            or set(support) != {"t1_native", "t1_arterial", "t1_venous", "t1_delayed"}
            or any(
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(float(value))
                or not (
                    (0.0 if partial_fov_authorized else DYNAMIC_LIVER_SUPPORT_THRESHOLD)
                    <= float(value)
                    <= 1.0
                )
                for value in support.values()
            )
            or (partial_fov_authorized and float(support["t1_venous"]) != 1.0)
            or row.get("minimum_dynamic_liver_support_fraction") != min(support.values())
            or row.get("all_dynamic_liver_support_at_least_99_percent")
            is not (min(support.values()) >= DYNAMIC_LIVER_SUPPORT_THRESHOLD)
            or row.get("lesion_mask_present") is not False
            or row.get("pathology_label_present") is not False
            or row.get("ground_truth_read") is not False
            or row.get("research_only") is not True
            or row.get("clinical_use_allowed") is not False
            or not isinstance(files, list)
            or len(files) != len(expected_roles)
        ):
            raise PipelineError("Registro preparado LLD-MMRI adulterado ou inseguro.")
        by_role = {str(item.get("role", "")): item for item in files}
        if set(by_role) != expected_roles or len(by_role) != len(files):
            raise PipelineError("Papeis preparados LLD-MMRI incompletos ou duplicados.")
        images: dict[str, sitk.Image] = {}
        for role, item in by_role.items():
            relative_text = str(item.get("relative_path", ""))
            relative = PurePosixPath(relative_text)
            forbidden = any(
                term in (role + " " + relative_text).lower()
                for term in ("lesion", "label", "bbox", "annotation", "ground_truth")
            )
            if (
                forbidden
                or relative.is_absolute()
                or ".." in relative.parts
                or len(relative.parts) != 2
                or relative.parts[0] != case_id
                or relative_text in seen_paths
            ):
                raise PipelineError("Caminho preparado LLD-MMRI inseguro ou duplicado.")
            path = (inputs_root / Path(*relative.parts)).resolve()
            if (
                not path.is_relative_to(inputs_root)
                or not path.is_file()
                or path.stat().st_size != item.get("bytes")
                or _sha256(path) != item.get("sha256")
            ):
                raise PipelineError("NIfTI preparado LLD-MMRI ausente ou adulterado.")
            image = _read_valid_nifti(path, role=role)
            if item.get("source_geometry") != _geometry(image):
                raise PipelineError("Geometria persistida LLD-MMRI divergiu do NIfTI.")
            images[role] = image
            seen_paths.add(relative_text)
        reference = images["t1_venous"]
        if any(
            not _same_geometry(reference, images[role])
            for role in ("t1_native", "t1_arterial", "t1_delayed", MASK_ROLE)
        ):
            raise PipelineError("Gate geometrico preparado LLD-MMRI falhou.")
        mask = np.asarray(sitk.GetArrayFromImage(images[MASK_ROLE])) > 0
        liver_voxels = int(mask.sum())
        if (
            liver_voxels < MINIMUM_LIVER_VOXELS
            or row.get("automatic_liver_mask_voxels") != liver_voxels
        ):
            raise PipelineError("Mascara hepatica preparada LLD-MMRI divergiu.")
    if len(seen_paths) != len(expected_case_ids) * len(expected_roles):
        raise PipelineError("Cobertura preparada LLD-MMRI incompleta.")
    return {
        "status": "ready_for_label_blind_panel_generation",
        "protocol_case_count": protocol["case_count"],
        "case_count": len(expected_case_ids),
        "technical_failure_case_count": len(technical_failure_case_ids),
        "technical_failure_case_ids": technical_failure_case_ids,
        "preparation_signature": signature,
        "inputs_sha256": summary["inputs_sha256"],
        "labels_read": False,
        "lesion_masks_read": 0,
        "research_only": True,
        "clinical_use_allowed": False,
        "requires_human_review": True,
    }


__all__ = [
    "INPUT_SCHEMA",
    "MASK_ROLE",
    "PREPARATION_SCHEMA",
    "prepare_lld_mmri_v23_blind_inputs",
    "total_mr_liver_segmenter",
    "verify_lld_mmri_v23_blind_inputs",
]
