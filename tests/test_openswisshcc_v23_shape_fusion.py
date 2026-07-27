from __future__ import annotations

from dtwin.benchmark.openswisshcc_v20_fusion import V11_WEIGHTS
from dtwin.benchmark.openswisshcc_v23_shape_fusion import (
    CALIBRATOR_SCHEMA,
    SHAPE_WEIGHT,
    V11_WEIGHT,
    _fusion_scores,
    _loocv,
    score_with_frozen_calibrator,
)
from dtwin.benchmark.openswisshcc_v20_fusion import _canonical_sha
from dtwin.core import PipelineError
import pytest


def _rows(values):
    names = list(V11_WEIGHTS)
    return [
        {"case_id": f"anon-{index:03d}", "signals": {name: value for name in names}}
        for index, value in enumerate(values)
    ]


def test_declared_weights_sum_to_one():
    assert SHAPE_WEIGHT == 0.20
    assert V11_WEIGHT == 0.80
    assert SHAPE_WEIGHT + V11_WEIGHT == 1.0


def test_fold_scores_use_training_reference_only():
    rows = _rows([0.0, 1.0, 1000.0])
    scores = _fusion_scores(rows, [0.0, 1.0, 1000.0], [0, 1], [2])
    assert scores == [1.0]


def test_loocv_separates_a_strong_synthetic_signal():
    values = [float(index) for index in range(20)]
    rows = _rows(values)
    truth = [index >= 10 for index in range(20)]
    result = _loocv(rows, values, truth)
    assert result["sensitivity"] >= 0.9
    assert result["specificity"] >= 0.9
    assert len(result["scores"]) == 20
    assert len(result["thresholds"]) == 20


def test_shape_changes_fusion_score_when_v11_is_constant():
    rows = _rows([0.0, 0.0, 0.0])
    low, high = _fusion_scores(rows, [0.0, 1.0, 2.0], [0, 1], [0, 2])
    assert high > low


def _calibrator():
    references = {
        **{name: [0.0, 1.0] for name in V11_WEIGHTS},
        "candidate_weighted_linearity": [0.0, 1.0],
    }
    base = {
        "schema": CALIBRATOR_SCHEMA,
        "status": "frozen_for_new_independent_external_validation",
        "development_reference_count": 2,
        "primary_shape_feature": "candidate_weighted_linearity",
        "weights": {"v11": 0.8, "candidate_weighted_linearity": 0.2},
        "decision_threshold": 0.5,
        "ecdf_references": references,
        "hypothesis_selected_after_development_labels": True,
        "independent_balanced_validation_required": True,
        "holdout_v21_reuse_forbidden": True,
        "qualified": False,
        "research_only": True,
        "clinical_use_allowed": False,
    }
    return {**base, "calibrator_signature": _canonical_sha(base)}


def test_frozen_calibrator_scores_without_labels():
    signals = {name: 1.0 for name in V11_WEIGHTS}
    result = score_with_frozen_calibrator(
        _calibrator(), signals=signals, weighted_linearity=1.0
    )
    assert result["prediction"] == "POSITIVE"
    assert result["score"] == pytest.approx(0.75)


def test_frozen_calibrator_rejects_tampering():
    value = _calibrator()
    value["decision_threshold"] = 0.9
    with pytest.raises(PipelineError, match="adulterado"):
        score_with_frozen_calibrator(
            value,
            signals={name: 1.0 for name in V11_WEIGHTS},
            weighted_linearity=1.0,
        )


def test_external_signal_schema_is_exact():
    with pytest.raises(PipelineError, match="incompletos"):
        score_with_frozen_calibrator(
            _calibrator(), signals={"unexpected": 1.0}, weighted_linearity=0.5
        )
