"""Label-blind segmentation timing pilot for the frozen LLD-MMRI v23 cohort."""
from __future__ import annotations

import json
import math
import os
import shutil
import time
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np
import SimpleITK as sitk

from dtwin.benchmark.lld_mmri_v23_download import validate_lld_mmri_v23_download
from dtwin.benchmark.lld_mmri_v23_geometry_audit import (
    verify_lld_mmri_v23_geometry_audit,
)
from dtwin.benchmark.lld_mmri_v23_harmonization import (
    DYNAMIC_ROLES,
    LIVER_SUPPORT_THRESHOLD,
    dynamic_liver_support_fractions,
    verify_lld_mmri_v23_harmonization,
)
from dtwin.benchmark.lld_mmri_v23_mask_quality import (
    MASK_QUALITY_POLICY,
    evaluate_liver_mask_quality,
)
from dtwin.benchmark.lld_mmri_v23_preparation import (
    MINIMUM_LIVER_VOXELS,
    _read_valid_nifti,
    _same_geometry,
)
from dtwin.benchmark.openswisshcc_alignment import _publish_directory, _sha256
from dtwin.benchmark.openswisshcc_v20_fusion import _canonical_sha
from dtwin.core import PipelineError
from dtwin.medgemma_screening import _write_json_atomic

PILOT_SCHEMA = "argos-lld-mmri-v23-segmentation-timing-pilot-v1"
Segmenter = Callable[[Path, Path], dict[str, Any] | None]
Progress = Callable[[dict[str, Any]], None]


def _checkpoint_payload(rows: list[dict[str, Any]]) -> str:
    return "".join(
        json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows
    )


def _valid_checkpoint_file(path: Path) -> bool:
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


def _write_checkpoint_rows_atomic(path: Path, rows: list[dict[str, Any]]) -> None:
    """Durably replace a checkpoint while retaining the last valid generation."""

    payload = _checkpoint_payload(rows)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex[:8]}.tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    # Refuse to publish a sparse/NUL or otherwise invalid generation.
    if not _valid_checkpoint_file(temporary) or temporary.stat().st_size != len(
        payload.encode("utf-8")
    ):
        temporary.unlink(missing_ok=True)
        raise PipelineError("Nova geracao do checkpoint LLD-MMRI e invalida.")
    backup = path.with_name("checkpoint_rows.backup.jsonl")
    if _valid_checkpoint_file(path):
        backup_tmp = backup.with_name(f".{backup.name}.{uuid.uuid4().hex[:8]}.tmp")
        shutil.copyfile(path, backup_tmp)
        with backup_tmp.open("r+b") as handle:
            os.fsync(handle.fileno())
        if not _valid_checkpoint_file(backup_tmp):
            backup_tmp.unlink(missing_ok=True)
            temporary.unlink(missing_ok=True)
            raise PipelineError("Backup do checkpoint LLD-MMRI e invalido.")
        backup_tmp.replace(backup)
    temporary.replace(path)


def _mask_gate(mask_path: Path, reference: sitk.Image) -> tuple[bool, int, bool]:
    """Return the exact label-blind geometry/size gate used by the audit."""

    if not mask_path.is_file():
        return False, 0, False
    try:
        mask_image = _read_valid_nifti(mask_path, role="liver_mask_venous")
    except PipelineError:
        return False, 0, False
    voxels = int((np.asarray(sitk.GetArrayFromImage(mask_image)) > 0).sum())
    same_geometry = _same_geometry(reference, mask_image)
    return same_geometry and voxels >= MINIMUM_LIVER_VOXELS, voxels, same_geometry


