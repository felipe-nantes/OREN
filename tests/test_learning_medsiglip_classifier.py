from __future__ import annotations

from dtwin.learning.medsiglip_classifier import (
    _aggregate,
    _best_threshold,
    _confusion,
)


def test_panel_probability_aggregations():
    values = [0.1, 0.8, 0.6]
    assert _aggregate(values, "mean") == sum(values) / 3
    assert _aggregate(values, "max") == 0.8
    assert _aggregate(values, "top2_mean") == 0.7


def test_threshold_selection_uses_failures_as_errors():
    case_ids = ["p1", "p2", "n1", "n2"]
    labels = {"p1": 1, "p2": 1, "n1": 0, "n2": 0}
    scores = {"p1": 0.9, "n1": 0.1}
    threshold, metrics = _best_threshold(case_ids, scores, labels)
    assert 0.1 < threshold <= 0.9
    assert metrics["technical_failures"] == 2
    assert metrics["sensitivity"] == 0.5
    assert metrics["specificity"] == 0.5


def test_confusion_counts_negative_failure_as_false_positive():
    metrics = _confusion(
        ["positive", "negative"],
        {"positive": 0.9},
        {"positive": 1, "negative": 0},
        0.5,
    )
    assert metrics["tp"] == 1
    assert metrics["fp"] == 1
    assert metrics["technical_failures"] == 1
