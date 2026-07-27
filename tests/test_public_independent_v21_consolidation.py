from __future__ import annotations

import json
from pathlib import Path

import pytest

from dtwin.benchmark import public_independent_v21_consolidation as module
from dtwin.core import PipelineError


def _write(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value), encoding="utf-8")


def _fixture(tmp_path: Path) -> tuple[Path, Path]:
    positive = {
        "schema": module.POSITIVE_SCHEMA,
        "evaluation_scope": "positive_only_external_sensitivity_stress",
        "case_count": 14, "positive_count": 14, "negative_count": 0,
        "confusion_matrix_positive_arm": {"tp": 11, "fn": 3},
        "sensitivity": 11 / 14, "sensitivity_95_wilson": [0.52, 0.92],
        "specificity": None, "simultaneous_75_75_gate_evaluated": False,
        "qualified": False, "time_gate_180_seconds_passed": True,
        "timing_seconds": {"maximum": 52.0},
        "source_hashes": {"calibrator_sha256": "a" * 64},
        "protected_public_ground_truth_read": True, "holdout_opened": False,
    }
    negative = {
        "schema": module.NEGATIVE_SCHEMA,
        "evaluation_scope": "negative_only_secondary_specificity_domain_shift_stress",
        "case_count": 20, "positive_count": 0, "negative_count": 20,
        "confusion_matrix_negative_arm": {"tn": 20, "fp": 0},
        "specificity": 1.0, "specificity_95_wilson": [0.84, 1.0],
        "sensitivity": None, "dataset_class_confounding": True,
        "combined_primary_metric_allowed": False,
        "simultaneous_75_75_gate_evaluated": False, "qualified": False,
        "time_gate_180_seconds_passed": True,
        "timing_seconds": {"maximum": 44.0},
        "source_hashes": {"calibrator_sha256": "a" * 64},
        "protected_public_ground_truth_read": True, "holdout_opened": False,
    }
    pos, neg = tmp_path / "positive.json", tmp_path / "negative.json"
    _write(pos, positive); _write(neg, negative)
    return pos, neg


def test_consolidation_reports_point_gates_but_refuses_pooled_metric(tmp_path: Path):
    positive, negative = _fixture(tmp_path)
    result = module.consolidate_v21_external_arms(
        positive_evaluation_path=positive, negative_evaluation_path=negative,
        output_dir=tmp_path / "out",
    )
    assert result["point_estimate_gates"]["both_passed"] is True
    assert result["confidence_interval_lower_bound_gates"]["both_passed"] is False
    assert result["time_gate"]["both_arms_passed"] is True
    assert result["pooled_confusion_matrix"] is None
    assert result["pooled_metrics_forbidden"] is True
    assert result["qualified"] is False
    assert result["holdout_opened"] is False


def test_consolidation_rejects_dataset_confounding_hidden(tmp_path: Path):
    positive, negative = _fixture(tmp_path)
    payload = json.loads(negative.read_text())
    payload["dataset_class_confounding"] = False
    _write(negative, payload)
    with pytest.raises(PipelineError, match="negativo"):
        module.consolidate_v21_external_arms(
            positive_evaluation_path=positive, negative_evaluation_path=negative,
            output_dir=tmp_path / "out",
        )


def test_consolidation_rejects_different_calibrators(tmp_path: Path):
    positive, negative = _fixture(tmp_path)
    payload = json.loads(negative.read_text())
    payload["source_hashes"]["calibrator_sha256"] = "b" * 64
    _write(negative, payload)
    with pytest.raises(PipelineError, match="calibrador"):
        module.consolidate_v21_external_arms(
            positive_evaluation_path=positive, negative_evaluation_path=negative,
            output_dir=tmp_path / "out",
        )
