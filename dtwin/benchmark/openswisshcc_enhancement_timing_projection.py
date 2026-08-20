"""Label-free timing projection for the v22 exact-top5 4B pilot."""
from __future__ import annotations

import json
import math
import statistics
from pathlib import Path
from typing import Any

import numpy as np

from dtwin.benchmark.openswisshcc_alignment import _sha256
from dtwin.benchmark.openswisshcc_candidate_volume_score import (
    PREDICTION_SCHEMA,
    SUMMARY_SCHEMA,
)
from dtwin.benchmark.openswisshcc_enhancement_localizer import (
    ALGORITHM_VERSION as PROPOSAL_ALGORITHM,
)
from dtwin.benchmark.openswisshcc_enhancement_localizer import (
    COHORT_SCHEMA as PROPOSAL_SCHEMA,
)
from dtwin.benchmark.openswisshcc_enhancement_score_preflight import PREFLIGHT_SCHEMA
from dtwin.core import PipelineError
from dtwin.medgemma_screening import _write_json_atomic

PROJECTION_SCHEMA = "argos-openswisshcc-enhancement-top5-timing-projection-v22"
HISTORICAL_TIMING_SCHEMA = "argos-openswisshcc-candidate-volume-timing-run-v16"
CASE_TIME_GATE_SECONDS = 180.0
MAX_CANDIDATES = 5


def _load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PipelineError(f"JSON invalido na projecao temporal v22: {path}.") from exc
    if not isinstance(value, dict):
        raise PipelineError(f"Objeto JSON esperado na projecao temporal v22: {path}.")
    return value


def _refuse_holdout(*paths: Path) -> None:
    if any(
        any("holdout" in part.lower() for part in Path(path).resolve().parts)
        for path in paths
    ):
        raise PipelineError("Projecao temporal v22 recusou caminho de holdout.")


