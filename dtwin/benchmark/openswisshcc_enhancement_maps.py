"""Blind deterministic multiphase enhancement features for OpenSwissHCC v22.

The builder accepts only source MR phases, automatic liver masks and the
previously validated arterial/delayed registrations.  Dataset lesion masks,
labels and clinical metadata are deliberately outside this interface.
"""
from __future__ import annotations

import json
import math
import shutil
import uuid
from pathlib import Path
from typing import Any

import numpy as np
import SimpleITK as sitk
from scipy import ndimage

from dtwin.benchmark.openswisshcc_alignment import _publish_directory, _sha256
from dtwin.core import PipelineError
from dtwin.medgemma_screening import _write_json_atomic

CASE_SCHEMA = "argos-openswisshcc-enhancement-features-case-v22"
COHORT_SCHEMA = "argos-openswisshcc-enhancement-features-cohort-v22"
ALGORITHM_VERSION = "robust-liver-zscore-dynamic-v1"
INPUT_SCHEMA = "argos-public-liver-mri-input-v1"
ALIGNMENT_SCHEMA = "argos-public-liver-mri-alignment-v1"
SELECTION_SCHEMA = "argos-openswisshcc-candidate-volume-cohort-v16"
FORBIDDEN_INPUT_TERMS = ("lesion", "manual", "ground_truth", "label", "truth")
MIN_ANALYSIS_VOXELS = 300
JOINT_COMPONENT_THRESHOLD = 3.0
MIN_COMPONENT_VOXELS = 8


def _load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PipelineError(f"JSON v22 invalido: {path}") from exc
    if not isinstance(value, dict):
        raise PipelineError("JSON v22 deve ser objeto.")
    return value


def _jsonl(path: Path) -> list[dict[str, Any]]:
    try:
        rows = [
            json.loads(line)
            for line in Path(path).read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    except (OSError, json.JSONDecodeError) as exc:
        raise PipelineError(f"JSONL v22 invalido: {path}") from exc
    if not rows or any(not isinstance(row, dict) for row in rows):
        raise PipelineError("JSONL v22 vazio ou invalido.")
    return rows


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex[:8]}.tmp")
    try:
        temporary.write_text(
            "".join(
                json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n"
                for row in rows
            ),
            encoding="utf-8",
        )
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def _geometry_equal(left: sitk.Image, right: sitk.Image) -> bool:
    return (
        left.GetSize() == right.GetSize()
        and np.allclose(left.GetSpacing(), right.GetSpacing(), rtol=0, atol=1e-5)
        and np.allclose(left.GetOrigin(), right.GetOrigin(), rtol=0, atol=1e-4)
        and np.allclose(left.GetDirection(), right.GetDirection(), rtol=0, atol=1e-6)
    )


def _robust_zscore(
    array: np.ndarray, mask: np.ndarray, *, phase: str
) -> tuple[np.ndarray, dict[str, float]]:
    values = np.asarray(array[mask], dtype=np.float64)
    values = values[np.isfinite(values)]
    if values.size < MIN_ANALYSIS_VOXELS:
        raise PipelineError(f"Fase {phase} sem voxels hepaticos suficientes no v22.")
    median = float(np.median(values))
    mad = float(np.median(np.abs(values - median)))
    q25, q75 = (float(value) for value in np.percentile(values, [25.0, 75.0]))
    mad_scale = 1.4826 * mad
    iqr_scale = (q75 - q25) / 1.349
    scale = mad_scale if mad_scale > 1e-6 else iqr_scale
    if not math.isfinite(scale) or scale <= 1e-6:
        raise PipelineError(f"Fase {phase} sem variacao robusta suficiente no v22.")
    zscore = np.clip((np.asarray(array, dtype=np.float32) - median) / scale, -8.0, 8.0)
    if not np.isfinite(zscore[mask]).all():
        raise PipelineError(f"Fase {phase} gerou z-score nao finito no v22.")
    return zscore, {
        "median": median,
        "mad": mad,
        "q25": q25,
        "q75": q75,
        "scale": float(scale),
    }


def _quantile_features(prefix: str, values: np.ndarray) -> dict[str, float]:
    q90, q95, q99 = (float(value) for value in np.percentile(values, [90, 95, 99]))
    top_count = max(1, int(math.ceil(values.size * 0.01)))
    top = np.partition(values, values.size - top_count)[-top_count:]
    return {
        f"{prefix}_q90": q90,
        f"{prefix}_q95": q95,
        f"{prefix}_q99": q99,
        f"{prefix}_top1pct_mean": float(np.mean(top)),
        f"{prefix}_maximum": float(np.max(values)),
    }


