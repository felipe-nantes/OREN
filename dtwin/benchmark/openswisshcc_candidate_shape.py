"""Blind geometric features for deterministic OpenSwissHCC candidates.

This module deliberately receives only automatic candidate masks and source
geometry. Public labels and lesion masks are not part of its API.
"""
from __future__ import annotations

import math
import shutil
import sys
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np
import SimpleITK as sitk
from scipy import ndimage

from dtwin.benchmark.openswisshcc_alignment import _publish_directory, _sha256
from dtwin.benchmark.openswisshcc_candidate_volume import (
    _valid_localizer_run_schema,
    _validate_localizer,
)
from dtwin.benchmark.openswisshcc_enhancement_maps import (
    _input_index,
    _load,
    _selection,
    _write_jsonl,
)
from dtwin.core import PipelineError
from dtwin.medgemma_screening import _write_json_atomic

ALGORITHM_VERSION = "candidate-physical-shape-v1"
CASE_SCHEMA = "argos-openswisshcc-candidate-shape-case-v23"
COHORT_SCHEMA = "argos-openswisshcc-candidate-shape-cohort-v23"
CONNECTIVITY = 3


def _empty_features() -> dict[str, float | int]:
    return {
        "candidate_present": 0,
        "candidate_component_count": 0,
        "candidate_total_voxels": 0,
        "candidate_largest_fraction": 0.0,
        "candidate_largest_linearity": 0.0,
        "candidate_max_linearity": 0.0,
        "candidate_weighted_linearity": 0.0,
        "candidate_largest_planarity": 0.0,
        "candidate_weighted_planarity": 0.0,
        "candidate_largest_sphericity_proxy": 0.0,
        "candidate_weighted_sphericity_proxy": 0.0,
        "candidate_largest_axis_ratio": 0.0,
        "candidate_weighted_axis_ratio": 0.0,
        "candidate_largest_bbox_fill": 0.0,
        "candidate_weighted_bbox_fill": 0.0,
    }


def _component_shape(points_zyx: np.ndarray, spacing_zyx: np.ndarray) -> dict[str, float | int]:
    count = int(points_zyx.shape[0])
    if count < 4:
        raise PipelineError("Componente candidato v23 pequeno demais para geometria 3D.")
    physical = points_zyx.astype(np.float64, copy=False) * spacing_zyx
    covariance = np.cov(physical, rowvar=False)
    eigenvalues = np.sort(np.maximum(np.linalg.eigvalsh(covariance), 1e-9))[::-1]
    major, middle, minor = (float(value) for value in eigenvalues)
    bbox_voxels = int(np.prod(np.ptp(points_zyx, axis=0) + 1))
    return {
        "voxels": count,
        "linearity": float(1.0 - middle / major),
        "planarity": float((middle - minor) / major),
        "sphericity_proxy": float(minor / major),
        "axis_ratio": float(math.sqrt(major / minor)),
        "bbox_fill": float(count / bbox_voxels),
    }


def compute_candidate_shape_features(candidate_mask: sitk.Image) -> dict[str, Any]:
    """Describe compact versus tubular shape in physical space."""

    array = np.asarray(sitk.GetArrayFromImage(candidate_mask)) > 0
    features = _empty_features()
    if not array.any():
        return {
            "algorithm_version": ALGORITHM_VERSION,
            "features": features,
        }
    labels, component_count = ndimage.label(
        array,
        structure=ndimage.generate_binary_structure(3, CONNECTIVITY),
    )
    spacing_zyx = np.asarray(candidate_mask.GetSpacing()[::-1], dtype=np.float64)
    if spacing_zyx.shape != (3,) or not np.isfinite(spacing_zyx).all() or np.any(spacing_zyx <= 0):
        raise PipelineError("Espacamento candidato v23 invalido.")
    components = [
        _component_shape(np.argwhere(labels == component_id), spacing_zyx)
        for component_id in range(1, int(component_count) + 1)
    ]
    components.sort(key=lambda item: int(item["voxels"]), reverse=True)
    total = int(sum(int(item["voxels"]) for item in components))
    largest = components[0]

    def weighted(name: str) -> float:
        return float(
            sum(int(item["voxels"]) * float(item[name]) for item in components) / total
        )

    features.update(
        {
            "candidate_present": 1,
            "candidate_component_count": int(component_count),
            "candidate_total_voxels": total,
            "candidate_largest_fraction": float(int(largest["voxels"]) / total),
            "candidate_largest_linearity": float(largest["linearity"]),
            "candidate_max_linearity": float(max(float(item["linearity"]) for item in components)),
            "candidate_weighted_linearity": weighted("linearity"),
            "candidate_largest_planarity": float(largest["planarity"]),
            "candidate_weighted_planarity": weighted("planarity"),
            "candidate_largest_sphericity_proxy": float(largest["sphericity_proxy"]),
            "candidate_weighted_sphericity_proxy": weighted("sphericity_proxy"),
            "candidate_largest_axis_ratio": float(largest["axis_ratio"]),
            "candidate_weighted_axis_ratio": weighted("axis_ratio"),
            "candidate_largest_bbox_fill": float(largest["bbox_fill"]),
            "candidate_weighted_bbox_fill": weighted("bbox_fill"),
        }
    )
    if any(not math.isfinite(float(value)) for value in features.values()):
        raise PipelineError("Feature geometrica v23 nao finita.")
    return {
        "algorithm_version": ALGORITHM_VERSION,
        "features": features,
    }


