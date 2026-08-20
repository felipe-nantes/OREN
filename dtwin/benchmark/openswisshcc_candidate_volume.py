"""Blind candidate-centred multisequence MRI stacks for OpenSwissHCC v16.

The localizer mask used here is model-derived. Dataset lesion masks, labels and
clinical metadata are deliberately outside this interface. The resulting PNG
frames contain only source-image pixels: candidate contours are audit-only and
are never rendered into model inputs.
"""
from __future__ import annotations

import hashlib
import html
import json
import shutil
import uuid
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import numpy as np
import SimpleITK as sitk
from PIL import Image
from scipy import ndimage

from dtwin.benchmark.openswisshcc_alignment import _publish_directory, _sha256
from dtwin.benchmark.openswisshcc_lesion_localizer import (
    CASE_SCHEMA as LOCALIZER_CASE_SCHEMA,
)
from dtwin.benchmark.openswisshcc_lesion_localizer import (
    RUN_SCHEMA as LOCALIZER_RUN_SCHEMA,
)
from dtwin.benchmark.openswisshcc_lesion_localizer_chunks import MERGED_RUN_SCHEMA
from dtwin.benchmark.openswisshcc_localizer_enhancement_roi import _registered
from dtwin.benchmark.openswisshcc_localizer_roi import (
    _available,
    _bbox,
    _input_index,
    _load,
    _rows,
    _safe,
)
from dtwin.core import PipelineError
from dtwin.medgemma_screening import _write_json_atomic

CANDIDATE_SCHEMA = "argos-openswisshcc-candidate-volume-v16"
CASE_SCHEMA = "argos-openswisshcc-candidate-volume-case-v16"
COHORT_SCHEMA = "argos-openswisshcc-candidate-volume-cohort-v16"
REVIEW_SCHEMA = "argos-openswisshcc-localizer-roi-paired-review-v1"
CONTRACT = "dtwin-medgemma-volume-v1"

ROI_MM = 80.0
OUTPUT_SIDE = 384
TARGET_CANDIDATE_COVERAGE = 0.75
MIN_BASE_CANDIDATES = 3
MAX_CANDIDATES = 5
MIN_FRAMES = 5
MAX_FRAMES = 29

GROUPS = (
    ("t1_native", "dynamic", 5),
    ("t1_arterial_registered", "dynamic", 5),
    ("t1_venous", "dynamic", 5),
    ("t1_delayed_registered", "dynamic", 5),
    ("t2", "morphology", 3),
    ("dwi_trace", "morphology", 3),
    ("dwi_adc", "morphology", 3),
)