def _finite_positive(value: Any, description: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise PipelineError(f"Tempo invalido na projecao v22: {description}.") from exc
    if not math.isfinite(result) or result <= 0:
        raise PipelineError(f"Tempo invalido na projecao v22: {description}.")
    return result


def _quantile(values: list[float], q: float) -> float:
    return float(np.quantile(np.asarray(values, dtype=np.float64), q, method="higher"))


def project_enhancement_top5_timing(
    *,
    historical_score_root: Path,
    historical_timing_report_path: Path,
    proposal_summary_path: Path,
    preflight_path: Path,
    output_path: Path,
    expected_historical_case_count: int = 87,
) -> dict[str, Any]:
    """Project timing from frozen measurements; never call the model."""

    score_root = Path(historical_score_root).resolve()
    timing_path = Path(historical_timing_report_path).resolve()
    proposal_path = Path(proposal_summary_path).resolve()
    preflight_path = Path(preflight_path).resolve()
    output_path = Path(output_path).resolve()
    _refuse_holdout(score_root, timing_path, proposal_path, preflight_path, output_path)
    if output_path.exists():
        raise PipelineError("Projecao temporal v22 ja existe; sobrescrita recusada.")

    summary_path = score_root / "summary.json"
    score_summary = _load(summary_path)
    predictions = score_summary.get("predictions")
    if (
        score_summary.get("schema") != SUMMARY_SCHEMA
        or score_summary.get("status") != "complete"
        or int(score_summary.get("case_count", -1)) != expected_historical_case_count
        or int(score_summary.get("completed_case_count", -1)) != expected_historical_case_count
        or int(score_summary.get("pending_case_count", -1)) != 0
        or score_summary.get("scoring_timing_seconds", {}).get("all_within_180") is not True
        or score_summary.get("end_to_end_180_seconds_proven") is not False
        or score_summary.get("ground_truth_read") is not False
        or score_summary.get("holdout_opened") is not False
        or score_summary.get("metrics_calculated") is not False
        or not isinstance(predictions, list)
        or len(predictions) != expected_historical_case_count
    ):
        raise PipelineError("Resumo historico de scoring v16 invalido para projecao.")

    request_times: list[float] = []
    case_times: list[float] = []
    seen_cases: set[str] = set()
    for record in predictions:
        case_id = str(record.get("case_id", ""))
        prediction_path = score_root / "predictions" / f"{case_id}.json"
        if (
            not case_id.startswith("anon-")
            or case_id in seen_cases
            or not prediction_path.is_file()
            or _sha256(prediction_path) != record.get("prediction_sha256")
        ):
            raise PipelineError("Predicao historica v16 ausente, duplicada ou adulterada.")
        prediction = _load(prediction_path)
        candidates = prediction.get("candidate_results")
        if (
            prediction.get("schema") != PREDICTION_SCHEMA
            or prediction.get("status") != "technical_passed"
            or prediction.get("case_id") != case_id
            or prediction.get("time_gate_passed") is not True
            or prediction.get("ground_truth_read") is not False
            or prediction.get("holdout_opened") is not False
            or prediction.get("metrics_calculated") is not False
            or not isinstance(candidates, list)
            or len(candidates) != int(prediction.get("candidate_stack_count", -1))
        ):
            raise PipelineError("Predicao historica v16 violou contrato temporal.")
        seen_cases.add(case_id)
        case_times.append(_finite_positive(prediction.get("scoring_elapsed_seconds"), case_id))
        for candidate in candidates:
            request_times.append(
                _finite_positive(candidate.get("request_elapsed_seconds"), f"{case_id}/candidate")
            )
    if len(request_times) != int(score_summary.get("candidate_request_count", -1)):
        raise PipelineError("Numero de chamadas historicas divergiu do resumo v16.")

    timing = _load(timing_path)
    timing_cases = timing.get("cases")
    if (
        timing.get("schema") != HISTORICAL_TIMING_SCHEMA
        or timing.get("status") != "timing_gate_passed"
        or timing.get("model_id") != "google/medgemma-1.5-4b-it"
        or timing.get("case_time_gate_seconds") != CASE_TIME_GATE_SECONDS
        or timing.get("ground_truth_read") is not False
        or timing.get("holdout_opened") is not False
        or timing.get("metrics_calculated") is not False
        or timing.get("timing_interpretation", {}).get("full_pipeline_180_seconds_proven") is not False
        or not isinstance(timing_cases, list)
        or not timing_cases
    ):
        raise PipelineError("Relatorio historico de timing v16 invalido.")
    alignment_localizer_max = max(
        _finite_positive(row.get("known_alignment_localizer_seconds"), "alignment_localizer")
        for row in timing_cases
    )
    rendering_max = max(
        _finite_positive(row.get("rendering_elapsed_seconds"), "rendering")
        for row in timing_cases
    )

    proposal = _load(proposal_path)
    if (
        proposal.get("schema") != PROPOSAL_SCHEMA
        or proposal.get("status") != "complete_blind_proposals_with_declared_fallbacks"
        or proposal.get("algorithm_version") != PROPOSAL_ALGORITHM
        or proposal.get("labels_read") is not False
        or proposal.get("ground_truth_lesion_masks_read") != 0
        or proposal.get("inference_executed") is not False
    ):
        raise PipelineError("Resumo do localizador de propostas v22 invalido.")
    proposal_max = _finite_positive(proposal.get("max_case_seconds"), "proposal_localizer")

    preflight = _load(preflight_path)
    if (
        preflight.get("schema") != PREFLIGHT_SCHEMA
        or preflight.get("status") != "passed_pending_explicit_human_review"
        or preflight.get("case_count") != 10
        or preflight.get("candidate_stack_count") != 48
        or preflight.get("selection", {}).get("maximum_components") != MAX_CANDIDATES
        or preflight.get("human_review_signed") is not False
        or preflight.get("inference_authorized") is not False
        or preflight.get("inference_executed") is not False
        or preflight.get("labels_read") is not False
        or preflight.get("lesion_masks_read") is not False
        or preflight.get("holdout_opened") is not False
        or preflight.get("case_time_gate_seconds") != CASE_TIME_GATE_SECONDS
    ):
        raise PipelineError("Preflight exact-top5 v22 invalido para projecao temporal.")

    request_stats = {
        "count": len(request_times),
        "minimum": min(request_times),
        "median": statistics.median(request_times),
        "p90_higher": _quantile(request_times, 0.90),
        "p95_higher": _quantile(request_times, 0.95),
        "p99_higher": _quantile(request_times, 0.99),
        "maximum": max(request_times),
    }
    fixed_overhead = alignment_localizer_max + rendering_max + proposal_max
    scenarios = []
    for name, request_seconds in (
        ("p95_higher", request_stats["p95_higher"]),
        ("p99_higher", request_stats["p99_higher"]),
        ("maximum_observed", request_stats["maximum"]),
    ):
        score_seconds = MAX_CANDIDATES * request_seconds
        projected = fixed_overhead + score_seconds
        scenarios.append(
            {
                "scenario": name,
                "request_seconds": request_seconds,
                "candidate_count": MAX_CANDIDATES,
                "projected_scoring_seconds": score_seconds,
                "projected_pipeline_seconds": projected,
                "margin_to_180_seconds": CASE_TIME_GATE_SECONDS - projected,
                "projected_gate_passed": projected <= CASE_TIME_GATE_SECONDS,
            }
        )

    strict = next(row for row in scenarios if row["scenario"] == "maximum_observed")
    result: dict[str, Any] = {
        "schema": PROJECTION_SCHEMA,
        "status": "projection_complete_actual_v22_measurement_required",
        "model_id": "google/medgemma-1.5-4b-it",
        "case_time_gate_seconds": CASE_TIME_GATE_SECONDS,
        "historical_request_times_seconds": request_stats,
        "historical_case_scoring_seconds": {
            "count": len(case_times),
            "median": statistics.median(case_times),
            "maximum": max(case_times),
        },
        "fixed_overhead_seconds": {
            "historical_alignment_and_localizer_maximum": alignment_localizer_max,
            "historical_five_candidate_rendering_maximum": rendering_max,
            "v22_proposal_generation_maximum": proposal_max,
            "conservative_sum": fixed_overhead,
            "possible_double_counting_of_replaced_historical_localizer": True,
        },
        "scenarios": scenarios,
        "strict_worst_observed_projection_passed": strict["projected_gate_passed"],
        "actual_v22_pilot_measured": False,
        "precomputed_scoring_only_180_seconds_previously_proven": True,
        "raw_dicom_end_to_end_180_seconds_proven": False,
        "qualification_decision": "pending_actual_v22_pilot",
        "source_hashes": {
            "historical_score_summary_sha256": _sha256(summary_path),
            "historical_timing_report_sha256": _sha256(timing_path),
            "v22_proposal_summary_sha256": _sha256(proposal_path),
            "v22_preflight_sha256": _sha256(preflight_path),
        },
        "ground_truth_read": False,
        "lesion_masks_read": False,
        "holdout_opened": False,
        "inference_executed": False,
        "research_only": True,
        "clinical_use_allowed": False,
        "requires_human_review": True,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    _write_json_atomic(output_path, result)
    return result


__all__ = ["PROJECTION_SCHEMA", "project_enhancement_top5_timing"]
