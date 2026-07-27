"""Blind v22 enhancement features restricted to model-derived candidates.

Only automatic liver masks, registered MR phases and the frozen v16 localizer
output enter this builder. Public labels and dataset lesion masks are outside
the API by construction.
"""
from __future__ import annotations

import json
import math
import shutil
import sys
import uuid
from pathlib import Path
from typing import Any, Callable

import numpy as np
import SimpleITK as sitk
from scipy import ndimage

from dtwin.benchmark.openswisshcc_alignment import _publish_directory, _sha256
from dtwin.benchmark.openswisshcc_candidate_volume import (
    _valid_localizer_run_schema,
    _validate_localizer,
)
from dtwin.benchmark.openswisshcc_enhancement_maps import (
    CASE_SCHEMA,
    COHORT_SCHEMA,
    _compute_enhancement_state,
    _input_index,
    _load,
    _registered_paths,
    _selection,
    _write_jsonl,
)
from dtwin.core import PipelineError
from dtwin.medgemma_screening import _write_json_atomic


ALGORITHM_VERSION = "model-candidate-dynamic-context-5mm-v1"
CONTEXT_RADIUS_MM = 5.0
MAP_NAMES = (
    "arterial_relative",
    "arterial_over_venous",
    "arterial_over_delayed",
    "venous_over_delayed",
    "joint_enhancement",
)


def _base_features() -> dict[str, float | int]:
    features: dict[str, float | int] = {
        "candidate_present": 0,
        "candidate_component_count": 0,
        "candidate_total_voxels": 0,
        "candidate_total_mm3": 0.0,
        "candidate_largest_component_mm3": 0.0,
        "candidate_fraction_of_liver": 0.0,
        "candidate_shared_fov_voxels": 0,
        "candidate_shared_fov_fraction": 0.0,
        "context_shell_available": 0,
        "core_joint_ge_3_fraction": 0.0,
        "core_aphe_washout_fraction": 0.0,
        "context_aphe_washout_fraction": 0.0,
    }
    for name in MAP_NAMES:
        for suffix in (
            "core_mean",
            "core_q90",
            "core_q95",
            "context_q90",
            "component_max_q90",
            "core_minus_shell_mean",
        ):
            features[f"{name}_{suffix}"] = 0.0
    return features


def _percentile(values: np.ndarray, quantile: float) -> float:
    if values.size < 1 or not np.isfinite(values).all():
        raise PipelineError("Regiao candidata v22 vazia ou nao finita.")
    return float(np.percentile(values, quantile))


