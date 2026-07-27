"""Alinhamento T1 seguro do desenvolvimento OpenSwissHCC.

O método escolhe entre regradeamento físico por identidade e o transform
pairwise publicado usando apenas Dice de máscaras hepáticas automáticas. Labels
de HCC e máscaras de lesão não são aceitos por esta API.
"""
from __future__ import annotations

import gc
import hashlib
import json
import os
import shutil
import tempfile
import time
import uuid
from pathlib import Path, PurePosixPath
from typing import Any, Mapping

import numpy as np
import SimpleITK as sitk

from dtwin.core import PipelineError


ALGORITHM_VERSION = "openswisshcc-pairwise-or-identity-v1"
FORBIDDEN_RECORD_KEYS = {"label", "truth", "hcc", "positive", "negative"}


class AlignmentGateError(PipelineError):
    """O alinhamento não atingiu o Dice hepático mínimo predefinido."""


def _publish_directory(
    staging: Path, destination: Path, *, attempts: int = 12, base_delay: float = 0.25
) -> None:
    """Publique um diretório atomicamente, tolerando locks transitórios do Windows."""
    if attempts < 1:
        raise PipelineError("attempts de publicação deve ser positivo.")
    if destination.exists():
        raise PipelineError(f"Destino de publicação já existe: {destination}.")
    last_error: PermissionError | None = None
    for attempt in range(attempts):
        try:
            os.replace(staging, destination)
            return
        except PermissionError as exc:
            last_error = exc
            if destination.exists():
                raise PipelineError(
                    f"Destino apareceu durante publicação atômica: {destination}."
                ) from exc
            gc.collect()
            if attempt + 1 < attempts:
                time.sleep(min(base_delay * (2**attempt), 1.0))
    assert last_error is not None
    raise last_error


def dice_coefficient(first: np.ndarray, second: np.ndarray) -> float:
    a = np.asarray(first, dtype=bool)
    b = np.asarray(second, dtype=bool)
    if a.shape != b.shape:
        raise PipelineError(f"Máscaras com shapes incompatíveis: {a.shape} != {b.shape}.")
    denominator = int(a.sum()) + int(b.sum())
    if denominator == 0:
        raise PipelineError("Dice indefinido para duas máscaras vazias.")
    return float(2 * np.logical_and(a, b).sum() / denominator)


def select_alignment_method(
    *, identity_dice: float, pairwise_dice: float, minimum_dice: float
) -> dict[str, float | str]:
    values = {"identity": float(identity_dice), "pairwise": float(pairwise_dice)}
    if not 0.0 <= minimum_dice <= 1.0:
        raise PipelineError("minimum_dice deve estar em [0, 1].")
    if any(not np.isfinite(value) or not 0.0 <= value <= 1.0 for value in values.values()):
        raise PipelineError("Dice de alinhamento inválido.")
    # Empate favorece identidade: menor transformação e menor risco de artefato.
    method = "pairwise" if pairwise_dice > identity_dice else "identity"
    selected = values[method]
    if selected < minimum_dice:
        raise AlignmentGateError(
            f"Gate de alinhamento falhou: melhor Dice={selected:.6f} < {minimum_dice:.6f}."
        )
    return {
        "method": method,
        "identity_dice": values["identity"],
        "pairwise_dice": values["pairwise"],
        "selected_dice": selected,
        "minimum_dice": float(minimum_dice),
    }


