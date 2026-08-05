"""Label-blind T2/DWI/ADC candidates for single-dynamic-phase liver MRI."""
from __future__ import annotations

import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from dtwin.core import PipelineError
from dtwin.learning.candidate_dataset import CANDIDATE_RECORD_SCHEMA
from dtwin.learning.monophase_slice_candidates import (
    case_intensity_window,
    is_proven_label_blind_input,
    liver_slice_indices,
    liver_xy_bbox,
    publish_immutable_directory,
    render_axial_candidate,
)
from dtwin.learning.protocol import canonical_sha256, sha256_file


SCHEMA = "oren-monophase-complementary-candidates-v1"
SEQUENCE_ROLES = ("t2_haste", "dwi_trace_run_03", "dwi_adc")


def _jsonl(path: Path) -> list[dict[str, Any]]:
    try:
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    except (OSError, json.JSONDecodeError) as exc:
        raise PipelineError(f"Manifesto invalido: {path}") from exc
    if any(not isinstance(row, dict) for row in rows):
        raise PipelineError("Manifesto contem registro invalido.")
    return rows


def _role(row: dict[str, Any], name: str) -> dict[str, Any] | None:
    matches = [item for item in row.get("files", []) if item.get("role") == name]
    if len(matches) > 1:
        raise PipelineError(f"Papel duplicado em {row.get('case_id')}: {name}")
    return matches[0] if matches else None