def _compute_enhancement_state(
    *,
    arterial: sitk.Image,
    venous: sitk.Image,
    delayed: sitk.Image,
    liver_mask: sitk.Image,
) -> dict[str, Any]:
    """Build normalized label-free dynamic maps in venous geometry."""

    if not all(
        _geometry_equal(venous, image)
        for image in (arterial, delayed, liver_mask)
    ):
        raise PipelineError("Geometrias multifasicas v22 divergentes.")
    art = np.asarray(sitk.GetArrayFromImage(arterial), dtype=np.float32)
    ven = np.asarray(sitk.GetArrayFromImage(venous), dtype=np.float32)
    dele = np.asarray(sitk.GetArrayFromImage(delayed), dtype=np.float32)
    liver = np.asarray(sitk.GetArrayFromImage(liver_mask)) > 0
    valid = (
        liver
        & np.isfinite(art)
        & np.isfinite(ven)
        & np.isfinite(dele)
        & (art != 0)
        & (ven != 0)
        & (dele != 0)
    )
    if int(valid.sum()) < MIN_ANALYSIS_VOXELS:
        raise PipelineError("Mascara hepatica multifasica v22 vazia ou insuficiente.")
    eroded = ndimage.binary_erosion(
        valid, structure=ndimage.generate_binary_structure(3, 1), iterations=1
    )
    analysis_mask = eroded if int(eroded.sum()) >= MIN_ANALYSIS_VOXELS else valid
    z_art, art_stats = _robust_zscore(art, analysis_mask, phase="arterial")
    z_ven, ven_stats = _robust_zscore(ven, analysis_mask, phase="venous")
    z_del, del_stats = _robust_zscore(dele, analysis_mask, phase="delayed")

    arterial_relative = z_art
    arterial_over_venous = z_art - z_ven
    arterial_over_delayed = z_art - z_del
    venous_over_delayed = z_ven - z_del
    joint = (
        np.maximum(arterial_relative, 0.0)
        + np.maximum(arterial_over_delayed, 0.0)
        + 0.5 * np.maximum(arterial_over_venous, 0.0)
        + 0.25 * np.maximum(venous_over_delayed, 0.0)
    )
    joint = np.where(analysis_mask, joint, 0.0).astype(np.float32)

    return {
        "analysis_mask": analysis_mask,
        "liver_mask": liver,
        "valid_mask": valid,
        "arterial_relative": arterial_relative,
        "arterial_over_venous": arterial_over_venous,
        "arterial_over_delayed": arterial_over_delayed,
        "venous_over_delayed": venous_over_delayed,
        "joint_enhancement": joint,
        "analysis_mask_voxels": int(analysis_mask.sum()),
        "liver_mask_voxels": int(liver.sum()),
        "valid_multiphase_voxels": int(valid.sum()),
        "erosion_used": bool(analysis_mask is eroded),
        "normalization": {
            "arterial": art_stats,
            "venous": ven_stats,
            "delayed": del_stats,
        },
    }


def compute_enhancement_features(
    *,
    arterial: sitk.Image,
    venous: sitk.Image,
    delayed: sitk.Image,
    liver_mask: sitk.Image,
) -> dict[str, Any]:
    """Calculate label-free dynamic enhancement features in venous geometry."""

    state = _compute_enhancement_state(
        arterial=arterial,
        venous=venous,
        delayed=delayed,
        liver_mask=liver_mask,
    )
    analysis_mask = state["analysis_mask"]
    arterial_relative = state["arterial_relative"]
    arterial_over_venous = state["arterial_over_venous"]
    arterial_over_delayed = state["arterial_over_delayed"]
    venous_over_delayed = state["venous_over_delayed"]
    joint = state["joint_enhancement"]

    features: dict[str, float | int | list[float] | None] = {}
    for name, array in (
        ("arterial_relative", arterial_relative),
        ("arterial_over_venous", arterial_over_venous),
        ("arterial_over_delayed", arterial_over_delayed),
        ("venous_over_delayed", venous_over_delayed),
        ("joint_enhancement", joint),
    ):
        features.update(_quantile_features(name, np.asarray(array[analysis_mask])))
    joint_values = joint[analysis_mask]
    for threshold in (1.0, 2.0, 3.0, 4.0):
        key = str(threshold).replace(".", "_")
        features[f"joint_fraction_ge_{key}"] = float(np.mean(joint_values >= threshold))

    candidate = analysis_mask & (joint >= JOINT_COMPONENT_THRESHOLD)
    labels, count = ndimage.label(
        candidate, structure=ndimage.generate_binary_structure(3, 2)
    )
    components: list[tuple[int, int, np.ndarray]] = []
    for component_id in range(1, int(count) + 1):
        indices = np.argwhere(labels == component_id)
        if indices.shape[0] >= MIN_COMPONENT_VOXELS:
            components.append((int(indices.shape[0]), component_id, indices))
    components.sort(key=lambda item: (-item[0], item[1]))
    voxel_volume = float(np.prod(venous.GetSpacing()))
    features["component_count_ge_3"] = len(components)
    features["component_voxels_ge_3"] = int(sum(item[0] for item in components))
    features["largest_component_voxels_ge_3"] = components[0][0] if components else 0
    features["largest_component_mm3_ge_3"] = (
        float(components[0][0] * voxel_volume) if components else 0.0
    )
    if components:
        center_zyx = components[0][2].mean(axis=0)
        center_xyz = tuple(float(value) for value in center_zyx[::-1])
        physical = venous.TransformContinuousIndexToPhysicalPoint(center_xyz)
        features["largest_component_center_lps_xyz"] = [float(value) for value in physical]
    else:
        features["largest_component_center_lps_xyz"] = None

    if any(
        isinstance(value, float) and not math.isfinite(value)
        for value in features.values()
    ):
        raise PipelineError("Feature multifasica v22 nao finita.")
    return {
        "algorithm_version": ALGORITHM_VERSION,
        "analysis_mask_voxels": state["analysis_mask_voxels"],
        "liver_mask_voxels": state["liver_mask_voxels"],
        "valid_multiphase_voxels": state["valid_multiphase_voxels"],
        "erosion_used": state["erosion_used"],
        "normalization": state["normalization"],
        "features": features,
    }


