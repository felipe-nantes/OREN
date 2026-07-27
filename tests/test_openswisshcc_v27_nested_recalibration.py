from __future__ import annotations

import numpy as np
import pytest

from dtwin.benchmark import openswisshcc_v27_nested_recalibration as subject


def test_logistic_fit_separates_simple_balanced_data():
    matrix = np.asarray([[-2.0], [-1.0], [1.0], [2.0]])
    truth = np.asarray([0.0, 0.0, 1.0, 1.0])
    fitted = subject._fit_logistic(matrix, truth, 0.01)
    probabilities = subject._predict_logistic(matrix, fitted)
    assert probabilities[0] < probabilities[1] < probabilities[2] < probabilities[3]
    assert probabilities[1] < 0.5 < probabilities[2]


def test_scaler_replaces_constant_scale():
    mean, scale = subject._fit_scaler(np.asarray([[1.0, 2.0], [1.0, 4.0]]))
    assert mean.tolist() == [1.0, 3.0]
    assert scale[0] == 1.0
    assert scale[1] == 1.0


def test_inner_assignments_are_deterministic_and_stratified():
    ids = [f"case-{index}" for index in range(20)]
    labels = {case_id: index >= 10 for index, case_id in enumerate(ids)}
    first = subject._inner_assignments(ids, labels)
    second = subject._inner_assignments(list(reversed(ids)), labels)
    assert first == second
    for fold in range(subject.INNER_FOLDS):
        in_fold = [case_id for case_id in ids if first[case_id] == fold]
        assert sum(labels[case_id] for case_id in in_fold) == 2
        assert sum(not labels[case_id] for case_id in in_fold) == 2


def test_outer_selection_never_needs_test_label(monkeypatch):
    names = subject.FAMILIES["v23_core"]
    features = {
        f"case-{index}": {name: float(index + offset) for offset, name in enumerate(names)}
        for index in range(20)
    }
    labels = {case_id: index >= 10 for index, case_id in enumerate(features)}
    scores, selection = subject._fit_outer(
        features=features,
        labels=labels,
        training_ids=list(features)[:-1],
        test_ids=[list(features)[-1]],
        family="v23_core",
    )
    assert list(scores) == ["case-19"]
    assert selection["ridge"] in subject.RIDGE_GRID
    assert selection["training_case_count"] == 19


def test_prediction_marks_failure_without_fabricating_score():
    row = subject._prediction(
        case_id="failed",
        family=subject.PRIMARY_FAMILY,
        validation="loocv",
        score=None,
        threshold=None,
        selection=None,
        extra={},
    )
    assert row["prediction"] == "TECHNICAL_FAILURE"
    assert row["score"] is None
    assert row["held_out_label_used_for_model_fit"] is False
    assert row["lesion_masks_read"] == 0


def test_primary_family_contains_all_predeclared_groups():
    primary = set(subject.FAMILIES[subject.PRIMARY_FAMILY])
    assert set(subject.V23_FEATURES) <= primary
    assert "v24_mean_positive_probability" in primary
    assert "v25_suspicious_panel_fraction" in primary
    assert "v26_benign_variant_panel_fraction" in primary
    assert len(primary) == len(subject.FAMILIES[subject.PRIMARY_FAMILY])


def test_probability_validation_rejects_invalid_value():
    with pytest.raises(Exception):
        subject._finite_probability(1.1, "test")