def run_lld_mmri_v23_segmentation_pilot(
    *,
    protocol_root: Path,
    download_root: Path,
    geometry_audit_root: Path | None,
    output_root: Path,
    segment_liver: Segmenter,
    fallback_segment_liver: Segmenter | None = None,
    case_count: int = 5,
    failed_audit_root: Path | None = None,
    harmonization_root: Path | None = None,
    selection: str = "first_n",
    continue_on_technical_failure: bool = False,
    primary_attempt_name: str = "primary_full_resolution",
    fallback_attempt_name: str = "fallback_fast_3mm",
    mask_quality_policy: str = "legacy_voxel_geometry_v1",
    progress: Progress | None = None,
) -> dict[str, Any]:
    """Measure the first N protocol cases without producing inference inputs."""

    if isinstance(case_count, bool) or not isinstance(case_count, int) or case_count < 1:
        raise PipelineError("Auditoria de segmentacao LLD-MMRI exige ao menos 1 caso.")
    if selection not in {"first_n", "lowest_whole_grid_support"}:
        raise PipelineError("Selecao do piloto LLD-MMRI invalida.")
    if not primary_attempt_name or not fallback_attempt_name or not mask_quality_policy:
        raise PipelineError("Identidade do protocolo de segmentacao LLD-MMRI invalida.")
    download_root = Path(download_root).resolve()
    manifest = validate_lld_mmri_v23_download(
        protocol_root=protocol_root, destination=download_root
    )
    if case_count > len(manifest["cases"]):
        raise PipelineError(
            "Auditoria de segmentacao LLD-MMRI nao pode exceder o coorte congelado."
        )
    harmonized_by_id: dict[str, dict[str, Any]] = {}
    if harmonization_root is not None or failed_audit_root is not None:
        if harmonization_root is None or failed_audit_root is None or geometry_audit_root is not None:
            raise PipelineError("Piloto LLD-MMRI exige harmonizacao+auditoria falha ou auditoria aprovada.")
        source_gate = verify_lld_mmri_v23_harmonization(
            protocol_root=protocol_root,
            download_root=download_root,
            failed_audit_root=failed_audit_root,
            harmonization_root=harmonization_root,
        )
        try:
            harmonized_rows = [
                json.loads(line)
                for line in (Path(harmonization_root).resolve() / "cases.jsonl").read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
        except (OSError, json.JSONDecodeError) as exc:
            raise PipelineError("Casos harmonizados ausentes no piloto LLD-MMRI.") from exc
        harmonized_by_id = {str(row["case_id"]): row for row in harmonized_rows}
        source_gate_type = "verified_dynamic_t1_harmonization"
        source_gate_signature = source_gate["harmonization_signature"]
    else:
        if geometry_audit_root is None:
            raise PipelineError("Piloto LLD-MMRI exige gate geometrico aprovado.")
        source_gate = verify_lld_mmri_v23_geometry_audit(
            protocol_root=protocol_root,
            download_root=download_root,
            audit_root=geometry_audit_root,
        )
        source_gate_type = "passed_original_geometry_audit"
        source_gate_signature = source_gate["audit_signature"]
    if selection == "lowest_whole_grid_support":
        if not harmonized_by_id:
            raise PipelineError("Selecao por cobertura exige harmonizacao verificada.")
        protocol_order = {case["case_id"]: index for index, case in enumerate(manifest["cases"])}
        selected = sorted(
            manifest["cases"],
            key=lambda case: (
                min(
                    float(item["whole_reference_grid_support_fraction"])
                    for item in harmonized_by_id[str(case["case_id"])]["files"]
                ),
                protocol_order[str(case["case_id"])],
            ),
        )[:case_count]
        selection_text = "lowest_whole_grid_support_no_labels"
    else:
        selected = manifest["cases"][:case_count]
        selection_text = "first_n_frozen_protocol_order_no_labels"
    output_root = Path(output_root).resolve()
    if output_root.exists():
        raise PipelineError("Piloto de segmentacao LLD-MMRI existente; sobrescrita recusada.")
    output_root.parent.mkdir(parents=True, exist_ok=True)
    staging = output_root.with_name(f".{output_root.name}.incomplete")
    checkpoint_context = {
        "schema": "argos-lld-mmri-v23-segmentation-checkpoint-v1",
        "protocol_signature": manifest["protocol_signature"],
        "source_gate_type": source_gate_type,
        "source_gate_signature": source_gate_signature,
        "selection": selection_text,
        "case_ids": [str(case["case_id"]) for case in selected],
        "continue_on_technical_failure": bool(continue_on_technical_failure),
        "primary_attempt_name": primary_attempt_name,
        "fallback_attempt_name": fallback_attempt_name,
        "mask_quality_policy": mask_quality_policy,
        "ground_truth_read": False,
        "lesion_masks_read": 0,
    }
    checkpoint_context["checkpoint_signature"] = _canonical_sha(checkpoint_context)
    checkpoint_rows_path = staging / "checkpoint_rows.jsonl"
    if staging.exists():
        try:
            persisted_context = json.loads(
                (staging / "checkpoint_context.json").read_text(encoding="utf-8")
            )
            rows = [
                json.loads(line)
                for line in checkpoint_rows_path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
        except (OSError, json.JSONDecodeError) as exc:
            raise PipelineError("Checkpoint LLD-MMRI incompleto ou invalido.") from exc
        legacy_context = dict(checkpoint_context)
        legacy_context.pop("continue_on_technical_failure")
        legacy_context.pop("checkpoint_signature")
        legacy_context["checkpoint_signature"] = _canonical_sha(legacy_context)
        if persisted_context == legacy_context:
            _write_json_atomic(staging / "checkpoint_context.json", checkpoint_context)
        elif persisted_context != checkpoint_context:
            raise PipelineError("Checkpoint LLD-MMRI pertence a outro protocolo ou selecao.")
        rows_migrated = False
        for row in rows:
            if "segmentation_status" not in row:
                row["segmentation_status"] = "valid_liver_mask"
                rows_migrated = True
        if rows_migrated:
            _write_checkpoint_rows_atomic(checkpoint_rows_path, rows)
        expected_prefix = checkpoint_context["case_ids"][: len(rows)]
        if [row.get("case_id") for row in rows] != expected_prefix:
            raise PipelineError("Ordem do checkpoint LLD-MMRI foi adulterada.")
        for row in rows:
            if row.get("segmentation_status") == "technical_failure_no_valid_liver_mask":
                case_path = staging / str(row["case_id"])
                if (
                    case_path.exists()
                    or row.get("mask_sha256") is not None
                    or row.get("technical_failure_counts_as_error") is not True
                ):
                    raise PipelineError("Falha tecnica do checkpoint LLD-MMRI foi adulterada.")
                continue
            mask = staging / str(row["case_id"]) / "liver_mask_venous.nii.gz"
            if not mask.is_file() or row.get("mask_sha256") != _sha256(mask):
                raise PipelineError("Mascara do checkpoint LLD-MMRI foi adulterada.")
    else:
        staging.mkdir()
        _write_json_atomic(staging / "checkpoint_context.json", checkpoint_context)
        rows: list[dict[str, Any]] = []
        checkpoint_rows_path.write_text("", encoding="utf-8")
    current_case_id: str | None = None
    try:
        for case in selected[len(rows):]:
            case_id = str(case["case_id"])
            current_case_id = case_id
            harmonized = harmonized_by_id.get(case_id)
            if harmonized is not None:
                by_role = {str(item["role"]): item for item in harmonized["files"]}
                venous = (Path(harmonization_root).resolve() / str(by_role["t1_venous"]["relative_path"])).resolve()
            else:
                venous_item = case["images"]["t1_venous"]
                venous = (download_root / str(venous_item["relative_path"])).resolve()
            reference = _read_valid_nifti(venous, role="t1_venous")
            case_dir = staging / case_id
            if case_dir.exists():
                stale = list(case_dir.iterdir())
                if any(
                    not item.is_file() or item.name != "liver_mask_venous.nii.gz"
                    for item in stale
                ):
                    raise PipelineError(
                        "Caso nao checkpointado contem artefato inesperado; retomada recusada."
                    )
                for item in stale:
                    item.unlink()
                case_dir.rmdir()
            case_dir.mkdir()
            mask_path = case_dir / "liver_mask_venous.nii.gz"
            started = time.perf_counter()
            attempts: list[dict[str, Any]] = []
            primary_error: Exception | None = None
            try:
                primary_receipt = segment_liver(venous, mask_path) or {}
            except Exception as exc:
                primary_receipt = {}
                primary_error = exc
            primary_passed, primary_voxels, primary_geometry = _mask_gate(mask_path, reference)
            attempts.append(
                {
                    "attempt": primary_attempt_name,
                    "status": "passed_gate" if primary_passed else "failed_gate",
                    "same_geometry": primary_geometry,
                    "liver_voxels": primary_voxels,
                    "receipt": primary_receipt,
                    "error_type": type(primary_error).__name__ if primary_error else None,
                    "error": str(primary_error) if primary_error else None,
                }
            )
            fallback_used = False
            receipt = primary_receipt
            if not primary_passed and fallback_segment_liver is not None:
                fallback_used = True
                mask_path.unlink(missing_ok=True)
                fallback_error: Exception | None = None
                try:
                    fallback_receipt = fallback_segment_liver(venous, mask_path) or {}
                except Exception as exc:
                    fallback_receipt = {}
                    fallback_error = exc
                fallback_passed, fallback_voxels, fallback_geometry = _mask_gate(
                    mask_path, reference
                )
                attempts.append(
                    {
                        "attempt": fallback_attempt_name,
                        "status": "passed_gate" if fallback_passed else "failed_gate",
                        "same_geometry": fallback_geometry,
                        "liver_voxels": fallback_voxels,
                        "receipt": fallback_receipt,
                        "error_type": type(fallback_error).__name__ if fallback_error else None,
                        "error": str(fallback_error) if fallback_error else None,
                    }
                )
                receipt = fallback_receipt
                primary_passed = fallback_passed
            elapsed = time.perf_counter() - started
            if not primary_passed:
                if fallback_segment_liver is None and primary_error is not None:
                    raise primary_error
                detail = "; ".join(
                    f"{item['attempt']}={item['status']} voxels={item['liver_voxels']}"
                    for item in attempts
                )
                if not continue_on_technical_failure:
                    raise PipelineError(
                        f"Mascara do piloto LLD-MMRI falhou no gate geometrico ({detail})."
                    )
                mask_path.unlink(missing_ok=True)
                case_dir.rmdir()
                rows.append(
                    {
                        "case_id": case_id,
                        "selection": selection_text,
                        "segmentation_status": "technical_failure_no_valid_liver_mask",
                        "segmentation_elapsed_seconds": elapsed,
                        "segmentation_receipt": receipt,
                        "segmentation_attempts": attempts,
                        "segmentation_selected_attempt": None,
                        "segmentation_fallback_used": fallback_used,
                        "liver_voxels": 0,
                        "dynamic_liver_support_fraction": None,
                        "minimum_dynamic_liver_support_fraction": None,
                        "all_dynamic_liver_support_at_least_99_percent": False,
                        "mask_sha256": None,
                        "within_180_seconds_segmentation_only": elapsed <= 180.0,
                        "technical_failure_counts_as_error": True,
                    }
                )
                _write_checkpoint_rows_atomic(checkpoint_rows_path, rows)
                (staging / "failure.json").unlink(missing_ok=True)
                if progress is not None:
                    progress(
                        {
                            "case_id": case_id,
                            "completed": len(rows),
                            "total": len(selected),
                            "segmentation_elapsed_seconds": elapsed,
                            "segmentation_status": "technical_failure_no_valid_liver_mask",
                        }
                    )
                continue
            mask_image = _read_valid_nifti(mask_path, role="liver_mask_venous")
            voxels = int((np.asarray(sitk.GetArrayFromImage(mask_image)) > 0).sum())
            support_fractions: dict[str, float] = {}
            if harmonized is not None:
                support_fractions = dynamic_liver_support_fractions(harmonized, mask_image)
            else:
                support_fractions = {role: 1.0 for role in DYNAMIC_ROLES}
            minimum_support = min(support_fractions.values())
            if (
                not math.isfinite(elapsed)
                or elapsed < 0
                or ("elapsed_seconds" in receipt and not math.isfinite(float(receipt["elapsed_seconds"])))
            ):
                raise PipelineError("Tempo do piloto LLD-MMRI invalido.")
            rows.append(
                {
                    "case_id": case_id,
                    "selection": selection_text,
                    "segmentation_status": "valid_liver_mask",
                    "segmentation_elapsed_seconds": elapsed,
                    "segmentation_receipt": receipt,
                    "segmentation_attempts": attempts,
                    "segmentation_selected_attempt": (
                        fallback_attempt_name if fallback_used else primary_attempt_name
                    ),
                    "segmentation_fallback_used": fallback_used,
                    "liver_voxels": voxels,
                    "dynamic_liver_support_fraction": support_fractions,
                    "minimum_dynamic_liver_support_fraction": minimum_support,
                    "all_dynamic_liver_support_at_least_99_percent": (
                        minimum_support >= LIVER_SUPPORT_THRESHOLD
                    ),
                    "mask_sha256": _sha256(mask_path),
                    "within_180_seconds_segmentation_only": elapsed <= 180.0,
                }
            )
            _write_checkpoint_rows_atomic(checkpoint_rows_path, rows)
            (staging / "failure.json").unlink(missing_ok=True)
            if progress is not None:
                progress(
                    {
                        "case_id": case_id,
                        "completed": len(rows),
                        "total": len(selected),
                        "segmentation_elapsed_seconds": elapsed,
                        "minimum_dynamic_liver_support_fraction": minimum_support,
                    }
                )
        rows_path = staging / "cases.jsonl"
        rows_path.write_text(
            "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows),
            encoding="utf-8",
        )
        maximum = max(float(row["segmentation_elapsed_seconds"]) for row in rows)
        valid_rows = [row for row in rows if row["segmentation_status"] == "valid_liver_mask"]
        base = {
            "schema": PILOT_SCHEMA,
            "status": "complete_segmentation_timing_only",
            "case_count": len(rows),
            "case_ids": [row["case_id"] for row in rows],
            "selection": selection_text,
            "max_segmentation_seconds": maximum,
            "all_segmentation_only_within_180_seconds": maximum <= 180.0,
            "segmentation_fallback_case_count": sum(
                bool(row.get("segmentation_fallback_used", False)) for row in rows
            ),
            "segmentation_technical_failure_case_count": len(rows) - len(valid_rows),
            "technical_failures_count_as_errors": True,
            "primary_attempt_name": primary_attempt_name,
            "fallback_attempt_name": fallback_attempt_name,
            "mask_quality_policy": mask_quality_policy,
            "cases_sha256": _sha256(rows_path),
            "protocol_signature": manifest["protocol_signature"],
            "source_gate_type": source_gate_type,
            "source_gate_signature": source_gate_signature,
            "liver_support_threshold": LIVER_SUPPORT_THRESHOLD,
            "minimum_dynamic_liver_support_fraction": min(
                row["minimum_dynamic_liver_support_fraction"] for row in valid_rows
            ) if valid_rows else None,
            "all_dynamic_liver_support_at_least_99_percent": all(
                row["all_dynamic_liver_support_at_least_99_percent"] for row in rows
            ) and bool(valid_rows),
            "ground_truth_read": False,
            "lesion_masks_read": 0,
            "technical_timing_only": True,
            "eligible_for_inference": False,
            "end_to_end_time_measured": False,
            "qualified": False,
            "research_only": True,
            "clinical_use_allowed": False,
        }
        summary = dict(base)
        summary["pilot_signature"] = _canonical_sha(base)
        _write_json_atomic(staging / "summary.json", summary)
        (staging / "checkpoint_context.json").unlink(missing_ok=True)
        checkpoint_rows_path.unlink(missing_ok=True)
        (staging / "checkpoint_rows.backup.jsonl").unlink(missing_ok=True)
        (staging / "failure.json").unlink(missing_ok=True)
        _publish_directory(staging, output_root)
        return summary
    except Exception as exc:
        _write_json_atomic(
            staging / "failure.json",
            {
                "schema": "argos-lld-mmri-v23-segmentation-checkpoint-failure-v1",
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


def verify_lld_mmri_v23_segmentation_pilot(
    *,
    protocol_root: Path,
    download_root: Path,
    pilot_root: Path,
    geometry_audit_root: Path | None = None,
    failed_audit_root: Path | None = None,
    harmonization_root: Path | None = None,
    expected_pilot_signature: str | None = None,
) -> dict[str, Any]:
    """Recompute every label-blind segmentation-audit invariant."""

    download_root = Path(download_root).resolve()
    pilot_root = Path(pilot_root).resolve()
    manifest = validate_lld_mmri_v23_download(
        protocol_root=protocol_root, destination=download_root
    )
    harmonized_by_id: dict[str, dict[str, Any]] = {}
    if harmonization_root is not None or failed_audit_root is not None:
        if harmonization_root is None or failed_audit_root is None or geometry_audit_root is not None:
            raise PipelineError("Verificador LLD-MMRI exige um unico gate geometrico.")
        source_gate = verify_lld_mmri_v23_harmonization(
            protocol_root=protocol_root,
            download_root=download_root,
            failed_audit_root=failed_audit_root,
            harmonization_root=harmonization_root,
        )
        try:
            harmonized_rows = [
                json.loads(line)
                for line in (Path(harmonization_root).resolve() / "cases.jsonl")
                .read_text(encoding="utf-8")
                .splitlines()
                if line.strip()
            ]
        except (OSError, json.JSONDecodeError) as exc:
            raise PipelineError("Harmonizacao ausente ao verificar auditoria LLD-MMRI.") from exc
        harmonized_by_id = {str(row["case_id"]): row for row in harmonized_rows}
        source_gate_type = "verified_dynamic_t1_harmonization"
        source_gate_signature = source_gate["harmonization_signature"]
    else:
        if geometry_audit_root is None:
            raise PipelineError("Verificador LLD-MMRI exige gate geometrico.")
        source_gate = verify_lld_mmri_v23_geometry_audit(
            protocol_root=protocol_root,
            download_root=download_root,
            audit_root=geometry_audit_root,
        )
        source_gate_type = "passed_original_geometry_audit"
        source_gate_signature = source_gate["audit_signature"]
    try:
        summary = json.loads((pilot_root / "summary.json").read_text(encoding="utf-8"))
        rows = [
            json.loads(line)
            for line in (pilot_root / "cases.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    except (OSError, json.JSONDecodeError) as exc:
        raise PipelineError("Auditoria de segmentacao LLD-MMRI ausente ou invalida.") from exc
    unsigned = dict(summary) if isinstance(summary, dict) else {}
    signature = unsigned.pop("pilot_signature", None)
    if (
        summary.get("schema") != PILOT_SCHEMA
        or summary.get("status") != "complete_segmentation_timing_only"
        or signature != _canonical_sha(unsigned)
        or (expected_pilot_signature is not None and signature != expected_pilot_signature)
        or summary.get("protocol_signature") != manifest["protocol_signature"]
        or summary.get("source_gate_type") != source_gate_type
        or summary.get("source_gate_signature") != source_gate_signature
        or summary.get("case_count") != len(rows)
        or not 1 <= len(rows) <= len(manifest["cases"])
        or summary.get("cases_sha256") != _sha256(pilot_root / "cases.jsonl")
        or summary.get("ground_truth_read") is not False
        or summary.get("lesion_masks_read") != 0
        or summary.get("technical_timing_only") is not True
        or summary.get("eligible_for_inference") is not False
        or summary.get("end_to_end_time_measured") is not False
        or summary.get("qualified") is not False
        or summary.get("research_only") is not True
        or summary.get("clinical_use_allowed") is not False
    ):
        raise PipelineError("Resumo da auditoria de segmentacao LLD-MMRI adulterado.")
    selection = summary.get("selection")
    primary_attempt_name = summary.get("primary_attempt_name", "primary_full_resolution")
    fallback_attempt_name = summary.get("fallback_attempt_name", "fallback_fast_3mm")
    mask_quality_policy = summary.get("mask_quality_policy", "legacy_voxel_geometry_v1")
    if (
        not isinstance(primary_attempt_name, str)
        or not primary_attempt_name
        or not isinstance(fallback_attempt_name, str)
        or not fallback_attempt_name
        or mask_quality_policy not in {"legacy_voxel_geometry_v1", MASK_QUALITY_POLICY}
    ):
        raise PipelineError("Politica da auditoria de segmentacao LLD-MMRI invalida.")
    if selection == "first_n_frozen_protocol_order_no_labels":
        selected = manifest["cases"][: len(rows)]
    elif selection == "lowest_whole_grid_support_no_labels" and harmonized_by_id:
        protocol_order = {case["case_id"]: index for index, case in enumerate(manifest["cases"])}
        selected = sorted(
            manifest["cases"],
            key=lambda case: (
                min(
                    float(item["whole_reference_grid_support_fraction"])
                    for item in harmonized_by_id[str(case["case_id"])]["files"]
                ),
                protocol_order[str(case["case_id"])],
            ),
        )[: len(rows)]
    else:
        raise PipelineError("Selecao da auditoria de segmentacao LLD-MMRI invalida.")
    expected_ids = [str(case["case_id"]) for case in selected]
    if summary.get("case_ids") != expected_ids or [row.get("case_id") for row in rows] != expected_ids:
        raise PipelineError("Ordem da auditoria de segmentacao LLD-MMRI divergiu do protocolo.")
    for case, row in zip(selected, rows, strict=True):
        case_id = str(case["case_id"])
        mask_path = (pilot_root / case_id / "liver_mask_venous.nii.gz").resolve()
        elapsed = row.get("segmentation_elapsed_seconds")
        if row.get("segmentation_status") == "technical_failure_no_valid_liver_mask":
            if (
                (pilot_root / case_id).exists()
                or row.get("selection") != selection
                or row.get("mask_sha256") is not None
                or row.get("liver_voxels") != 0
                or row.get("dynamic_liver_support_fraction") is not None
                or row.get("minimum_dynamic_liver_support_fraction") is not None
                or row.get("all_dynamic_liver_support_at_least_99_percent") is not False
                or row.get("technical_failure_counts_as_error") is not True
                or isinstance(elapsed, bool)
                or not isinstance(elapsed, (int, float))
                or not math.isfinite(float(elapsed))
                or float(elapsed) < 0
                or row.get("within_180_seconds_segmentation_only") is not (float(elapsed) <= 180.0)
            ):
                raise PipelineError("Falha tecnica da auditoria LLD-MMRI adulterada.")
            continue
        if row.get("segmentation_status") != "valid_liver_mask":
            raise PipelineError("Status da segmentacao LLD-MMRI invalido.")
        if not mask_path.is_relative_to(pilot_root) or not mask_path.is_file():
            raise PipelineError("Mascara auditada LLD-MMRI ausente ou insegura.")
        if set(path.name for path in (pilot_root / case_id).iterdir()) != {"liver_mask_venous.nii.gz"}:
            raise PipelineError("Diretorio de mascara auditada LLD-MMRI contem arquivo inesperado.")
        harmonized = harmonized_by_id.get(case_id)
        if harmonized is not None:
            by_role = {str(item["role"]): item for item in harmonized["files"]}
            venous = (
                Path(harmonization_root).resolve()
                / str(by_role["t1_venous"]["relative_path"])
            ).resolve()
        else:
            venous = (download_root / str(case["images"]["t1_venous"]["relative_path"])).resolve()
        reference = _read_valid_nifti(venous, role="t1_venous")
        mask_image = _read_valid_nifti(mask_path, role="liver_mask_venous")
        voxels = int((np.asarray(sitk.GetArrayFromImage(mask_image)) > 0).sum())
        quality_passed = True
        if mask_quality_policy == MASK_QUALITY_POLICY:
            quality_passed = bool(
                evaluate_liver_mask_quality(mask_path, reference)["gate_passed"]
            )
        support = (
            dynamic_liver_support_fractions(harmonized, mask_image)
            if harmonized is not None
            else {role: 1.0 for role in DYNAMIC_ROLES}
        )
        if (
            not _same_geometry(reference, mask_image)
            or not quality_passed
            or voxels < MINIMUM_LIVER_VOXELS
            or row.get("selection") != selection
            or row.get("mask_sha256") != _sha256(mask_path)
            or row.get("liver_voxels") != voxels
            or row.get("dynamic_liver_support_fraction") != support
            or row.get("minimum_dynamic_liver_support_fraction") != min(support.values())
            or row.get("all_dynamic_liver_support_at_least_99_percent")
            is not (min(support.values()) >= LIVER_SUPPORT_THRESHOLD)
            or isinstance(elapsed, bool)
            or not isinstance(elapsed, (int, float))
            or not math.isfinite(float(elapsed))
            or float(elapsed) < 0
            or row.get("within_180_seconds_segmentation_only") is not (float(elapsed) <= 180.0)
            or row.get("segmentation_selected_attempt")
            not in {primary_attempt_name, fallback_attempt_name}
        ):
            raise PipelineError("Registro da auditoria de segmentacao LLD-MMRI adulterado.")
    valid_rows = [row for row in rows if row.get("segmentation_status") == "valid_liver_mask"]
    technical_failures = len(rows) - len(valid_rows)
    if (
        summary.get("segmentation_technical_failure_case_count") != technical_failures
        or summary.get("technical_failures_count_as_errors") is not True
        or summary.get("minimum_dynamic_liver_support_fraction")
        != (min(row["minimum_dynamic_liver_support_fraction"] for row in valid_rows) if valid_rows else None)
        or summary.get("all_dynamic_liver_support_at_least_99_percent")
        is not (bool(valid_rows) and all(row["all_dynamic_liver_support_at_least_99_percent"] for row in rows))
    ):
        raise PipelineError("Resumo de falhas tecnicas LLD-MMRI adulterado.")
    maximum = max(float(row["segmentation_elapsed_seconds"]) for row in rows)
    minimum = (
        min(float(row["minimum_dynamic_liver_support_fraction"]) for row in valid_rows)
        if valid_rows else None
    )
    all_support = bool(valid_rows) and all(
        bool(row["all_dynamic_liver_support_at_least_99_percent"]) for row in rows
    )
    fallback_count = sum(bool(row.get("segmentation_fallback_used", False)) for row in rows)
    if (
        summary.get("max_segmentation_seconds") != maximum
        or summary.get("all_segmentation_only_within_180_seconds") is not (maximum <= 180.0)
        or summary.get("liver_support_threshold") != LIVER_SUPPORT_THRESHOLD
        or summary.get("minimum_dynamic_liver_support_fraction") != minimum
        or summary.get("all_dynamic_liver_support_at_least_99_percent") is not all_support
        or summary.get("segmentation_fallback_case_count", 0) != fallback_count
    ):
        raise PipelineError("Agregacao da auditoria de segmentacao LLD-MMRI divergiu.")
    return summary


__all__ = [
    "LIVER_SUPPORT_THRESHOLD",
    "PILOT_SCHEMA",
    "run_lld_mmri_v23_segmentation_pilot",
    "verify_lld_mmri_v23_segmentation_pilot",
]
