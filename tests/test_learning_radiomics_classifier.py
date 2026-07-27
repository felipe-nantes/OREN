from __future__ import annotations

import numpy as np
import pytest

from dtwin.core import PipelineError
from dtwin.learning.radiomics_classifier import (
    _best_threshold,
    _confusion,
    _fit_model,
)


def test_negative_technical_failure_counts_as_false_positive():
    metrics = _confusion(
        ["positive", "negative"],
        {"positive": 0.9},
        {"positive": 1, "negative": 0},
        0.5,
    )
    assert metrics["tp"] == 1
    assert metrics["fp"] == 1
    assert metrics["technical_failures"] == 1


def test_threshold_is_selected_without_dropping_failures():
    ids = ["p1", "p2", "n1", "n2"]
    labels = {"p1": 1, "p2": 1, "n1": 0, "n2": 0}
    threshold, metrics = _best_threshold(ids, {"p1": 0.9, "n1": 0.1}, labels)
    assert 0.1 < threshold <= 0.9
    assert metrics["sensitivity"] == 0.5
    assert metrics["specificity"] == 0.5


def test_elastic_net_pipeline_selects_features_inside_fit():
    features = {
        f"p{i}": np.asarray([2.0 + i, 0.1 * i, 1.0, -i], dtype=np.float64)
        for i in range(4)
    }
    features.update(
        {
            f"n{i}": np.asarray([-2.0 - i, -0.1 * i, 1.0, i], dtype=np.float64)
            for i in range(4)
        }
    )
    labels = {case_id: int(case_id.startswith("p")) for case_id in features}
    model = _fit_model(
        list(features),
        features,
        labels,
        c_value=0.1,
        l1_ratio=0.5,
        feature_count=2,
        seed=7,
        max_iter=1000,
    )
    assert model.named_steps["selector"].get_support().sum() == 2
    assert model.predict_proba(np.stack(list(features.values()))).shape == (8, 2)


def test_training_requires_two_classes():
    features = {"a": np.asarray([1.0, 2.0]), "b": np.asarray([2.0, 3.0])}
    with pytest.raises(PipelineError, match="duas classes"):
        _fit_model(
            ["a", "b"],
            features,
            {"a": 1, "b": 1},
            c_value=0.1,
            l1_ratio=0.5,
            feature_count="all",
            seed=1,
            max_iter=100,
        )