def build_candidate_shape_cohort(
    *,
    input_manifest_path: Path,
    input_root: Path,
    selection_manifest_path: Path,
    localizer_root: Path,
    output_dir: Path,
    progress: Callable[[int, int, str], None] | None = None,
) -> dict[str, Any]:
    """Publish label-blind shape features in the frozen development order."""

    case_ids, _ = _selection(selection_manifest_path)
    inputs = _input_index(input_manifest_path, input_root)
    localizer_root = Path(localizer_root).resolve()
    summary_path = localizer_root / "summary.json"
    localizer_summary = _load(summary_path)
    if (
        not _valid_localizer_run_schema(localizer_summary)
        or localizer_summary.get("status") != "complete_scores_only_no_decision"
        or localizer_summary.get("ground_truth_read") is not False
        or localizer_summary.get("ground_truth_lesion_mask_used") is not False
        or localizer_summary.get("final_decision") is not None
        or any(case_id not in localizer_summary.get("case_ids", []) for case_id in case_ids)
        or any(case_id not in inputs for case_id in case_ids)
    ):
        raise PipelineError("Entrada cega do extrator geometrico v23 invalida.")

    output_dir = Path(output_dir).resolve()
    if output_dir.exists():
        raise PipelineError("Destino geometrico v23 ja existe.")
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    staging = output_dir.parent / f"._v23shape_{uuid.uuid4().hex[:8]}"
    staging.mkdir()
    rows: list[dict[str, Any]] = []
    try:
        for index, case_id in enumerate(case_ids, 1):
            if progress:
                progress(index, len(case_ids), case_id)
            source = inputs[case_id]
            venous = sitk.ReadImage(str(source["paths"]["t1_venous"]))
            manifest, manifest_path, candidate_path, _, _, _ = _validate_localizer(
                case_id, localizer_root / case_id, venous
            )
            if manifest.get("candidate_mask_is_deterministic_enhancement") is not True:
                raise PipelineError("Extrator v23 exige candidato deterministico de realce.")
            result = compute_candidate_shape_features(sitk.ReadImage(str(candidate_path)))
            rows.append(
                {
                    "schema": CASE_SCHEMA,
                    "case_id": case_id,
                    "status": "complete_blind_shape_features",
                    **result,
                    "source_hashes": {
                        "localizer_manifest": _sha256(manifest_path),
                        "candidate_mask": _sha256(candidate_path),
                    },
                    "ground_truth_read": False,
                    "ground_truth_lesion_mask_used": False,
                    "inference_executed": False,
                    "research_only": True,
                    "clinical_use_allowed": False,
                    "requires_human_review": True,
                }
            )
        features_path = staging / "features.jsonl"
        _write_jsonl(features_path, rows)
        empty_ids = [
            row["case_id"] for row in rows if row["features"]["candidate_present"] == 0
        ]
        summary = {
            "schema": COHORT_SCHEMA,
            "status": "complete_blind_shape_features",
            "algorithm_version": ALGORITHM_VERSION,
            "case_count": len(rows),
            "case_ids": case_ids,
            "empty_candidate_count": len(empty_ids),
            "empty_candidate_ids": empty_ids,
            "features_sha256": _sha256(features_path),
            "input_manifest_sha256": _sha256(Path(input_manifest_path).resolve()),
            "selection_manifest_sha256": _sha256(Path(selection_manifest_path).resolve()),
            "source_localizer_summary_sha256": _sha256(summary_path),
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


def _stderr_progress(index: int, total: int, case_id: str) -> None:
    print(f"[v23-geometria] {index:02d}/{total}: {case_id}", file=sys.stderr, flush=True)


__all__ = [
    "ALGORITHM_VERSION",
    "CASE_SCHEMA",
    "COHORT_SCHEMA",
    "build_candidate_shape_cohort",
    "compute_candidate_shape_features",
    "_stderr_progress",
]
