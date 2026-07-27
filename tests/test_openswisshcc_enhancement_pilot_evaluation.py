from __future__ import annotations

import json
from pathlib import Path

import pytest

from dtwin.benchmark.openswisshcc_alignment import _sha256
from dtwin.benchmark.openswisshcc_candidate_volume_score import (
    PREDICTION_SCHEMA,
    RUN_CONTEXT_SCHEMA,
    SUMMARY_SCHEMA,
)
from dtwin.benchmark.openswisshcc_enhancement_pilot_evaluation import (
    EVALUATION_SCHEMA,
    PROTOCOL_SCHEMA,
    evaluate_enhancement_pilot,
    freeze_enhancement_pilot_evaluation_protocol,
)
from dtwin.benchmark.openswisshcc_enhancement_score_preflight import PREFLIGHT_SCHEMA
from dtwin.core import PipelineError


def _write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def _preflight(tmp_path: Path) -> tuple[Path, list[str]]:
    path = tmp_path / "development_preflight.json"
    case_ids = [f"anon-openswiss-{index:02d}" for index in range(10)]
    _write(
        path,
        {
            "schema": PREFLIGHT_SCHEMA,
            "status": "passed_pending_explicit_human_review",
            "case_count": 10,
            "candidate_stack_count": 48,
            "cases": [{"case_id": case_id} for case_id in case_ids],
            "source_hashes": {
                "gallery_signature": "g" * 64,
                "bundle_cohort_sha256": "b" * 64,
            },
            "human_review_signed": False,
            "inference_authorized": False,
            "inference_executed": False,
            "labels_read": False,
            "lesion_masks_read": False,
            "holdout_opened": False,
            "case_time_gate_seconds": 180.0,
        },
    )
    return path, case_ids


def test_freeze_is_signed_and_refuses_late_predictions(tmp_path: Path) -> None:
    preflight, _ = _preflight(tmp_path)
    score_root = tmp_path / "scores" / "pilot_v1"
    protocol_path = tmp_path / "protocol.json"
    protocol = freeze_enhancement_pilot_evaluation_protocol(
        preflight_path=preflight,
        intended_score_root=score_root,
        output_path=protocol_path,
    )
    assert protocol["schema"] == PROTOCOL_SCHEMA
    assert protocol["predictions_present_at_freeze"] is False
    assert protocol["labels_read"] is False
    assert protocol["case_decision_rule"]["score_threshold_calibration"] == "none"
    assert len(protocol["protocol_signature"]) == 64
    score_root.mkdir(parents=True)
    with pytest.raises(PipelineError, match="congelamento tardio"):
        freeze_enhancement_pilot_evaluation_protocol(
            preflight_path=preflight,
            intended_score_root=score_root,
            output_path=tmp_path / "late.json",
        )


def _complete_score_run(
    score_root: Path,
    case_ids: list[str],
    decisions: list[str],
) -> None:
    records = []
    total = 0
    for index, (case_id, decision) in enumerate(zip(case_ids, decisions, strict=True)):
        count = 4 if index in {1, 4} else 5
        classifications = [decision] + ["NEGATIVA"] * (count - 1)
        prediction = {
            "schema": PREDICTION_SCHEMA,
            "status": "technical_passed",
            "case_id": case_id,
            "candidate_stack_count": count,
            "candidate_results": [
                {"classification": value} for value in classifications
            ],
            "scoring_elapsed_seconds": 80.0 + index,
            "time_gate_passed": True,
            "ground_truth_read": False,
            "holdout_opened": False,
            "metrics_calculated": False,
        }
        path = score_root / "predictions" / f"{case_id}.json"
        _write(path, prediction)
        records.append({"case_id": case_id, "prediction_sha256": _sha256(path)})
        total += count
    _write(
        score_root / "summary.json",
        {
            "schema": SUMMARY_SCHEMA,
            "status": "complete",
            "case_count": 10,
            "completed_case_count": 10,
            "pending_case_count": 0,
            "candidate_request_count": total,
            "predictions": records,
            "ground_truth_read": False,
            "holdout_opened": False,
            "metrics_calculated": False,
        },
    )
    _write(
        score_root / "run_context.json",
        {
            "schema": RUN_CONTEXT_SCHEMA,
            "case_ids": case_ids,
            "bundle_cohort_sha256": "b" * 64,
            "bundle_gallery_signature": "g" * 64,
            "ground_truth_read": False,
            "holdout_opened": False,
            "metrics_calculated": False,
        },
    )


def test_evaluation_applies_any_positive_and_penalizes_inconclusives(tmp_path: Path) -> None:
    preflight, case_ids = _preflight(tmp_path)
    score_root = tmp_path / "scores" / "pilot_v1"
    protocol_path = tmp_path / "protocol.json"
    freeze_enhancement_pilot_evaluation_protocol(
        preflight_path=preflight,
        intended_score_root=score_root,
        output_path=protocol_path,
    )
    # Four positives: 3 TP + 1 inconclusive/FN. Six negatives: 5 TN + 1 inconclusive/FP.
    decisions = [
        "POSITIVA", "POSITIVA", "POSITIVA", "INCONCLUSIVA",
        "NEGATIVA", "NEGATIVA", "NEGATIVA", "NEGATIVA", "NEGATIVA", "INCONCLUSIVA",
    ]
    _complete_score_run(score_root, case_ids, decisions)
    labels_path = tmp_path / "development_labels.jsonl"
    labels_path.write_text(
        "".join(
            json.dumps(
                {
                    "schema": "argos-openswisshcc-ground-truth-v1",
                    "case_id": case_id,
                    "label": "POSITIVE" if index < 4 else "NEGATIVE",
                }
            ) + "\n"
            for index, case_id in enumerate(case_ids)
        ),
        encoding="utf-8",
    )
    result = evaluate_enhancement_pilot(
        protocol_path=protocol_path,
        preflight_path=preflight,
        score_root=score_root,
        labels_path=labels_path,
        output_root=tmp_path / "evaluation",
    )
    assert result["schema"] == EVALUATION_SCHEMA
    assert result["confusion_matrix"] == {"tp": 3, "tn": 5, "fp": 1, "fn": 1}
    assert result["sensitivity"] == 0.75
    assert result["specificity"] == pytest.approx(5 / 6)
    assert result["inconclusive_count"] == 2
    assert result["inconclusives_counted_as_errors"] is True
    assert result["pilot_75_75_180_gate_passed"] is True
    assert result["qualified"] is False
    assert result["raw_dicom_end_to_end_180_seconds_proven"] is False


def test_evaluation_refuses_holdout_path(tmp_path: Path) -> None:
    preflight, _ = _preflight(tmp_path)
    with pytest.raises(PipelineError, match="holdout"):
        freeze_enhancement_pilot_evaluation_protocol(
            preflight_path=preflight,
            intended_score_root=tmp_path / "holdout" / "scores",
            output_path=tmp_path / "protocol.json",
        )
