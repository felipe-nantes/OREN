from __future__ import annotations

import numpy as np
import pytest
import yaml

from dtwin.core import PipelineError
from dtwin.learning.medsiglip_pairwise_subtype import (
    _fit_pair_models,
    _macro_recall,
    class_pairs,
    load_pairwise_config,
    pairwise_probability_mass,
)


def _config(**overrides):
    value = {
        "schema": "argos-hybrid-medsiglip-pairwise-subtype-config-v1",
        "candidate_id": "test",
        "class_names": ["a", "b", "c", "d"],
        "regularization_c_grid": [0.1, 1.0],
        "panel_probability_aggregations": ["mean", "top2_mean"],
        "selection_objective": "inner_macro_recall_only",
        "binary_decision_unchanged": True,
        "technical_failures_count_as_errors": True,
    }
    value.update(overrides)
    return value


def test_pairwise_config_is_fail_closed(tmp_path):
    path = tmp_path / "pairwise.yaml"
    path.write_text(yaml.safe_dump(_config()), encoding="utf-8")
    assert load_pairwise_config(path)["binary_decision_unchanged"] is True
    path.write_text(yaml.safe_dump(_config(binary_decision_unchanged=False)), encoding="utf-8")
    with pytest.raises(PipelineError, match="decisão binária"):
        load_pairwise_config(path)


def test_four_classes_create_exactly_six_pairs():
    pairs = class_pairs(["hcc", "fnh", "hemangioma", "hepatic_cyst"])
    assert len(pairs) == 6
    assert len(set(pairs)) == 6


def _separable():
    rng = np.random.RandomState(7)
    names = ["a", "b", "c", "d"]
    centers = np.eye(4) * 8.0
    embeddings = {}
    labels = {}
    for class_index, name in enumerate(names):
        for index in range(8):
            case_id = f"{name}{index}"
            embeddings[case_id] = [centers[class_index] + rng.normal(0, 0.2, 4)]
            labels[case_id] = name
    return names, embeddings, labels


def test_pairwise_mass_is_normalized_and_label_blind():
    names, embeddings, labels = _separable()
    models = _fit_pair_models(labels, embeddings, labels, names, c_value=1.0, seed=1, max_iter=500)
    mass = pairwise_probability_mass(models, embeddings["a0"], names, "mean")
    assert sum(mass.values()) == pytest.approx(1.0)
    assert max(mass, key=mass.get) == "a"
    assert set(mass) == set(names)


def test_pairwise_rejects_missing_pair_model():
    names, embeddings, labels = _separable()
    models = _fit_pair_models(labels, embeddings, labels, names, c_value=1.0, seed=1, max_iter=500)
    models.pop(next(iter(models)))
    with pytest.raises(PipelineError, match="incompleta"):
        pairwise_probability_mass(models, embeddings["a0"], names, "mean")


def test_macro_recall_counts_missing_embedding_as_error():
    masses = {"a": {"x": 0.9, "y": 0.1}}
    metrics = _macro_recall(["a", "b"], masses, {"a": "x", "b": "y"}, ["x", "y"])
    assert metrics["balanced_accuracy"] == pytest.approx(0.5)
    assert metrics["technical_failures"] == 1


def test_pair_fit_fails_if_training_fold_lacks_a_class():
    names, embeddings, labels = _separable()
    ids = [case_id for case_id in labels if labels[case_id] != "d"]
    with pytest.raises(PipelineError, match="Fold sem as duas classes"):
        _fit_pair_models(ids, embeddings, labels, names, c_value=1.0, seed=1, max_iter=500)