def select_arterial_roles(
    input_roles: set[str], arterial_source_phase: str
) -> tuple[str, str]:
    if arterial_source_phase == "arterial_ttc_3":
        image, mask = "t1_arterial_ttc_3", "liver_mask_arterial_ttc_3"
    elif arterial_source_phase == "arterial":
        if "t1_arterial" in input_roles:
            image, mask = "t1_arterial", "liver_mask_arterial"
        else:
            image, mask = "t1_arterial_ttc_1", "liver_mask_arterial_ttc_1"
    else:
        raise PipelineError(f"Fase arterial de registro não autorizada: {arterial_source_phase!r}.")
    missing = {image, mask} - input_roles
    if missing:
        raise PipelineError(f"Input sem arterial/máscara esperada: {sorted(missing)}.")
    return image, mask


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(8 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PipelineError(f"JSON inválido ou ilegível: {path}: {exc}") from exc


def _load_input_records(
    input_root: Path, *, manifest_filename: str = "development_inputs.jsonl"
) -> dict[str, dict[str, Any]]:
    if manifest_filename not in {"development_inputs.jsonl", "holdout_inputs.jsonl"}:
        raise PipelineError("Manifesto de inputs OpenSwissHCC não autorizado.")
    path = input_root / "manifests" / manifest_filename
    records: dict[str, dict[str, Any]] = {}
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise PipelineError(f"Manifesto de inputs ausente: {path}.") from exc
    for line in lines:
        record = json.loads(line)
        case_id = str(record.get("case_id", ""))
        if not case_id.startswith("anon-") or case_id in records:
            raise PipelineError("case_id inválido ou duplicado no manifesto de inputs.")
        if FORBIDDEN_RECORD_KEYS & set(record):
            raise PipelineError("Manifesto de input contém ground truth protegido.")
        records[case_id] = record
    return records


def _load_registration_records(registration_root: Path) -> dict[str, dict[str, Any]]:
    payload = _load_json(registration_root / "registration_manifest.json")
    records: dict[str, dict[str, Any]] = {}
    for record in payload.get("records", []):
        case_id = str(record.get("case_id", ""))
        if not case_id.startswith("anon-") or case_id in records:
            raise PipelineError("case_id inválido ou duplicado no manifesto de registro.")
        if FORBIDDEN_RECORD_KEYS & set(record):
            raise PipelineError("Manifesto de registro contém ground truth protegido.")
        records[case_id] = record
    return records


def _resolve_record_files(
    record: Mapping[str, Any], *, base: Path, prefix: str = ""
) -> dict[str, tuple[Path, str]]:
    root = (base / prefix).resolve()
    result: dict[str, tuple[Path, str]] = {}
    for item in record.get("files", []):
        role = str(item.get("role", ""))
        relative = PurePosixPath(str(item.get("relative_path", "")))
        if not role or role in result or relative.is_absolute() or ".." in relative.parts:
            raise PipelineError("Entrada de arquivo insegura ou duplicada no manifesto.")
        path = (root / Path(*relative.parts)).resolve()
        if not path.is_relative_to(root) or not path.is_file():
            raise PipelineError(f"Arquivo de manifesto ausente ou fora do root: {relative}.")
        expected = str(item.get("sha256", ""))
        actual = _sha256(path)
        if actual != expected:
            raise PipelineError(f"SHA-256 incompatível para role {role}.")
        result[role] = (path, actual)
    return result


def _identity_resample_mask(source: Path, reference: sitk.Image) -> np.ndarray:
    moving = sitk.ReadImage(str(source))
    result = sitk.Resample(
        moving,
        reference,
        sitk.Transform(),
        sitk.sitkNearestNeighbor,
        0,
        moving.GetPixelID(),
    )
    return sitk.GetArrayFromImage(result) > 0


def _parameter_object(stage_0: Path, stage_1: Path, interpolation_order: int):
    try:
        import itk
    except ImportError as exc:  # pragma: no cover - depende do extra openswiss
        raise PipelineError(
            "Alinhamento OpenSwissHCC exige o extra opcional itk-elastix."
        ) from exc
    temporary = tempfile.TemporaryDirectory()
    folder = Path(temporary.name)
    shutil.copyfile(stage_0, folder / "TransformParameters.0.txt")
    shutil.copyfile(stage_1, folder / "TransformParameters.1.txt")
    parameters = itk.ParameterObject.New()
    parameters.ReadParameterFiles(
        [str(folder / "TransformParameters.0.txt"), str(folder / "TransformParameters.1.txt")]
    )
    parameters.SetParameter(0, "FinalBSplineInterpolationOrder", str(interpolation_order))
    parameters.SetParameter(1, "FinalBSplineInterpolationOrder", str(interpolation_order))
    return itk, parameters, temporary


def _pairwise_mask(source: Path, stage_0: Path, stage_1: Path) -> np.ndarray:
    itk, parameters, temporary = _parameter_object(stage_0, stage_1, 0)
    try:
        moving = itk.imread(str(source), itk.UC)
        result = itk.transformix_filter(
            moving, transform_parameter_object=parameters, log_to_console=False
        )
        return np.asarray(itk.array_view_from_image(result)) > 0
    finally:
        temporary.cleanup()


def _write_aligned_image(
    *, method: str, source: Path, reference: sitk.Image,
    stage_0: Path, stage_1: Path, destination: Path
) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if method == "identity":
        moving = sitk.ReadImage(str(source), sitk.sitkFloat32)
        result = sitk.Resample(
            moving, reference, sitk.Transform(), sitk.sitkLinear, 0.0, sitk.sitkFloat32
        )
        sitk.WriteImage(result, str(destination), True)
        return
    if method != "pairwise":
        raise PipelineError(f"Método de alinhamento inválido: {method!r}.")
    itk, parameters, temporary = _parameter_object(stage_0, stage_1, 3)
    try:
        moving = itk.imread(str(source), itk.F)
        result = itk.transformix_filter(
            moving, transform_parameter_object=parameters, log_to_console=False
        )
        itk.imwrite(result, str(destination), compression=True)
    finally:
        temporary.cleanup()


def _geometry_compatible(path: Path, reference: sitk.Image) -> bool:
    image = sitk.ReadImage(str(path))
    return (
        image.GetSize() == reference.GetSize()
        and np.allclose(image.GetSpacing(), reference.GetSpacing(), atol=1e-6)
        and np.allclose(image.GetOrigin(), reference.GetOrigin(), atol=1e-4)
        and np.allclose(image.GetDirection(), reference.GetDirection(), atol=1e-6)
    )


def _write_json_atomic(path: Path, payload: object) -> None:
    temporary = path.with_name(f".tmp-{uuid.uuid4().hex}")
    try:
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _cache_signature(
    case_id: str,
    input_files: Mapping[str, tuple[Path, str]],
    transform_files: Mapping[str, tuple[Path, str]],
    minimum_dice: float,
) -> str:
    payload = {
        "algorithm": ALGORITHM_VERSION,
        "case_id": case_id,
        "minimum_dice": minimum_dice,
        "inputs": {role: digest for role, (_path, digest) in sorted(input_files.items())},
        "transforms": {
            role: digest for role, (_path, digest) in sorted(transform_files.items())
        },
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _reuse_cache(case_dir: Path, signature: str) -> dict[str, Any]:
    manifest = _load_json(case_dir / "alignment_manifest.json")
    if manifest.get("cache_signature") != signature:
        raise PipelineError("Cache de alinhamento existe com assinatura incompatível.")
    resolved_case_dir = case_dir.resolve()
    for item in manifest.get("outputs", []):
        relative = PurePosixPath(str(item.get("filename", "")))
        if relative.is_absolute() or ".." in relative.parts or len(relative.parts) != 1:
            raise PipelineError("Cache de alinhamento contém caminho de saída inseguro.")
        path = (resolved_case_dir / relative.name).resolve()
        if not path.is_relative_to(resolved_case_dir):
            raise PipelineError("Cache de alinhamento contém caminho fora do caso.")
        if not path.is_file() or _sha256(path) != item.get("sha256"):
            raise PipelineError("Cache de alinhamento corrompido ou incompleto.")
    reused = dict(manifest)
    reused["cache_reused"] = True
    return reused


def _align_case(
    *, case_id: str, input_root: Path, registration_root: Path,
    output_root: Path, minimum_dice: float,
    input_manifest_filename: str,
) -> dict[str, Any]:
    """Alinhe arterial/tardia à venosa e grave cache imutável por hash."""
    started = time.perf_counter()
    input_root = Path(input_root).resolve()
    registration_root = Path(registration_root).resolve()
    output_root = Path(output_root).resolve()
    input_records = _load_input_records(
        input_root, manifest_filename=input_manifest_filename
    )
    registration_records = _load_registration_records(registration_root)
    if case_id not in input_records or case_id not in registration_records:
        raise PipelineError(f"case_id ausente nos manifestos OpenSwissHCC: {case_id!r}.")
    input_files = _resolve_record_files(input_records[case_id], base=input_root, prefix="inputs")
    transform_files = _resolve_record_files(
        registration_records[case_id], base=registration_root
    )
    signature = _cache_signature(
        case_id, input_files, transform_files, float(minimum_dice)
    )
    case_dir = output_root / case_id
    if case_dir.exists():
        return _reuse_cache(case_dir, signature)

    roles = set(input_files)
    arterial_image_role, arterial_mask_role = select_arterial_roles(
        roles, str(registration_records[case_id]["arterial_source_phase"])
    )
    required = {
        "t1_venous", "liver_mask_venous", "t1_delayed", "liver_mask_delayed",
        arterial_image_role, arterial_mask_role,
    }
    missing = required - roles
    if missing:
        raise PipelineError(f"Caso sem inputs obrigatórios: {sorted(missing)}.")

    output_root.mkdir(parents=True, exist_ok=True)
    staging = output_root / f".{case_id}.staging.{uuid.uuid4().hex}"
    staging.mkdir()
    try:
        reference_mask = sitk.ReadImage(str(input_files["liver_mask_venous"][0]))
        target = sitk.GetArrayFromImage(reference_mask) > 0
        reference_image = sitk.ReadImage(str(input_files["t1_venous"][0]), sitk.sitkFloat32)
        if reference_mask.GetSize() != reference_image.GetSize():
            raise PipelineError("Máscara e imagem venosa têm grades incompatíveis.")

        phase_specs = {
            "art": (
                arterial_image_role, arterial_mask_role, "arterial_to_venous"
            ),
            "del": ("t1_delayed", "liver_mask_delayed", "delayed_to_venous"),
        }
        decisions: dict[str, dict[str, float | str]] = {}
        outputs: list[dict[str, Any]] = []
        for phase, (image_role, mask_role, transform_prefix) in phase_specs.items():
            identity = _identity_resample_mask(input_files[mask_role][0], reference_mask)
            pairwise = _pairwise_mask(
                input_files[mask_role][0],
                transform_files[f"{transform_prefix}_stage_0"][0],
                transform_files[f"{transform_prefix}_stage_1"][0],
            )
            decision = select_alignment_method(
                identity_dice=dice_coefficient(identity, target),
                pairwise_dice=dice_coefficient(pairwise, target),
                minimum_dice=float(minimum_dice),
            )
            decisions[phase] = decision
            destination = staging / f"{phase}_registered_to_venous.nii.gz"
            _write_aligned_image(
                method=str(decision["method"]),
                source=input_files[image_role][0],
                reference=reference_image,
                stage_0=transform_files[f"{transform_prefix}_stage_0"][0],
                stage_1=transform_files[f"{transform_prefix}_stage_1"][0],
                destination=destination,
            )
            if not _geometry_compatible(destination, reference_image):
                raise PipelineError(f"Saída {phase} não coincide com a grade venosa.")
            outputs.append(
                {
                    "phase": phase,
                    "filename": destination.name,
                    "sha256": _sha256(destination),
                    "bytes": destination.stat().st_size,
                }
            )

        manifest = {
            "schema": "argos-public-liver-mri-alignment-v1",
            "algorithm_version": ALGORITHM_VERSION,
            "case_id": case_id,
            "reference_phase": "venous",
            "arterial_input_role": arterial_image_role,
            "cache_signature": signature,
            "alignment_decisions": decisions,
            "outputs": outputs,
            "elapsed_seconds": time.perf_counter() - started,
            "cache_reused": False,
            "research_only": True,
            "clinical_use_allowed": False,
            "requires_human_review": True,
        }
        if FORBIDDEN_RECORD_KEYS & set(manifest):
            raise PipelineError("Manifesto de alinhamento contém ground truth protegido.")
        _write_json_atomic(staging / "alignment_manifest.json", manifest)
        _publish_directory(staging, case_dir)
        return manifest
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def align_development_case(
    *, case_id: str, input_root: Path, registration_root: Path,
    output_root: Path, minimum_dice: float = 0.80
) -> dict[str, Any]:
    """Align one development case while preserving the legacy API."""

    return _align_case(
        case_id=case_id,
        input_root=input_root,
        registration_root=registration_root,
        output_root=output_root,
        minimum_dice=minimum_dice,
        input_manifest_filename="development_inputs.jsonl",
    )


def align_holdout_case_label_blind(
    *, case_id: str, input_root: Path, registration_root: Path,
    output_root: Path, minimum_dice: float = 0.80
) -> dict[str, Any]:
    """Align one holdout case without accepting any label artifact."""

    result = _align_case(
        case_id=case_id,
        input_root=input_root,
        registration_root=registration_root,
        output_root=output_root,
        minimum_dice=minimum_dice,
        input_manifest_filename="holdout_inputs.jsonl",
    )
    if result.get("research_only") is not True or result.get("clinical_use_allowed") is not False:
        raise PipelineError("Alinhamento holdout perdeu salvaguardas de pesquisa.")
    return result