def _safe_path(root: Path, item: dict[str, Any]) -> Path:
    relative = str(item.get("relative_path", ""))
    serialized = (str(item.get("role", "")) + " " + relative).lower()
    if any(term in serialized for term in FORBIDDEN_INPUT_TERMS):
        raise PipelineError("Input proibido no extrator multifasico v22.")
    path = (root / relative).resolve()
    if (
        not path.is_relative_to(root)
        or not path.is_file()
        or path.stat().st_size != int(item.get("bytes", -1))
        or _sha256(path) != item.get("sha256")
    ):
        raise PipelineError("Input multifasico v22 mudou ou saiu da raiz.")
    return path


def _input_index(manifest_path: Path, input_root: Path) -> dict[str, dict[str, Any]]:
    root = Path(input_root).resolve()
    indexed: dict[str, dict[str, Any]] = {}
    required = ("t1_venous", "liver_mask_venous")
    for row in _jsonl(manifest_path):
        case_id = str(row.get("case_id", ""))
        if (
            row.get("schema") != INPUT_SCHEMA
            or not case_id.startswith("anon-")
            or case_id in indexed
            or row.get("research_only") is not True
            or row.get("clinical_use_allowed") is not False
        ):
            raise PipelineError("Registro de input v22 inseguro.")
        files = row.get("files")
        if not isinstance(files, list):
            raise PipelineError("Lista de arquivos v22 invalida.")
        by_role = {str(item.get("role", "")): item for item in files}
        if any(role not in by_role for role in required):
            raise PipelineError("Fase venosa ou mascara hepatica ausente no v22.")
        indexed[case_id] = {
            "paths": {role: _safe_path(root, by_role[role]) for role in required},
            "hashes": {role: str(by_role[role]["sha256"]) for role in required},
        }
    return indexed


def _selection(path: Path) -> tuple[list[str], dict[str, str]]:
    value = _load(path)
    cases = value.get("cases")
    if (
        value.get("schema") != SELECTION_SCHEMA
        or value.get("case_count") != 87
        or not isinstance(cases, list)
        or len(cases) != 87
    ):
        raise PipelineError("Selecao full87 invalida para features v22.")
    case_ids: list[str] = []
    modes: dict[str, str] = {}
    for item in cases:
        case_id = str(item.get("case_id", ""))
        mode = str(item.get("dynamic_alignment_mode", ""))
        if not case_id.startswith("anon-") or case_id in modes or mode not in {
            "registered_to_venous",
            "original_unregistered_physical_center",
        }:
            raise PipelineError("Caso ou modo full87 invalido no v22.")
        case_ids.append(case_id)
        modes[case_id] = mode
    return case_ids, modes


