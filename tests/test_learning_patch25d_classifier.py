from __future__ import annotations

from dtwin.learning.patch25d_classifier import _aggregate, _best_threshold, _confusion
from dtwin.learning.patch25d_classifier import _fit, _scores
import numpy as np


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


def test_candidate_fit_preserves_non_sequential_localized_ids():
    embeddings = {
        "p": [("localized-004", np.array([1.0, 1.0])), ("localized-011", np.array([2.0, 2.0]))],
        "n": [("localized-002", np.array([-1.0, -1.0])), ("localized-019", np.array([-2.0, -2.0]))],
    }
    targets = {
        ("p", "localized-004"): 1,
        ("p", "localized-011"): 1,
        ("n", "localized-002"): 0,
        ("n", "localized-019"): 0,
    }
    model = _fit(["p", "n"], embeddings, targets, c_value=1.0, seed=7, max_iter=500)
    scores = _scores(model, ["p", "n"], embeddings, "max")
    assert scores["p"] > scores["n"]