def compute_candidate_enhancement_features(
    *,
    arterial: sitk.Image,
    venous: sitk.Image,
    delayed: sitk.Image,
    liver_mask: sitk.Image,
    candidate_mask: sitk.Image,
) -> dict[str, Any]:
    """Measure dynamic behavior only around blind model-derived candidates."""

    state = _compute_enhancement_state(
        arterial=arterial,
        venous=venous,
        delayed=delayed,
        liver_mask=liver_mask,
    )
    if (
        candidate_mask.GetSize() != venous.GetSize()
        or not np.allclose(candidate_mask.GetSpacing(), venous.GetSpacing(), rtol=0, atol=1e-5)
        or not np.allclose(candidate_mask.GetOrigin(), venous.GetOrigin(), rtol=0, atol=1e-4)
        or not np.allclose(candidate_mask.GetDirection(), venous.GetDirection(), rtol=0, atol=1e-6)
    ):
        raise PipelineError("Geometria da mascara candidata divergiu no v22.")

    original_candidate = np.asarray(sitk.GetArrayFromImage(candidate_mask)) > 0
    if np.any(original_candidate & ~state["liver_mask"]):
        raise PipelineError("Mascara candidata v22 saiu do figado automatico.")
    core = original_candidate & state["valid_mask"]
    features = _base_features()
    if not original_candidate.any():
        return {
            "algorithm_version": ALGORITHM_VERSION,
            "context_radius_mm": CONTEXT_RADIUS_MM,
            "analysis_mask_voxels": state["analysis_mask_voxels"],
            "normalization": state["normalization"],
            "features": features,
        }

    original_labels, original_component_count = ndimage.label(
        original_candidate, structure=ndimage.generate_binary_structure(3, 3)
    )
    original_component_sizes = [
        int(np.count_nonzero(original_labels == component_id))
        for component_id in range(1, int(original_component_count) + 1)
    ]
    voxel_volume = float(np.prod(venous.GetSpacing()))
    features.update(
        {
            "candidate_present": 1,
            "candidate_component_count": int(original_component_count),
            "candidate_total_voxels": int(original_candidate.sum()),
            "candidate_total_mm3": float(original_candidate.sum() * voxel_volume),
            "candidate_largest_component_mm3": float(max(original_component_sizes) * voxel_volume),
            "candidate_fraction_of_liver": float(
                original_candidate.sum() / state["liver_mask_voxels"]
            ),
            "candidate_shared_fov_voxels": int(core.sum()),
            "candidate_shared_fov_fraction": float(core.sum() / original_candidate.sum()),
        }
    )
    if not core.any():
        return {
            "algorithm_version": ALGORITHM_VERSION,
            "context_radius_mm": CONTEXT_RADIUS_MM,
            "analysis_mask_voxels": state["analysis_mask_voxels"],
            "normalization": state["normalization"],
            "features": features,
        }

    spacing_zyx = tuple(float(value) for value in venous.GetSpacing()[::-1])
    distance = ndimage.distance_transform_edt(~core, sampling=spacing_zyx)
    context = (distance <= CONTEXT_RADIUS_MM) & state["valid_mask"]
    shell = context & ~core
    labels, component_count = ndimage.label(
        core, structure=ndimage.generate_binary_structure(3, 3)
    )
    features.update(
        {
            "context_shell_available": int(shell.any()),
        }
    )

    for name in MAP_NAMES:
        array = np.asarray(state[name], dtype=np.float32)
        core_values = array[core]
        context_values = array[context]
        shell_mean = float(np.mean(array[shell])) if shell.any() else float(np.mean(core_values))
        component_q90 = [
            _percentile(array[labels == component_id], 90.0)
            for component_id in range(1, int(component_count) + 1)
        ]
        features.update(
            {
                f"{name}_core_mean": float(np.mean(core_values)),
                f"{name}_core_q90": _percentile(core_values, 90.0),
                f"{name}_core_q95": _percentile(core_values, 95.0),
                f"{name}_context_q90": _percentile(context_values, 90.0),
                f"{name}_component_max_q90": float(max(component_q90)),
                f"{name}_core_minus_shell_mean": float(np.mean(core_values) - shell_mean),
            }
        )

    arterial_relative = state["arterial_relative"]
    arterial_over_venous = state["arterial_over_venous"]
    arterial_over_delayed = state["arterial_over_delayed"]
    pattern = (
        (arterial_relative >= 1.0)
        & (arterial_over_venous >= 0.5)
        & (arterial_over_delayed >= 1.0)
    )
    features["core_joint_ge_3_fraction"] = float(
        np.mean(state["joint_enhancement"][core] >= 3.0)
    )
    features["core_aphe_washout_fraction"] = float(np.mean(pattern[core]))
    features["context_aphe_washout_fraction"] = float(np.mean(pattern[context]))
    if any(
        not math.isfinite(float(value))
        for value in features.values()
        if isinstance(value, (int, float))
    ):
        raise PipelineError("Feature candidata multifasica v22 nao finita.")
    return {
        "algorithm_version": ALGORITHM_VERSION,
        "context_radius_mm": CONTEXT_RADIUS_MM,
        "analysis_mask_voxels": state["analysis_mask_voxels"],
        "normalization": state["normalization"],
        "features": features,
    }