def _registered_paths(case_id: str, alignment_root: Path) -> tuple[Path, Path, dict[str, str]]:
    case_root = Path(alignment_root).resolve() / case_id
    manifest_path = case_root / "alignment_manifest.json"
    manifest = _load(manifest_path)
    if (
        manifest.get("schema") != ALIGNMENT_SCHEMA
        or manifest.get("case_id") != case_id
        or manifest.get("reference_phase") != "venous"
        or manifest.get("research_only") is not True
        or manifest.get("clinical_use_allowed") is not False
    ):
        raise PipelineError("Manifesto de alinhamento v22 invalido.")
    outputs = {str(item.get("phase")): item for item in manifest.get("outputs", [])}
    if set(outputs) != {"art", "del"}:
        raise PipelineError("Fases registradas v22 incompletas.")
    paths: dict[str, Path] = {}
    hashes: dict[str, str] = {}
    for phase in ("art", "del"):
        item = outputs[phase]
        path = (case_root / str(item.get("filename", ""))).resolve()
        if (
            not path.is_relative_to(case_root.resolve())
            or not path.is_file()
            or path.stat().st_size != int(item.get("bytes", -1))
            or _sha256(path) != item.get("sha256")
        ):
            raise PipelineError("Volume registrado v22 mudou ou saiu da raiz.")
        paths[phase] = path
        hashes[phase] = str(item["sha256"])
    hashes["alignment_manifest"] = _sha256(manifest_path)
    return paths["art"], paths["del"], hashes


def build_enhancement_feature_cohort(
    *,
    input_manifest_path: Path,
    input_root: Path,
    alignment_root: Path,
    selection_manifest_path: Path,
    output_dir: Path,
) -> dict[str, Any]:
    """Publish label-free features for all 87 cases, marking 3 fallbacks unavailable."""

    case_ids, modes = _selection(selection_manifest_path)
    inputs = _input_index(input_manifest_path, input_root)
    if any(case_id not in inputs for case_id in case_ids):
        raise PipelineError("Selecao v22 contem caso ausente nos inputs.")
    output_dir = Path(output_dir).resolve()
    if output_dir.exists():
        raise PipelineError("Destino de features v22 ja existe.")
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    staging = output_dir.parent / f"._v22enh_{uuid.uuid4().hex[:8]}"
    staging.mkdir()
    rows: list[dict[str, Any]] = []
    try:
        for case_id in case_ids:
            mode = modes[case_id]
            base: dict[str, Any] = {
                "schema": CASE_SCHEMA,
                "case_id": case_id,
                "algorithm_version": ALGORITHM_VERSION,
                "dynamic_alignment_mode": mode,
                "ground_truth_read": False,
                "ground_truth_lesion_mask_used": False,
                "research_only": True,
                "clinical_use_allowed": False,
                "requires_human_review": True,
            }
            if mode != "registered_to_venous":
                rows.append(
                    {
                        **base,
                        "status": "unavailable_unregistered_fallback",
                        "features": None,
                        "source_hashes": inputs[case_id]["hashes"],
                    }
                )
                continue
            arterial_path, delayed_path, registered_hashes = _registered_paths(
                case_id, alignment_root
            )
            source = inputs[case_id]
            result = compute_enhancement_features(
                arterial=sitk.ReadImage(str(arterial_path)),
                venous=sitk.ReadImage(str(source["paths"]["t1_venous"])),
                delayed=sitk.ReadImage(str(delayed_path)),
                liver_mask=sitk.ReadImage(str(source["paths"]["liver_mask_venous"])),
            )
            rows.append(
                {
                    **base,
                        "status": "complete_blind_features",
                    **result,
                    "source_hashes": {**source["hashes"], **registered_hashes},
                }
            )
        features_path = staging / "features.jsonl"
        _write_jsonl(features_path, rows)
        available = sum(row["status"] == "complete_blind_features" for row in rows)
        unavailable = [
            row["case_id"]
            for row in rows
            if row["status"] != "complete_blind_features"
        ]
        summary: dict[str, Any] = {
            "schema": COHORT_SCHEMA,
            "status": "complete_blind_features_with_declared_fallbacks",
            "algorithm_version": ALGORITHM_VERSION,
            "case_count": len(rows),
            "available_case_count": available,
            "unavailable_case_count": len(unavailable),
            "unavailable_case_ids": unavailable,
            "case_ids": case_ids,
            "features_sha256": _sha256(features_path),
            "input_manifest_sha256": _sha256(Path(input_manifest_path).resolve()),
            "selection_manifest_sha256": _sha256(Path(selection_manifest_path).resolve()),
            "alignment_root": str(Path(alignment_root).resolve()),
            "labels_read": False,
            "ground_truth_lesion_masks_read": 0,
            "inference_executed": False,
            "research_only": True,
            "clinical_use_allowed": False,
            "requires_human_review": True,
        }
        _write_json_atomic(staging / "summary.json", summary)
        _publish_directory(staging, output_dir)
        return summary
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise


__all__ = [
    "ALGORITHM_VERSION",
    "CASE_SCHEMA",
    "COHORT_SCHEMA",
    "build_enhancement_feature_cohort",
    "compute_enhancement_features",
]
