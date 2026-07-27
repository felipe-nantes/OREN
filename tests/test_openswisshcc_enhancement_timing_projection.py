from __future__ import annotations

import json
from pathlib import Path

import pytest

from dtwin.benchmark.openswisshcc_alignment import _sha256
from dtwin.benchmark.openswisshcc_candidate_volume_score import (
    PREDICTION_SCHEMA,
    SUMMARY_SCHEMA,
)
from dtwin.benchmark.openswisshcc_enhancement_localizer import (
    ALGORITHM_VERSION as PROPOSAL_ALGORITHM,
    COHORT_SCHEMA as PROPOSAL_SCHEMA,
)
from dtwin.benchmark.openswisshcc_enhancement_score_preflight import PREFLIGHT_SCHEMA
from dtwin.benchmark.openswisshcc_enhancement_timing_projection import (
    HISTORICAL_TIMING_SCHEMA,
    PROJECTION_SCHEMA,
    project_enhancement_top5_timing,
)
from dtwin.core import PipelineError


def _write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def _fixture(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    score_root = tmp_path / "development_scores"
    records = []
    total_requests = 0
    for index, request_times in enumerate(([10.0, 20.0], [30.0]), 1):
        case_id = f"anon-openswiss-{index}"
        prediction = {
            "schema": PREDICTION_SCHEMA,
            "status": "technical_passed",
            "case_id": case_id,
            "candidate_stack_count": len(request_times),
            "candidate_results": [
                {"request_elapsed_seconds": value} for value in request_times
            ],
            "scoring_elapsed_seconds": sum(request_times) + 1.0,
            "time_gate_passed": True,
            "ground_truth_read": False,
            "holdout_opened": False,
            "metrics_calculated": False,
        }
        path = score_root / "predictions" / f"{case_id}.json"
        _write(path, prediction)
        records.append(
            {
                "case_id": case_id,
                "prediction_sha256": _sha256(path),
                "scoring_elapsed_seconds": prediction["scoring_elapsed_seconds"],
            }
        )
        total_requests += len(request_times)
    _write(
        score_root / "summary.json",
        {
            "schema": SUMMARY_SCHEMA,
            "status": "complete",
            "case_count": 2,
            "completed_case_count": 2,
            "pending_case_count": 0,
            "candidate_request_count": total_requests,
            "predictions": records,
            "scoring_timing_seconds": {"all_within_180": True},
            "end_to_end_180_seconds_proven": False,
            "ground_truth_read": False,
            "holdout_opened": False,
            "metrics_calculated": False,
        },
    )
    timing_path = tmp_path / "development_timing.json"
    _write(
        timing_path,
        {
            "schema": HISTORICAL_TIMING_SCHEMA,
            "status": "timing_gate_passed",
            "model_id": "google/medgemma-1.5-4b-it",
            "case_time_gate_seconds": 180.0,
            "cases": [
                {
                    "known_alignment_localizer_seconds": 50.0,
                    "rendering_elapsed_seconds": 10.0,
                }
            ],
            "ground_truth_read": False,
            "holdout_opened": False,
            "metrics_calculated": False,
            "timing_interpretation": {"full_pipeline_180_seconds_proven": False},
        },
    )
    proposal_path = tmp_path / "development_proposals.json"
    _write(
        proposal_path,
        {
            "schema": PROPOSAL_SCHEMA,
            "status": "complete_blind_proposals_with_declared_fallbacks",
            "algorithm_version": PROPOSAL_ALGORITHM,
            "max_case_seconds": 5.0,
            "labels_read": False,
            "ground_truth_lesion_masks_read": 0,
            "inference_executed": False,
        },
    )
    preflight_path = tmp_path / "development_preflight.json"
    _write(
        preflight_path,
        {
            "schema": PREFLIGHT_SCHEMA,
            "status": "passed_pending_explicit_human_review",
            "case_count": 10,
            "candidate_stack_count": 48,
            "selection": {"maximum_components": 5},
            "human_review_signed": False,
            "inference_authorized": False,
            "inference_executed": False,
            "labels_read": False,
            "lesion_masks_read": False,
            "holdout_opened": False,
            "case_time_gate_seconds": 180.0,
        },
    )
    return score_root, timing_path, proposal_path, preflight_path


def test_projection_is_conservative_and_never_qualifies_without_measurement(tmp_path: Path) -> None:
    score, timing, proposal, preflight = _fixture(tmp_path)
    output = tmp_path / "new" / "projection.json"
    result = project_enhancement_top5_timing(
        historical_score_root=score,
        historical_timing_report_path=timing,
        proposal_summary_path=proposal,
        preflight_path=preflight,
        output_path=output,
        expected_historical_case_count=2,
    )
    assert result["schema"] == PROJECTION_SCHEMA
    assert result["historical_request_times_seconds"]["maximum"] == 30.0
    strict = next(row for row in result["scenarios"] if row["scenario"] == "maximum_observed")
    assert strict["projected_pipeline_seconds"] == 215.0
    assert strict["projected_gate_passed"] is False
    assert result["actual_v22_pilot_measured"] is False
    assert result["qualification_decision"] == "pending_actual_v22_pilot"
    assert result["ground_truth_read"] is False
    assert result["inference_executed"] is False
    assert output.is_file()


def test_projection_rejects_tampered_historical_prediction(tmp_path: Path) -> None:
    score, timing, proposal, preflight = _fixture(tmp_path)
    path = score / "predictions" / "anon-openswiss-1.json"
    path.write_text(path.read_text(encoding="utf-8") + " ", encoding="utf-8")
    with pytest.raises(PipelineError, match="adulterada"):
        project_enhancement_top5_timing(
            historical_score_root=score,
            historical_timing_report_path=timing,
            proposal_summary_path=proposal,
            preflight_path=preflight,
            output_path=tmp_path / "projection.json",
            expected_historical_case_count=2,
        )


def test_projection_refuses_holdout_output(tmp_path: Path) -> None:
    score, timing, proposal, preflight = _fixture(tmp_path)
    with pytest.raises(PipelineError, match="holdout"):
        project_enhancement_top5_timing(
            historical_score_root=score,
            historical_timing_report_path=timing,
            proposal_summary_path=proposal,
            preflight_path=preflight,
            output_path=tmp_path / "holdout" / "projection.json",
            expected_historical_case_count=2,
        )
