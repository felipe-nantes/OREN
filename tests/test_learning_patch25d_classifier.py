from __future__ import annotations

from dtwin.learning.patch25d_classifier import _aggregate, _best_threshold, _confusion


def test_candidate_aggregations():
    values = [0.1, 0.9, 0.5]
    assert _aggregate(values, "max") == 0.9
    assert _aggregate(values, "top2_mean") == 0.7
    assert _aggregate(values, "top3_mean") == 0.5


def test_failures_count_as_case_errors():
    labels = {"p": "POSITIVE", "n": "NEGATIVE"}
    metrics = _confusion(["p", "n"], {"p": 0.9}, labels, 0.5)
    assert metrics["tp"] == 1
    assert metrics["fp"] == 1
    assert metrics["technical_failures"] == 1


def test_inner_threshold_balances_axes():
    ids = ["p1", "p2", "n1", "n2"]
    labels = {"p1": "POSITIVE", "p2": "POSITIVE", "n1": "NEGATIVE", "n2": "NEGATIVE"}
    threshold, metrics = _best_threshold(
        ids, {"p1": 0.9, "p2": 0.8, "n1": 0.2, "n2": 0.1}, labels
    )
    assert 0.2 < threshold <= 0.8
    assert metrics["balanced_accuracy"] == 1.0
