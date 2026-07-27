"""Recompute and time v23 shape features without labels."""
from __future__ import annotations

import json
import math
import statistics
import time
from pathlib import Path
from typing import Any, Callable

import SimpleITK as sitk

from dtwin.benchmark.openswisshcc_alignment import _sha256
from dtwin.benchmark.openswisshcc_candidate_shape import (
    ALGORITHM_VERSION,
    CASE_SCHEMA,
    COHORT_SCHEMA,
    compute_candidate_shape_features,
)
from dtwin.core import PipelineError
from dtwin.medgemma_screening import _write_json_atomic


TIMING_SCHEMA = "argos-openswisshcc-candidate-shape-timing-v23"
V20_CONSERVATIVE_SECONDS = 104.4465
V22_PROPOSAL_MAX_SECONDS = 2.8262


def _percentile_higher(values: list[float], percentile: float) -> float:
    ordered = sorted(values)
    index = max(0, math.ceil(percentile * len(ordered)) - 1)
    return float(ordered[index])


def measure_candidate_shape_timing(
    *,
    shape_root: Path,
    localizer_root: Path,
    output_path: Path,
    clock: Callable[[], float] = time.perf_counter,
) -> dict[str, Any]:
    shape_root = Path(shape_root).resolve()
    localizer_root = Path(localizer_root).resolve()
    summary_path = shape_root / "summary.json"
    features_path = shape_root / "features.jsonl"
    try:
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        rows = [json.loads(line) for line in features_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    except (OSError, json.JSONDecodeError) as exc:
        raise PipelineError("Bundle geometrico v23 invalido para timing.") from exc
    if (
        summary.get("schema") != COHORT_SCHEMA
        or summary.get("status") != "complete_blind_shape_features"
        or summary.get("algorithm_version") != ALGORITHM_VERSION
        or summary.get("features_sha256") != _sha256(features_path)
        or summary.get("case_count") != len(rows)
        or summary.get("case_ids") != [row.get("case_id") for row in rows]
        or summary.get("labels_read") is not False
        or summary.get("ground_truth_lesion_masks_read") != 0
    ):
        raise PipelineError("Bundle geometrico v23 divergiu no timing.")
    timings: list[dict[str, Any]] = []
    for row in rows:
        case_id = str(row.get("case_id", ""))
        candidate_path = localizer_root / case_id / "liver_lesion_candidates_in_liver.nii.gz"
        if (
            row.get("schema") != CASE_SCHEMA
            or not candidate_path.is_file()
            or row.get("source_hashes", {}).get("candidate_mask") != _sha256(candidate_path)
        ):
            raise PipelineError(f"Fonte geometrica v23 divergente no timing: {case_id}.")
        started = clock()
        recomputed = compute_candidate_shape_features(sitk.ReadImage(str(candidate_path)))
        elapsed = float(clock() - started)
        if elapsed < 0 or not math.isfinite(elapsed) or recomputed.get("features") != row.get("features"):
            raise PipelineError(f"Recomputacao geometrica v23 divergiu: {case_id}.")
        timings.append({"case_id": case_id, "elapsed_seconds": elapsed})
    values = [item["elapsed_seconds"] for item in timings]
    maximum = max(values)
    conservative_precomputed = V20_CONSERVATIVE_SECONDS + V22_PROPOSAL_MAX_SECONDS + maximum
    result = {
        "schema": TIMING_SCHEMA,
        "status": "candidate_shape_timing_complete",
        "case_count": len(rows),
        "timing_scope": "candidate_nifti_read_plus_shape_extraction_only",
        "per_case": timings,
        "seconds": {
            "minimum": min(values),
            "mean": statistics.mean(values),
            "median": statistics.median(values),
            "p95_higher": _percentile_higher(values, 0.95),
            "maximum": maximum,
        },
        "conservative_precomputed_pipeline_seconds": {
            "v20_existing_bound": V20_CONSERVATIVE_SECONDS,
            "v22_proposal_generation_max": V22_PROPOSAL_MAX_SECONDS,
            "v23_shape_extraction_max": maximum,
            "sum": conservative_precomputed,
            "passed_180_seconds": conservative_precomputed <= 180.0,
            "possible_component_overlap_declared": True,
        },
        "raw_dicom_end_to_end_180_seconds_proven": False,
        "features_recomputed_exactly": True,
        "labels_read": False,
        "lesion_masks_read": False,
        "holdout_opened": False,
        "research_only": True,
        "clinical_use_allowed": False,
        "requires_human_review": True,
        "source_hashes": {
            "shape_summary": _sha256(summary_path),
            "shape_features": _sha256(features_path),
        },
    }
    output_path = Path(output_path).resolve()
    if output_path.exists():
        raise PipelineError("Timing v23 ja existe; sobrescrita recusada.")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    _write_json_atomic(output_path, result)
    return result


__all__ = ["TIMING_SCHEMA", "measure_candidate_shape_timing", "_percentile_higher"]