def _canonical(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()

def _valid_localizer_run_schema(summary: dict[str, Any]) -> bool:
    schema = summary.get("schema")
    return schema == LOCALIZER_RUN_SCHEMA or (
        schema == MERGED_RUN_SCHEMA
        and summary.get("source_run_schema") == LOCALIZER_RUN_SCHEMA
    )


def _geometry_equal(left: sitk.Image, right: sitk.Image) -> bool:
    return (
        left.GetSize() == right.GetSize()
        and np.allclose(left.GetSpacing(), right.GetSpacing(), rtol=0, atol=1e-5)
        and np.allclose(left.GetOrigin(), right.GetOrigin(), rtol=0, atol=1e-5)
        and np.allclose(left.GetDirection(), right.GetDirection(), rtol=0, atol=1e-5)
    )


def select_candidate_components(
    components: Iterable[dict[str, Any]],
    *,
    total_candidate_voxels: int,
    minimum_components: int = MIN_BASE_CANDIDATES,
    maximum_components: int = MAX_CANDIDATES,
    target_fraction: float = TARGET_CANDIDATE_COVERAGE,
) -> tuple[list[dict[str, Any]], float]:
    """Select the largest candidates using the frozen v16 coverage rule."""

    ordered = sorted(
        (dict(item) for item in components),
        key=lambda item: (-int(item["voxels"]), int(item["component_id"])),
    )
    if total_candidate_voxels < 0 or not 1 <= minimum_components <= maximum_components:
        raise PipelineError("Parametros da selecao candidata v16 invalidos.")
    if not 0.0 < float(target_fraction) <= 1.0:
        raise PipelineError("Cobertura candidata alvo v16 invalida.")
    if not ordered:
        if total_candidate_voxels != 0:
            raise PipelineError("Voxels candidatos sem componentes v16.")
        return [], 1.0
    if total_candidate_voxels <= 0 or sum(int(item["voxels"]) for item in ordered) != total_candidate_voxels:
        raise PipelineError("Contagem candidata v16 inconsistente.")

    limit = min(len(ordered), maximum_components)
    selected: list[dict[str, Any]] = []
    covered = 0
    for item in ordered[:limit]:
        selected.append(item)
        covered += int(item["voxels"])
        if len(selected) >= min(minimum_components, len(ordered)) and covered / total_candidate_voxels >= target_fraction:
            break
    fraction = covered / total_candidate_voxels
    if fraction < target_fraction:
        raise PipelineError(
            f"Os {maximum_components} maiores candidatos cobrem apenas {fraction:.6f}; alvo={target_fraction:.6f}."
        )
    return selected, fraction


def centered_slice_indices(center: float, size: int, count: int) -> list[int]:
    """Return exactly ``count`` unique centred indices, shifting at boundaries."""

    if size < count or count < 1 or count % 2 == 0 or not np.isfinite(center):
        raise PipelineError("Parametros de cortes centrados v16 invalidos.")
    middle = int(round(float(center)))
    start = middle - count // 2
    start = max(0, min(start, size - count))
    result = list(range(start, start + count))
    if len(result) != count or len(set(result)) != count:
        raise PipelineError("Cortes v16 duplicados ou incompletos.")
    return result

def preview_frame_indices(frame_count: int) -> list[int]:
    """Show start/centre/end without duplicating short groups."""

    if frame_count < 1:
        raise PipelineError("Grupo v16 vazio para preview.")
    return sorted({0, frame_count // 2, frame_count - 1})


def _component_records(candidate_img: sitk.Image, localizer_manifest: dict[str, Any]):
    array = sitk.GetArrayFromImage(candidate_img) > 0
    labels, count = ndimage.label(array, structure=ndimage.generate_binary_structure(3, 3))
    records = []
    for component_id in range(1, count + 1):
        indices_zyx = np.argwhere(labels == component_id)
        records.append(
            {
                "component_id": component_id,
                "voxels": int(indices_zyx.shape[0]),
                "centroid_index_xyz": [float(v) for v in indices_zyx.mean(axis=0)[::-1]],
            }
        )
    expected = localizer_manifest.get("features", {}).get("components", [])
    expected_ranked = sorted(expected, key=lambda item: int(item.get("rank_by_volume", 0)))
    if len(records) != int(localizer_manifest.get("features", {}).get("component_count", -1)):
        raise PipelineError("Componentes v16 divergiram do manifesto do localizador.")
    unmatched = list(records)
    ranked = []
    for source in expected_ranked:
        matches = [
            item
            for item in unmatched
            if item["voxels"] == int(source.get("voxels", -1))
            and np.allclose(
                item["centroid_index_xyz"],
                source.get("centroid_index_xyz", []),
                rtol=0,
                atol=1e-5,
            )
        ]
        if len(matches) != 1:
            raise PipelineError("Volume/centro candidato v16 divergiu do localizador.")
        actual = matches[0]
        unmatched.remove(actual)
        actual["source_component_id"] = int(source["component_id"])
        actual["rank_by_volume"] = int(source["rank_by_volume"])
        ranked.append(actual)
    return labels, ranked


def _group_window(array: np.ndarray, bbox: tuple[int, int, int, int], indices: list[int]) -> tuple[float, float]:
    y0, y1, x0, x1 = bbox
    values = np.asarray(array[indices, y0:y1, x0:x1], dtype=np.float32).ravel()
    values = values[np.isfinite(values)]
    nonzero = values[values != 0]
    if len(nonzero) >= 50:
        values = nonzero
    if len(values) < 10:
        raise PipelineError("Stack v16 sem intensidades suficientes.")
    lo, hi = (float(value) for value in np.percentile(values, [1, 99]))
    if not hi - lo > 1e-6:
        raise PipelineError("Stack v16 sem contraste util.")
    return lo, hi


def _render_source_crop(
    array: np.ndarray,
    bbox: tuple[int, int, int, int],
    *,
    lo: float,
    hi: float,
    spacing_xy: tuple[float, float],
    output_side: int,
) -> Image.Image:
    y0, y1, x0, x1 = bbox
    crop = np.asarray(array[y0:y1, x0:x1], dtype=np.float32)
    if crop.size == 0 or not np.isfinite(crop).all():
        raise PipelineError("Crop v16 vazio ou nao finito.")
    normalized = np.clip((crop - lo) / (hi - lo), 0.0, 1.0)
    source = Image.fromarray(np.rint(normalized * 255).astype(np.uint8), mode="L").convert("RGB")
    physical_width = source.width * float(spacing_xy[0])
    physical_height = source.height * float(spacing_xy[1])
    if physical_width <= 0 or physical_height <= 0:
        raise PipelineError("Spacing v16 invalido.")
    scale = min(output_side / physical_width, output_side / physical_height)
    target = (
        max(1, min(output_side, int(round(physical_width * scale)))),
        max(1, min(output_side, int(round(physical_height * scale)))),
    )
    source = source.resize(target, Image.Resampling.LANCZOS)
    canvas = Image.new("RGB", (output_side, output_side), (0, 0, 0))
    canvas.paste(source, ((output_side - target[0]) // 2, (output_side - target[1]) // 2))
    return canvas


def _validate_localizer(case_id: str, localizer_dir: Path, reference: sitk.Image):
    manifest_path = localizer_dir / "localizer_manifest.json"
    manifest = _load(manifest_path)
    candidate_path = localizer_dir / "liver_lesion_candidates_in_liver.nii.gz"
    if (
        manifest.get("schema") != LOCALIZER_CASE_SCHEMA
        or manifest.get("case_id") != case_id
        or manifest.get("status") != "candidate_scores_only_no_decision"
        or (
            manifest.get("candidate_mask_is_model_derived") is not True
            and manifest.get("candidate_mask_is_deterministic_enhancement") is not True
        )
        or manifest.get("ground_truth_read") is not False
        or manifest.get("ground_truth_lesion_mask_used") is not False
        or manifest.get("final_decision") is not None
        or not candidate_path.is_file()
        or _sha256(candidate_path) != manifest.get("filtered_candidate_mask_sha256")
    ):
        raise PipelineError("Localizador cego invalido para stack v16.")
    image = sitk.ReadImage(str(candidate_path))
    if not _geometry_equal(image, reference):
        raise PipelineError("Geometria candidata v16 divergiu do T1 venoso.")
    labels, components = _component_records(image, manifest)
    total = int(manifest["features"]["inside_liver_voxels"])
    if int((sitk.GetArrayFromImage(image) > 0).sum()) != total:
        raise PipelineError("Voxels candidatos v16 divergiram do manifesto.")
    return manifest, manifest_path, candidate_path, labels, components, total


def _original_dynamic_inputs(manifest_path: Path, input_root: Path) -> dict[str, dict[str, Any]]:
    root = Path(input_root).resolve()
    result: dict[str, dict[str, Any]] = {}
    required = ("t1_native", "t1_venous", "t1_delayed", "liver_mask_venous")
    for row in _rows(manifest_path):
        case_id = str(row.get("case_id", ""))
        files = row.get("files", [])
        if (
            row.get("schema") != "argos-public-liver-mri-input-v1"
            or not case_id.startswith("anon-")
            or case_id in result
            or row.get("research_only") is not True
            or row.get("clinical_use_allowed") is not False
            or not isinstance(files, list)
        ):
            raise PipelineError("Input dinamico original v16 inseguro.")
        if any("lesion" in (str(item.get("role", "")) + str(item.get("relative_path", ""))).lower() for item in files):
            raise PipelineError("Arquivo de lesao do dataset proibido no fallback v16.")
        by = {str(item.get("role", "")): item for item in files}
        if len(by) != len(files) or any(role not in by for role in required):
            raise PipelineError("Fase dinamica original obrigatoria ausente/duplicada no fallback v16.")
        if "t1_arterial" in by:
            arterial_role = "t1_arterial"
        elif "t1_arterial_ttc_3" in by:
            arterial_role = "t1_arterial_ttc_3"
        else:
            ttc_roles = [role for role in by if role.startswith("t1_arterial_ttc_")]
            if not ttc_roles or any(not role.rsplit("_", 1)[-1].isdigit() for role in ttc_roles):
                raise PipelineError("Fase arterial original ausente/invalida no fallback v16.")
            arterial_role = max(ttc_roles, key=lambda role: int(role.rsplit("_", 1)[-1]))
        roles = (*required, arterial_role)
        result[case_id] = {
            "arterial_role": arterial_role,
            "paths": {role: _safe(root, by[role]) for role in roles},
            "hashes": {role: str(by[role]["sha256"]) for role in roles},
        }
    return result


def _registered_or_none(case_id: str, registration_root: Path) -> dict[str, Any] | None:
    registration_root = Path(registration_root).resolve()
    case_root = (registration_root / case_id).resolve()
    if not case_root.is_relative_to(registration_root):
        raise PipelineError("Diretorio de registro v16 escapou da raiz autorizada.")
    manifest_path = case_root / "alignment_manifest.json"
    if not case_root.exists():
        return None
    if not manifest_path.is_file():
        if any(case_root.iterdir()):
            raise PipelineError("Registro v16 parcial existe sem manifesto; fallback recusado.")
        return None
    return _registered(case_id, registration_root)


def _sources_for_case(case_id: str, morphology: dict[str, Any], dynamic: dict[str, Any], registered: dict[str, Any] | None):
    if morphology["paths"]["t1_venous"] != dynamic["paths"]["t1_venous"]:
        raise PipelineError("Fontes venosas v16 divergentes.")
    morph_roles = morphology["roles"]
    t2_role = morph_roles[1]
    trace_role = morph_roles[2]
    if registered is None:
        arterial_role = dynamic["arterial_role"]
        arterial = (dynamic["paths"][arterial_role], dynamic["hashes"][arterial_role], arterial_role, "t1_arterial_original", "original_unregistered_physical_center")
        delayed = (dynamic["paths"]["t1_delayed"], dynamic["hashes"]["t1_delayed"], "t1_delayed", "t1_delayed_original", "original_unregistered_physical_center")
    else:
        arterial = (registered["t1_arterial_registered"]["path"], registered["t1_arterial_registered"]["sha256"], registered["t1_arterial_registered"]["source_role"], "t1_arterial_registered", "registered_to_venous")
        delayed = (registered["t1_delayed_registered"]["path"], registered["t1_delayed_registered"]["sha256"], registered["t1_delayed_registered"]["source_role"], "t1_delayed_registered", "registered_to_venous")
    sources = {
        "t1_native": (dynamic["paths"]["t1_native"], dynamic["hashes"]["t1_native"], "t1_native", "t1_native", "native_geometry"),
        "t1_arterial_registered": arterial,
        "t1_venous": (dynamic["paths"]["t1_venous"], dynamic["hashes"]["t1_venous"], "t1_venous", "t1_venous", "reference_geometry"),
        "t1_delayed_registered": delayed,
        "t2": (morphology["paths"][t2_role], morphology["hashes"][t2_role], t2_role, "t2", "native_geometry"),
        "dwi_trace": (morphology["paths"][trace_role], morphology["hashes"][trace_role], trace_role, "dwi_trace", "native_geometry"),
        "dwi_adc": (morphology["paths"]["dwi_adc"], morphology["hashes"]["dwi_adc"], "dwi_adc", "dwi_adc", "native_geometry"),
    }
    for role, (path, expected_hash, _, _, _) in sources.items():
        if not Path(path).is_file() or _sha256(Path(path)) != expected_hash:
            raise PipelineError(f"Fonte/hash v16 invalido: {role}.")
    return sources


def _render_group(
    *,
    role: str,
    category: str,
    count: int,
    image: sitk.Image,
    physical_center: tuple[float, float, float],
    candidate_dir: Path,
    frame_order: int,
    roi_mm: float,
    output_side: int,
    max_input_bytes: int,
):
    continuous = image.TransformPhysicalPointToContinuousIndex(physical_center)
    if not _available(continuous, image):
        return None, frame_order, "center_outside_fov"
    try:
        indices = centered_slice_indices(continuous[2], image.GetSize()[2], count)
        bbox = _bbox(continuous, image, roi_mm)
        array = sitk.GetArrayFromImage(image).astype(np.float32, copy=False)
        if not np.isfinite(array).all():
            raise PipelineError("Fonte v16 contem intensidades nao finitas.")
        lo, hi = _group_window(array, bbox, indices)
    except PipelineError:
        return None, frame_order, "insufficient_geometry_or_contrast"

    frames = []
    for group_order, source_z in enumerate(indices, 1):
        frame_order += 1
        filename = f"frame_{frame_order:03d}_{role}_z{source_z:04d}.png"
        path = candidate_dir / filename
        rendered = _render_source_crop(
            array[source_z],
            bbox,
            lo=lo,
            hi=hi,
            spacing_xy=(image.GetSpacing()[0], image.GetSpacing()[1]),
            output_side=output_side,
        )
        rendered.save(path, format="PNG", optimize=False)
        if path.stat().st_size > max_input_bytes:
            raise PipelineError("Frame v16 excede limite individual de bytes.")
        frames.append(
            {
                "order": frame_order,
                "group_order": group_order,
                "filename": filename,
                "source_index_z": source_z,
                "sha256": _sha256(path),
                "bytes": path.stat().st_size,
                "width": rendered.width,
                "height": rendered.height,
                "mode": rendered.mode,
            }
        )
    return (
        {
            "role": role,
            "category": category,
            "frame_count": len(frames),
            "physical_center_lps_xyz": [float(v) for v in physical_center],
            "continuous_center_index_xyz": [float(v) for v in continuous],
            "selected_source_indices_z": indices,
            "crop_bbox_yxyx": list(bbox),
            "window_percentile_1_99": [lo, hi],
            "window_shared_across_group": True,
            "frames": frames,
        },
        frame_order,
        None,
    )


def _render_candidate(
    *,
    case_id: str,
    candidate_number: int,
    candidate_total: int,
    component: dict[str, Any] | None,
    fallback_center_xyz: np.ndarray | None,
    reference: sitk.Image,
    sources: dict[str, tuple[Path, str, str, str, str]],
    destination: Path,
    roi_mm: float,
    output_side: int,
    max_input_bytes: int,
) -> dict[str, Any]:
    destination.mkdir()
    center_xyz = fallback_center_xyz if component is None else np.asarray(component["centroid_index_xyz"], dtype=float)
    if center_xyz is None or len(center_xyz) != 3:
        raise PipelineError("Centro candidato/fallback v16 ausente.")
    physical = reference.TransformContinuousIndexToPhysicalPoint(tuple(float(value) for value in center_xyz))
    groups = []
    omitted = []
    frame_order = 0
    for role, category, count in GROUPS:
        path, source_hash, source_role, rendered_role, alignment_mode = sources[role]
        image = sitk.ReadImage(str(path), sitk.sitkFloat32)
        group, frame_order, reason = _render_group(
            role=rendered_role,
            category=category,
            count=count,
            image=image,
            physical_center=physical,
            candidate_dir=destination,
            frame_order=frame_order,
            roi_mm=roi_mm,
            output_side=output_side,
            max_input_bytes=max_input_bytes,
        )
        if group is None:
            omitted.append({"role": rendered_role, "category": category, "reason": reason, "source_role": source_role, "source_sha256": source_hash, "alignment_mode": alignment_mode})
        else:
            group["source_role"] = source_role
            group["source_sha256"] = source_hash
            group["alignment_mode"] = alignment_mode
            groups.append(group)
    dynamic_roles = {group["role"] for group in groups if group["category"] == "dynamic"}
    morph_roles = {group["role"] for group in groups if group["category"] == "morphology"}
    frames = [frame for group in groups for frame in group["frames"]]
    gate = {
        "venous_group_present": "t1_venous" in dynamic_roles,
        "at_least_three_dynamic_groups": len(dynamic_roles) >= 3,
        "at_least_one_morphology_group": bool(morph_roles),
        "frame_count_within_contract": MIN_FRAMES <= len(frames) <= MAX_FRAMES,
        "all_frames_384_rgb": all(frame["width"] == output_side and frame["height"] == output_side and frame["mode"] == "RGB" for frame in frames),
        "all_hashes_present": all(len(frame["sha256"]) == 64 for frame in frames),
        "source_pixels_only": True,
        "candidate_contour_rendered": False,
        "ground_truth_read": False,
        "dataset_lesion_mask_used": False,
        "phi_metadata_included": False,
    }
    positive_checks = (
        "venous_group_present",
        "at_least_three_dynamic_groups",
        "at_least_one_morphology_group",
        "frame_count_within_contract",
        "all_frames_384_rgb",
        "all_hashes_present",
        "source_pixels_only",
    )
    negative_checks = (
        "candidate_contour_rendered",
        "ground_truth_read",
        "dataset_lesion_mask_used",
        "phi_metadata_included",
    )
    gate["passed"] = all(gate[key] is True for key in positive_checks) and all(
        gate[key] is False for key in negative_checks
    )
    if not gate["passed"]:
        raise PipelineError(f"Gate do stack candidato v16 falhou em {case_id}/{candidate_number}: {gate}.")
    manifest = {
        "schema": CANDIDATE_SCHEMA,
        "contract": CONTRACT,
        "case_id": case_id,
        "candidate_number": candidate_number,
        "candidate_total": candidate_total,
        "component_rank": None if component is None else int(component["rank_by_volume"]),
        "component_id": None if component is None else int(component["source_component_id"]),
        "component_voxels": 0 if component is None else int(component["voxels"]),
        "fallback_no_candidate": component is None,
        "fallback_reason": "no_model_derived_candidate_liver_center" if component is None else None,
        "reference_role": "t1_venous",
        "dynamic_alignment_mode": sources["t1_arterial_registered"][4],
        "physical_center_lps_xyz": [float(value) for value in physical],
        "roi_mm": roi_mm,
        "output_side": output_side,
        "normalization": "per_role_candidate_roi_percentile_1_99_shared_across_frames",
        "frame_order": "dynamic_native_art_venous_delayed_then_t2_trace_adc",
        "frame_count": len(frames),
        "groups": groups,
        "omitted_groups": omitted,
        "gate": gate,
        "research_only": True,
        "clinical_use_allowed": False,
        "requires_human_review": True,
    }
    _write_json_atomic(destination / "manifest.json", manifest)
    return manifest


def _validate_manifest_files(candidate_dir: Path, manifest: dict[str, Any]) -> None:
    if manifest.get("schema") != CANDIDATE_SCHEMA or manifest.get("gate", {}).get("passed") is not True:
        raise PipelineError("Manifesto candidato v16 invalido.")
    frames = [frame for group in manifest.get("groups", []) for frame in group.get("frames", [])]
    if len(frames) != manifest.get("frame_count") or len(frames) != len({frame.get("filename") for frame in frames}):
        raise PipelineError("Lista de frames v16 inconsistente ou duplicada.")
    for frame in frames:
        path = (candidate_dir / str(frame["filename"])).resolve()
        if not path.is_relative_to(candidate_dir.resolve()) or not path.is_file() or path.stat().st_size != int(frame["bytes"]) or _sha256(path) != frame["sha256"]:
            raise PipelineError("Frame/hash v16 ausente ou inconsistente.")


def build_candidate_volume_case(
    *,
    case_id: str,
    morphology_source: dict[str, Any],
    dynamic_source: dict[str, Any],
    registered_source: dict[str, Any] | None,
    localizer_dir: Path,
    destination: Path,
    roi_mm: float = ROI_MM,
    output_side: int = OUTPUT_SIDE,
    max_input_bytes: int = 8_000_000,
    minimum_candidates: int = MIN_BASE_CANDIDATES,
    maximum_candidates: int = MAX_CANDIDATES,
    candidate_target_fraction: float = TARGET_CANDIDATE_COVERAGE,
) -> dict[str, Any]:
    if not case_id.startswith("anon-") or not 40 <= roi_mm <= 140 or output_side != OUTPUT_SIDE:
        raise PipelineError("Parametros do caso v16 invalidos.")
    sources = _sources_for_case(case_id, morphology_source, dynamic_source, registered_source)
    reference = sitk.ReadImage(str(sources["t1_venous"][0]), sitk.sitkFloat32)
    lm, lm_path, candidate_path, _, components, total_voxels = _validate_localizer(case_id, Path(localizer_dir), reference)
    if lm.get("input_sha256") != sources["t1_venous"][1]:
        raise PipelineError("T1 venoso v16 nao corresponde ao localizador.")
    selected, coverage = select_candidate_components(
        components,
        total_candidate_voxels=total_voxels,
        minimum_components=minimum_candidates,
        maximum_components=maximum_candidates,
        target_fraction=candidate_target_fraction,
    )
    fallback_center = None
    if not selected:
        liver_path = morphology_source["paths"]["liver_mask_venous"]
        liver = sitk.ReadImage(str(liver_path))
        if not _geometry_equal(liver, reference):
            raise PipelineError("Mascara hepatica v16 divergiu do T1 venoso.")
        indices = np.argwhere(sitk.GetArrayFromImage(liver) > 0)
        if not len(indices):
            raise PipelineError("Mascara hepatica vazia no fallback v16.")
        fallback_center = indices.mean(axis=0)[::-1]
    destination.mkdir()
    candidate_records = []
    actual = selected if selected else [None]
    for number, component in enumerate(actual, 1):
        candidate_dir = destination / f"candidate_{number:03d}"
        manifest = _render_candidate(
            case_id=case_id,
            candidate_number=number,
            candidate_total=len(actual),
            component=component,
            fallback_center_xyz=fallback_center,
            reference=reference,
            sources=sources,
            destination=candidate_dir,
            roi_mm=roi_mm,
            output_side=output_side,
            max_input_bytes=max_input_bytes,
        )
        _validate_manifest_files(candidate_dir, manifest)
        candidate_records.append(
            {
                "candidate_number": number,
                "relative_directory": candidate_dir.name,
                "manifest_sha256": _sha256(candidate_dir / "manifest.json"),
                "frame_count": manifest["frame_count"],
                "component_rank": manifest["component_rank"],
                "component_voxels": manifest["component_voxels"],
                "fallback_no_candidate": manifest["fallback_no_candidate"],
            }
        )
    manifest = {
        "schema": CASE_SCHEMA,
        "contract": CONTRACT,
        "case_id": case_id,
        "strategy": "model_localizer_candidate_centered_multisequence_volume_v16",
        "selection": {
            "rule": "largest_until_minimum_and_target_fraction_with_maximum",
            "component_count": len(components),
            "total_candidate_voxels": total_voxels,
            "selected_component_count": len(selected),
            "selected_component_ranks": [int(item["rank_by_volume"]) for item in selected],
            "selected_candidate_voxels": sum(int(item["voxels"]) for item in selected),
            "candidate_volume_coverage_fraction": coverage,
            "target_fraction": candidate_target_fraction,
            "minimum_candidates": minimum_candidates,
            "maximum_candidates": maximum_candidates,
            "fallback_no_candidate": not bool(selected),
        },
        "candidate_stack_count": len(candidate_records),
        "candidate_stacks": candidate_records,
        "dynamic_alignment_mode": sources["t1_arterial_registered"][4],
        "source_localizer_manifest_sha256": _sha256(lm_path),
        "source_candidate_mask_sha256": _sha256(candidate_path),
        "source_sha256": {rendered_role: source_hash for _, (_, source_hash, _, rendered_role, _) in sources.items()},
        "gate": {
            "all_candidate_manifests_valid": True,
            "candidate_coverage_passed": coverage >= candidate_target_fraction,
            "ground_truth_read": False,
            "dataset_lesion_mask_used": False,
            "phi_metadata_included": False,
            "passed": True,
        },
        "inference_executed": False,
        "research_only": True,
        "clinical_use_allowed": False,
        "requires_human_review": True,
    }
    _write_json_atomic(destination / "case_manifest.json", manifest)
    return manifest


def _review_case_ids(review_path: Path) -> tuple[list[str], dict[str, Any]]:
    review = _load(review_path)
    confirmations = review.get("confirmations", {})
    if (
        review.get("schema") != REVIEW_SCHEMA
        or review.get("review_status") != "approved_for_research_scores_only"
        or review.get("ground_truth_read") is not False
        or review.get("lesion_mask_used") is not False
        or review.get("research_only") is not True
        or review.get("clinical_use_allowed") is not False
        or not confirmations
        or not all(value is True for value in confirmations.values())
    ):
        raise PipelineError("Revisao tecnica fonte v10 nao aprovada para piloto v16.")
    case_ids = [str(item.get("case_id", "")) for item in review.get("cases", [])]
    if len(case_ids) != review.get("case_count") or len(case_ids) != len(set(case_ids)) or any(not value.startswith("anon-") for value in case_ids):
        raise PipelineError("Casos da revisao v10 invalidos.")
    return case_ids, review


def _gallery_page(records: list[dict[str, Any]]) -> str:
    sections = []
    for case_number, record in enumerate(records, 1):
        candidates = []
        for candidate in record["gallery_candidates"]:
            figures = "".join(
                f'<figure><img loading="lazy" src="{html.escape(frame["relative_path"])}">'
                f'<figcaption>{html.escape(frame["caption"])}</figcaption></figure>'
                for frame in candidate["preview_frames"]
            )
            candidates.append(
                f'<article><h3>Candidato {candidate["candidate_number"]}/{record["candidate_stack_count"]}</h3>'
                f'<p>{html.escape(candidate["description"])}</p><div class="grid">{figures}</div></article>'
            )
        sections.append(f'<section><h2>{case_number}. {html.escape(record["case_id"])}</h2>{"".join(candidates)}</section>')
    return (
        '<!doctype html><html><head><meta charset="utf-8"><title>ARGOS v16 candidate volumes</title>'
        '<style>body{background:#091019;color:#e8edf2;font:15px system-ui;margin:24px}section{border-top:1px solid #334155;padding:18px 0}'
        'article{background:#111827;margin:12px 0;padding:12px}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:10px}'
        'figure{margin:0}img{width:100%;height:auto}figcaption{color:#aeb8c5;margin-top:4px}</style></head><body>'
        '<h1>ARGOS v16 — revisão técnica dos stacks focais</h1><p>Avaliar enquadramento do fígado/candidato, continuidade entre cortes, correspondência entre sequências, contraste e ausência de PHI. '
        'As imagens enviadas ao modelo não contêm contorno, texto, máscara de lesão do dataset ou pixels sintéticos.</p>'
        + "".join(sections)
        + "</body></html>"
    )


def build_candidate_volume_pilot(
    *,
    review_path: Path,
    localizer_run: Path,
    input_manifest: Path,
    input_root: Path,
    registration_root: Path,
    output_root: Path,
    expected_source_case_count: int = 88,
    roi_mm: float = ROI_MM,
    output_side: int = OUTPUT_SIDE,
    max_input_bytes: int = 8_000_000,
    minimum_candidates: int = MIN_BASE_CANDIDATES,
    maximum_candidates: int = MAX_CANDIDATES,
    candidate_target_fraction: float = TARGET_CANDIDATE_COVERAGE,
) -> dict[str, Any]:
    """Build the approved 10-case technical pilot without reading any label."""

    case_ids, review = _review_case_ids(Path(review_path))
    localizer_run = Path(localizer_run).resolve()
    localizer_summary = _load(localizer_run / "summary.json")
    if (
        not _valid_localizer_run_schema(localizer_summary)
        or localizer_summary.get("status") != "complete_scores_only_no_decision"
        or localizer_summary.get("ground_truth_read") is not False
        or localizer_summary.get("ground_truth_lesion_mask_used") is not False
        or localizer_summary.get("final_decision") is not None
        or any(case_id not in localizer_summary.get("case_ids", []) for case_id in case_ids)
    ):
        raise PipelineError("Run cego do localizador invalido para piloto v16.")
    morphology = _input_index(input_manifest, input_root)
    dynamic = _original_dynamic_inputs(input_manifest, input_root)
    if len(morphology) != expected_source_case_count or set(morphology) != set(dynamic):
        raise PipelineError("Coorte fonte v16 inesperada ou inconsistente.")
    destination = Path(output_root).resolve()
    if destination.exists():
        raise PipelineError("Destino v16 ja existe; sobrescrita recusada.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = destination.parent / f"._v16candidate_{uuid.uuid4().hex[:8]}"
    staging.mkdir()
    records = []
    try:
        for case_id in case_ids:
            case_dir = staging / case_id
            case_manifest = build_candidate_volume_case(
                case_id=case_id,
                morphology_source=morphology[case_id],
                dynamic_source=dynamic[case_id],
                registered_source=_registered_or_none(case_id, registration_root),
                localizer_dir=localizer_run / case_id,
                destination=case_dir,
                roi_mm=roi_mm,
                output_side=output_side,
                max_input_bytes=max_input_bytes,
                minimum_candidates=minimum_candidates,
                maximum_candidates=maximum_candidates,
                candidate_target_fraction=candidate_target_fraction,
            )
            gallery_candidates = []
            for stack in case_manifest["candidate_stacks"]:
                candidate_dir = case_dir / stack["relative_directory"]
                candidate_manifest = _load(candidate_dir / "manifest.json")
                preview = []
                for group in candidate_manifest["groups"]:
                    positions = preview_frame_indices(len(group["frames"]))
                    labels = {positions[0]: "inicio", positions[-1]: "fim"}
                    labels[positions[len(positions) // 2]] = "centro"
                    for position in positions:
                        frame = group["frames"][position]
                        preview.append(
                            {
                                "relative_path": f'{case_id}/{stack["relative_directory"]}/{frame["filename"]}',
                                "caption": f'{group["role"]} — {labels[position]} do grupo — z={frame["source_index_z"]}',
                            }
                        )

                gallery_candidates.append(
                    {
                        "candidate_number": stack["candidate_number"],
                        "description": "fallback no centro hepatico" if stack["fallback_no_candidate"] else f'rank {stack["component_rank"]}, {stack["component_voxels"]} voxels',
                        "preview_frames": preview,
                    }
                )
            records.append(
                {
                    "case_id": case_id,
                    "candidate_stack_count": case_manifest["candidate_stack_count"],
                    "case_manifest_sha256": _sha256(case_dir / "case_manifest.json"),
                    "gallery_candidates": gallery_candidates,
                }
            )
        (staging / "index.html").write_text(_gallery_page(records), encoding="utf-8")
        cohort = {
            "schema": COHORT_SCHEMA,
            "contract": CONTRACT,
            "case_count": len(records),
            "candidate_stack_count": sum(item["candidate_stack_count"] for item in records),
            "cases": records,
            "source_review_sha256": _sha256(Path(review_path).resolve()),
            "source_review_signature": review.get("review_signature"),
            "source_localizer_summary_sha256": _sha256(localizer_run / "summary.json"),
            "input_manifest_sha256": _sha256(Path(input_manifest).resolve()),
            "protocol": {
                "roi_mm": roi_mm,
                "output_side": output_side,
                "groups": [{"role": role, "category": category, "frame_count": count} for role, category, count in GROUPS],
                "candidate_target_fraction": candidate_target_fraction,
                "minimum_base_candidates": minimum_candidates,
                "maximum_candidates": maximum_candidates,
            },
            "gallery_signature": _canonical(records),
            "inference_executed": False,
            "ground_truth_read": False,
            "dataset_lesion_mask_used": False,
            "holdout_opened": False,
            "research_only": True,
            "clinical_use_allowed": False,
            "requires_human_review": True,
        }
        _write_json_atomic(staging / "cohort_manifest.json", cohort)
        _publish_directory(staging, destination)
        return cohort
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