def build_candidate_enhancement_cohort(
    *,
    input_manifest_path: Path,
    input_root: Path,
    alignment_root: Path,
    selection_manifest_path: Path,
    localizer_root: Path,
    output_dir: Path,
    progress: Callable[[int, int, str], None] | None = None,
) -> dict[str, Any]:
    """Publish blind candidate-restricted features for the frozen full87 order."""

    case_ids, modes = _selection(selection_manifest_path)
    inputs = _input_index(input_manifest_path, input_root)
    localizer_root = Path(localizer_root).resolve()
    localizer_summary_path = localizer_root / "summary.json"
    localizer_summary = _load(localizer_summary_path)
    if (
        not _valid_localizer_run_schema(localizer_summary)
        or localizer_summary.get("status") != "complete_scores_only_no_decision"
        or localizer_summary.get("ground_truth_read") is not False
        or localizer_summary.get("ground_truth_lesion_mask_used") is not False
        or localizer_summary.get("final_decision") is not None
        or any(case_id not in localizer_summary.get("case_ids", []) for case_id in case_ids)
    ):
        raise PipelineError("Run do localizador v22 invalido ou nao cego.")
    if any(case_id not in inputs for case_id in case_ids):
        raise PipelineError("Selecao candidata v22 contem caso ausente nos inputs.")

    output_dir = Path(output_dir).resolve()
    if output_dir.exists():
        raise PipelineError("Destino de features candidatas v22 ja existe.")
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    staging = output_dir.parent / f"._v22candidate_enh_{uuid.uuid4().hex[:8]}"
    staging.mkdir()
    rows: list[dict[str, Any]] = []
    try:
        for index, case_id in enumerate(case_ids, 1):
            if progress:
                progress(index, len(case_ids), case_id)
            mode = modes[case_id]
            base: dict[str, Any] = {
                "schema": CASE_SCHEMA,
                "case_id": case_id,
                "algorithm_version": ALGORITHM_VERSION,
                "feature_strategy": "model_candidate_restricted_dynamic_context",
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
            source = inputs[case_id]
            venous = sitk.ReadImage(str(source["paths"]["t1_venous"]))
            localizer_manifest, localizer_manifest_path, candidate_path, _, _, _ = _validate_localizer(
                case_id, localizer_root / case_id, venous
            )
            arterial_path, delayed_path, registered_hashes = _registered_paths(
                case_id, alignment_root
            )
            result = compute_candidate_enhancement_features(
                arterial=sitk.ReadImage(str(arterial_path)),
                venous=venous,
                delayed=sitk.ReadImage(str(delayed_path)),
                liver_mask=sitk.ReadImage(str(source["paths"]["liver_mask_venous"])),
                candidate_mask=sitk.ReadImage(str(candidate_path)),
            )
            rows.append(
                {
                    **base,
                    "status": "complete_blind_features",
                    "candidate_mask_is_model_derived": localizer_manifest.get(
                        "candidate_mask_is_model_derived"
                    ) is True,
                    "candidate_mask_is_deterministic_enhancement": localizer_manifest.get(
                        "candidate_mask_is_deterministic_enhancement"
                    ) is True,
                    **result,
                    "source_hashes": {
                        **source["hashes"],
                        **registered_hashes,
                        "localizer_manifest": _sha256(localizer_manifest_path),
                        "candidate_mask": _sha256(candidate_path),
                    },
                }
            )

        features_path = staging / "features.jsonl"
        _write_jsonl(features_path, rows)
        unavailable = [
            row["case_id"] for row in rows if row["status"] != "complete_blind_features"
        ]
        summary: dict[str, Any] = {
            "schema": COHORT_SCHEMA,
            "status": "complete_blind_features_with_declared_fallbacks",
            "algorithm_version": ALGORITHM_VERSION,
            "feature_strategy": "model_candidate_restricted_dynamic_context",
            "case_count": len(rows),
            "available_case_count": len(rows) - len(unavailable),
            "unavailable_case_count": len(unavailable),
            "unavailable_case_ids": unavailable,
            "case_ids": case_ids,
            "features_sha256": _sha256(features_path),
            "input_manifest_sha256": _sha256(Path(input_manifest_path).resolve()),
            "selection_manifest_sha256": _sha256(Path(selection_manifest_path).resolve()),
            "source_localizer_summary_sha256": _sha256(localizer_summary_path),
            "labels_read": False,
            "ground_truth_lesion_masks_read": 0,
            "candidate_masks_model_derived": localizer_summary.get("model_version") != "none_deterministic",
            "candidate_masks_deterministic_enhancement": localizer_summary.get("model_version") == "none_deterministic",
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


def _stderr_progress(index: int, total: int, case_id: str) -> None:
    print(f"[v22-candidato] {index:02d}/{total}: {case_id}", file=sys.stderr, flush=True)


__all__ = [
    "ALGORITHM_VERSION",
    "CONTEXT_RADIUS_MM",
    "build_candidate_enhancement_cohort",
    "compute_candidate_enhancement_features",
    "_stderr_progress",
]