def _relative(root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError as exc:
        raise PipelineError(f"Artefato fora do workspace: {path}") from exc


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as stream:
        for row in rows:
            stream.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def render_registration_overlay(
    image: Image.Image,
    mask_plane: np.ndarray,
    bbox: tuple[int, int, int, int],
    image_size: int = 448,
) -> Image.Image:
    """Overlay the automatic liver-mask boundary for audit only."""
    try:
        from scipy.ndimage import binary_erosion
    except ImportError as exc:
        raise PipelineError("SciPy obrigatorio para overlay de auditoria.") from exc
    y0, y1, x0, x1 = bbox
    cropped = np.asarray(mask_plane[y0:y1, x0:x1], dtype=bool)
    edge = cropped & ~binary_erosion(cropped)
    mask_image = Image.fromarray((edge.astype(np.uint8) * 255), mode="L")
    scale = min(image_size / mask_image.width, image_size / mask_image.height)
    resized = mask_image.resize(
        (max(1, round(mask_image.width * scale)), max(1, round(mask_image.height * scale))),
        Image.Resampling.NEAREST,
    )
    canvas = Image.new("L", (image_size, image_size), color=0)
    canvas.paste(resized, ((image_size - resized.width) // 2, (image_size - resized.height) // 2))
    output = image.convert("RGB").copy()
    pixels = np.asarray(output).copy()
    boundary = np.asarray(canvas) > 0
    # Thicken by one pixel so the contour remains readable in the gallery.
    boundary = boundary | np.roll(boundary, 1, 0) | np.roll(boundary, -1, 0) | np.roll(boundary, 1, 1) | np.roll(boundary, -1, 1)
    pixels[boundary] = (255, 214, 10)
    return Image.fromarray(pixels, mode="RGB")


def resample_liver_mask(reference_image: Any, liver_mask_image: Any) -> Any:
    """Reproject an automatic liver mask using physical image coordinates."""
    try:
        import SimpleITK as sitk
    except ImportError as exc:
        raise PipelineError("SimpleITK obrigatorio.") from exc
    return sitk.Resample(
        liver_mask_image,
        reference_image,
        sitk.Transform(),
        sitk.sitkNearestNeighbor,
        0,
        sitk.sitkUInt8,
    )


def register_liver_mask(
    reference_image: Any, venous_image: Any, liver_mask_image: Any
) -> tuple[Any, dict[str, Any]]:
    """Rigid multimodal registration, returning a mask in reference geometry."""
    try:
        import SimpleITK as sitk
    except ImportError as exc:
        raise PipelineError("SimpleITK obrigatorio.") from exc
    if reference_image.GetDimension() != 3 or venous_image.GetDimension() != 3:
        raise PipelineError("Registro complementar exige volumes 3D.")
    fixed = sitk.Normalize(sitk.Cast(reference_image, sitk.sitkFloat32))
    moving = sitk.Normalize(sitk.Cast(venous_image, sitk.sitkFloat32))
    initial = sitk.CenteredTransformInitializer(
        fixed,
        moving,
        sitk.Euler3DTransform(),
        sitk.CenteredTransformInitializerFilter.GEOMETRY,
    )
    method = sitk.ImageRegistrationMethod()
    method.SetMetricAsMattesMutualInformation(numberOfHistogramBins=32)
    if min(reference_image.GetSize()) < 32 or int(np.prod(reference_image.GetSize())) < 32768:
        method.SetMetricSamplingStrategy(method.NONE)
        sampling = "all_voxels_small_volume"
    else:
        method.SetMetricSamplingStrategy(method.RANDOM)
        method.SetMetricSamplingPercentage(0.02, 20260804)
        sampling = "random_2_percent"
    method.SetInterpolator(sitk.sitkLinear)
    method.SetOptimizerAsRegularStepGradientDescent(
        learningRate=1.0,
        minStep=0.001,
        numberOfIterations=120,
        relaxationFactor=0.5,
        gradientMagnitudeTolerance=1e-6,
    )
    method.SetOptimizerScalesFromPhysicalShift()
    method.SetShrinkFactorsPerLevel([4, 2, 1])
    method.SetSmoothingSigmasPerLevel([2, 1, 0])
    method.SmoothingSigmasAreSpecifiedInPhysicalUnitsOn()
    method.SetInitialTransform(initial, inPlace=False)
    try:
        transform = method.Execute(fixed, moving)
    except RuntimeError as exc:
        raise PipelineError(f"Falha no registro multimodal: {exc}") from exc
    metric = float(method.GetMetricValue())
    if not np.isfinite(metric):
        raise PipelineError("Metrica de registro multimodal nao finita.")
    registered = sitk.Resample(
        liver_mask_image,
        reference_image,
        transform,
        sitk.sitkNearestNeighbor,
        0,
        sitk.sitkUInt8,
    )
    return registered, {
        "method": "rigid_euler3d_mattes_mutual_information",
        "metric_value": metric,
        "optimizer_iteration": int(method.GetOptimizerIteration()),
        "optimizer_stop_condition": str(method.GetOptimizerStopConditionDescription()),
        "deterministic_sampling_seed": 20260804,
        "sampling": sampling,
    }


def _usable_mask(mask_zyx: np.ndarray, reference_zyx: np.ndarray) -> tuple[bool, str | None]:
    if mask_zyx.shape != reference_zyx.shape or mask_zyx.ndim != 3:
        return False, "geometry_mismatch_after_resampling"
    voxels = int(mask_zyx.sum())
    if voxels < 100:
        return False, "insufficient_reprojected_liver_voxels"
    occupied = np.count_nonzero(np.any(mask_zyx, axis=(1, 2)))
    if occupied < 3:
        return False, "insufficient_reprojected_liver_planes"
    points = np.argwhere(mask_zyx)
    spans = points.max(axis=0) - points.min(axis=0) + 1
    if any(float(span) / float(size) > 0.92 for span, size in zip(spans, mask_zyx.shape)):
        return False, "implausible_liver_extent"
    if voxels / float(mask_zyx.size) > 0.35:
        return False, "implausible_liver_volume_fraction"
    values = np.asarray(reference_zyx[mask_zyx], dtype=np.float64)
    finite = values[np.isfinite(values)]
    if finite.size < 100 or np.count_nonzero(np.abs(finite) > 1e-6) / finite.size < 0.50:
        return False, "liver_mask_projects_mostly_to_background"
    return True, None


def build_complementary_candidates(
    *,
    input_manifest_path: Path,
    input_files_root: Path,
    workspace_root: Path,
    output_root: Path,
    sequence_roles: tuple[str, ...] = SEQUENCE_ROLES,
    limit_cases: int | None = None,
    allow_rigid_fallback: bool = False,
    dataset_id: str = "openswisshcc_development",
    progress_callback: Any | None = None,
) -> dict[str, Any]:
    root = Path(workspace_root).resolve()
    destination = Path(output_root).resolve()
    if destination.exists():
        raise PipelineError("Saida imutavel ja existe.")
    if not sequence_roles or any(role not in SEQUENCE_ROLES for role in sequence_roles):
        raise PipelineError("Lista de sequencias complementares invalida.")
    dataset_id = str(dataset_id).strip()
    if not dataset_id:
        raise PipelineError("dataset_id nao pode ser vazio.")
    rows = sorted(_jsonl(Path(input_manifest_path)), key=lambda row: str(row["case_id"]))
    if limit_cases is not None:
        if limit_cases < 1:
            raise PipelineError("limit_cases deve ser positivo.")
        rows = rows[:limit_cases]
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{destination.name}.", dir=destination.parent))
    records: list[dict[str, Any]] = []
    sequences: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    try:
        try:
            import SimpleITK as sitk
        except ImportError as exc:
            raise PipelineError("SimpleITK obrigatorio.") from exc
        for row in rows:
            case_id = str(row["case_id"])
            if progress_callback is not None:
                progress_callback({"event": "case_started", "case_id": case_id})
            if not is_proven_label_blind_input(row):
                raise PipelineError(
                    f"Entrada de {case_id} não é comprovadamente label-blind."
                )
            if row.get("research_only") is not True:
                raise PipelineError(f"Caso fora do contrato de pesquisa: {case_id}")
            mask_item = _role(row, "liver_mask_venous")
            if mask_item is None:
                failures.append({"case_id": case_id, "sequence_role": None, "reason": "missing_liver_mask_venous"})
                continue
            mask_path = Path(input_files_root) / str(mask_item["relative_path"])
            if sha256_file(mask_path) != mask_item.get("sha256"):
                raise PipelineError(f"Hash da mascara hepática divergiu: {case_id}")
            mask_image = sitk.ReadImage(str(mask_path))
            venous_item = _role(row, "t1_venous")
            if venous_item is None:
                failures.append({"case_id": case_id, "sequence_role": None, "reason": "missing_t1_venous_for_registration"})
                continue
            venous_path = Path(input_files_root) / str(venous_item["relative_path"])
            if sha256_file(venous_path) != venous_item.get("sha256"):
                raise PipelineError(f"Hash da fase venosa divergiu: {case_id}")
            venous_image = sitk.ReadImage(str(venous_path))
            for role in sequence_roles:
                if progress_callback is not None:
                    progress_callback({"event": "sequence_started", "case_id": case_id, "sequence_role": role})
                item = _role(row, role)
                if item is None:
                    failures.append({"case_id": case_id, "sequence_role": role, "reason": "missing_sequence"})
                    continue
                source_path = Path(input_files_root) / str(item["relative_path"])
                if sha256_file(source_path) != item.get("sha256"):
                    raise PipelineError(f"Hash da sequencia divergiu: {case_id}/{role}")
                try:
                    image = sitk.ReadImage(str(source_path))
                    volume = sitk.GetArrayFromImage(image).astype(np.float32)
                    projected_mask = resample_liver_mask(image, mask_image)
                    liver = sitk.GetArrayFromImage(projected_mask) > 0
                    usable, reason = _usable_mask(liver, volume)
                    if usable:
                        registration = {
                            "method": "physical_coordinates_identity",
                            "rigid_fallback_used": False,
                            "initial_gate_passed": True,
                        }
                    elif allow_rigid_fallback:
                        registered_mask, rigid = register_liver_mask(
                            image, venous_image, mask_image
                        )
                        liver = sitk.GetArrayFromImage(registered_mask) > 0
                        usable, rigid_reason = _usable_mask(liver, volume)
                        if not usable:
                            raise PipelineError(
                                f"physical_projection:{reason};rigid_fallback:{rigid_reason}"
                            )
                        registration = {
                            **rigid,
                            "rigid_fallback_used": True,
                            "initial_gate_passed": False,
                            "initial_gate_failure": reason,
                        }
                    else:
                        raise PipelineError(f"physical_projection_gate:{reason}")
                    indices = liver_slice_indices(liver)
                    bbox = liver_xy_bbox(liver, 0.10)
                    window = case_intensity_window(volume, liver)
                    covered = 0
                    sequence_records: list[dict[str, Any]] = []
                    for number, axial_index in enumerate(indices, start=1):
                        relative = Path("slices") / role / case_id / f"axial_{axial_index:04d}.png"
                        target = staging / relative
                        target.parent.mkdir(parents=True, exist_ok=True)
                        rendered = render_axial_candidate(volume[axial_index], bbox, window, 448)
                        rendered.save(target, format="PNG", optimize=True)
                        plane_voxels = int(liver[axial_index].sum())
                        covered += plane_voxels
                        sequence_records.append({
                            "schema": CANDIDATE_RECORD_SCHEMA,
                            "case_id": case_id,
                            "patient_group_id": case_id,
                            "dataset_id": dataset_id,
                            "candidate_id": f"{role}-axial-{axial_index:04d}",
                            "candidate_kind": f"complementary_{role}_axial_liver_crop",
                            "sequence_role": role,
                            "automatic_candidate": True,
                            "panel_number": number,
                            "panel_total": len(indices),
                            "slice_indices": [axial_index],
                            "axial_index": axial_index,
                            "image_path": _relative(root, destination / relative),
                            "image_sha256": sha256_file(target),
                            "source_sequence_sha256": str(item["sha256"]),
                            "source_liver_mask_sha256": str(mask_item["sha256"]),
                            "source_venous_registration_sha256": str(venous_item["sha256"]),
                            "registration": registration,
                            "liver_voxels_in_slice": plane_voxels,
                            "intensity_window": list(window),
                            "crop_bbox_yxyx": list(bbox),
                            "single_phase_replicated_across_rgb": True,
                            "dynamic_enhancement_information_present": False,
                            "ground_truth_used": False,
                            "lesion_mask_used": False,
                            "research_only": True,
                            "clinical_use_allowed": False,
                        })
                    total = int(liver.sum())
                    if covered != total:
                        raise PipelineError("Gate inteiro de cobertura complementar falhou.")
                    audit_index = indices[len(indices) // 2]
                    # The candidate path is rooted at destination; staging mirrors its internal layout.
                    audit_source = staging / "slices" / role / case_id / f"axial_{audit_index:04d}.png"
                    with Image.open(audit_source) as base:
                        overlay = render_registration_overlay(base, liver[audit_index], bbox)
                    audit_relative = Path("registration_audit") / role / f"{case_id}.png"
                    audit_path = staging / audit_relative
                    audit_path.parent.mkdir(parents=True, exist_ok=True)
                    overlay.save(audit_path, format="PNG", optimize=True)
                    records.extend(sequence_records)
                    sequences.append({
                        "case_id": case_id,
                        "sequence_role": role,
                        "slice_count": len(indices),
                        "total_reprojected_liver_voxels": total,
                        "covered_reprojected_liver_voxels": covered,
                        "exact_coverage_gate": True,
                        "physical_mask_reprojection": True,
                        "rigid_multimodal_registration": registration,
                        "registration_audit_axial_index": audit_index,
                        "registration_audit_image": audit_relative.as_posix(),
                        "registration_audit_sha256": sha256_file(audit_path),
                    })
                    if progress_callback is not None:
                        progress_callback({
                            "event": "sequence_completed",
                            "case_id": case_id,
                            "sequence_role": role,
                            "slice_count": len(indices),
                            "rigid_fallback_used": bool(registration.get("rigid_fallback_used")),
                        })
                except Exception as exc:
                    failures.append({
                        "case_id": case_id,
                        "sequence_role": role,
                        "reason": f"{type(exc).__name__}:{exc}",
                    })
                    shutil.rmtree(staging / "slices" / role / case_id, ignore_errors=True)
                    if progress_callback is not None:
                        progress_callback({
                            "event": "sequence_failed",
                            "case_id": case_id,
                            "sequence_role": role,
                            "reason": f"{type(exc).__name__}:{exc}",
                        })
        records.sort(key=lambda value: (value["case_id"], value["sequence_role"], value["axial_index"]))
        sequences.sort(key=lambda value: (value["case_id"], value["sequence_role"]))
        failures.sort(key=lambda value: (value["case_id"], str(value["sequence_role"])))
        records_path = staging / "candidate_records.jsonl"
        sequences_path = staging / "sequence_coverage.jsonl"
        failures_path = staging / "technical_failures.jsonl"
        _write_jsonl(records_path, records)
        _write_jsonl(sequences_path, sequences)
        _write_jsonl(failures_path, failures)
        body = {
            "schema": SCHEMA,
            "status": "complete_label_blind_pending_independent_verification",
            "input_manifest_sha256": sha256_file(input_manifest_path),
            "dataset_id": dataset_id,
            "sequence_roles": list(sequence_roles),
            "expected_case_count": len(rows),
            "materialized_case_count": len({record["case_id"] for record in records}),
            "materialized_case_sequence_count": len(sequences),
            "candidate_record_count": len(records),
            "technical_failure_count": len(failures),
            "candidate_records_sha256": sha256_file(records_path),
            "sequence_coverage_sha256": sha256_file(sequences_path),
            "technical_failures_sha256": sha256_file(failures_path),
            "all_materialized_sequences_exact_coverage": all(item["exact_coverage_gate"] for item in sequences),
            "mask_use": "automatic_liver_mask_physical_projection_with_gated_rigid_fallback",
            "rigid_fallback_allowed": bool(allow_rigid_fallback),
            "ground_truth_read": False,
            "lesion_masks_read": 0,
            "synthetic_sequences_created": False,
            "research_only": True,
            "clinical_use_allowed": False,
        }
        manifest = {**body, "dataset_signature": canonical_sha256(body)}
        (staging / "dataset_manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        publish_immutable_directory(staging, destination)
        return manifest
    finally:
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)


__all__ = ["SCHEMA", "SEQUENCE_ROLES", "build_complementary_candidates", "resample_liver_mask"]
