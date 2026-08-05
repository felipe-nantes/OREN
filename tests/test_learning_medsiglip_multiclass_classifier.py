from __future__ import annotations

import numpy as np
import pytest
import yaml

from dtwin.core import PipelineError
from dtwin.learning.medsiglip_multiclass_classifier import (
    BINARY_GRANULARITY,
    CLINICAL_GRANULARITY,
    NEGATIVE_UNSPECIFIED,
    POSITIVE_UNSPECIFIED,
    _aggregate,
    _best_threshold,
    _confusion,
    _cross_validated_case_scores,
    _fit_model,
    _case_class_probability_mass,
    _positive_probability,
    _subtype_classification_metrics,
    build_multiclass_labels,
    load_multiclass_config,
    resolve_positive_classes,
    restrict_splits,
)
from dtwin.learning.schemas import ProtectedTrainingCase


def _case(case_id, label, dataset_id="lld_mmri"):
    return ProtectedTrainingCase(
        case_id=case_id, patient_group_id=case_id, dataset_id=dataset_id, label=label
    )


def _config(**overrides):
    base = {
        "schema": "argos-hybrid-medsiglip-multiclass-config-v1",
        "candidate_id": "test",
        "positive_classes": ["hcc"],
        "regularization_c_grid": [0.1, 1.0],
        "panel_probability_aggregations": ["mean", "max"],
        "threshold_selection": "inner_oof_only",
        "technical_failures_count_as_errors": True,
    }
    base.update(overrides)
    return base


def test_config_requires_inner_only_threshold(tmp_path):
    path = tmp_path / "c.yaml"
    path.write_text(yaml.safe_dump(_config(threshold_selection="outer")), encoding="utf-8")
    with pytest.raises(PipelineError, match="inner CV"):
        load_multiclass_config(path)


def test_config_requires_positive_classes(tmp_path):
    path = tmp_path / "c.yaml"
    path.write_text(yaml.safe_dump(_config(positive_classes=[])), encoding="utf-8")
    with pytest.raises(PipelineError, match="positive_classes"):
        load_multiclass_config(path)


def test_config_validates_iterative_topk_mil(tmp_path):
    selection = {
        "mode": "iterative_topk_mil",
        "positive_top_k": 2,
        "negative_hard_top_k": 3,
        "negative_easy_anchors_per_case": 1,
        "iterations": 2,
    }
    path = tmp_path / "c.yaml"
    path.write_text(
        yaml.safe_dump(_config(training_instance_selection=selection)), encoding="utf-8"
    )
    assert load_multiclass_config(path)["training_instance_selection"] == selection


def test_config_validates_domain_balanced_case_weighting(tmp_path):
    path = tmp_path / "c.yaml"
    path.write_text(yaml.safe_dump(_config(training_case_weighting="equal_dataset_class_case")), encoding="utf-8")
    assert load_multiclass_config(path)["training_case_weighting"] == "equal_dataset_class_case"
    path.write_text(yaml.safe_dump(_config(training_case_weighting="unknown")), encoding="utf-8")
    with pytest.raises(PipelineError, match="training_case_weighting"):
        load_multiclass_config(path)


@pytest.mark.parametrize(
    "selection,match",
    [
        ({"mode": "unknown", "positive_top_k": 1, "negative_hard_top_k": 1, "iterations": 1}, "Modo"),
        ({"mode": "iterative_topk_mil", "positive_top_k": 0, "negative_hard_top_k": 1, "iterations": 1}, "positive_top_k"),
        ({"mode": "iterative_topk_mil", "positive_top_k": 1, "negative_hard_top_k": 1, "iterations": 11}, "limite"),
    ],
)
def test_config_rejects_unsafe_mil_selection(tmp_path, selection, match):
    path = tmp_path / "c.yaml"
    path.write_text(
        yaml.safe_dump(_config(training_instance_selection=selection)), encoding="utf-8"
    )
    with pytest.raises(PipelineError, match=match):
        load_multiclass_config(path)


def test_build_labels_uses_finest_available_granularity():
    cases = [
        _case("l1", "POSITIVE"),
        _case("l2", "NEGATIVE"),
        _case("o1", "POSITIVE", dataset_id="openswisshcc"),
        _case("o2", "NEGATIVE", dataset_id="openswisshcc"),
    ]
    subtypes = {"l1": "hcc", "l2": "hepatic_cyst"}
    class_by_case, binary_by_case = build_multiclass_labels(cases, subtypes)
    assert class_by_case == {
        "l1": "hcc",
        "l2": "hepatic_cyst",
        "o1": POSITIVE_UNSPECIFIED,   # cohort declares only the binary endpoint
        "o2": NEGATIVE_UNSPECIFIED,
    }
    assert binary_by_case == {"l1": 1, "l2": 0, "o1": 1, "o2": 0}


def test_build_labels_rejects_subtype_contradicting_binary_endpoint():
    # 'hcc' appearing on both a POSITIVE and a NEGATIVE case means the label
    # sources contradict each other -- must fail closed, never be averaged over.
    cases = [_case("a", "POSITIVE"), _case("b", "NEGATIVE")]
    with pytest.raises(PipelineError, match="polaridade binária inconsistente"):
        build_multiclass_labels(cases, {"a": "hcc", "b": "hcc"})


def test_resolve_positive_classes_matches_protected_polarity():
    class_by_case = {"a": "hcc", "b": "hepatic_cyst", "c": POSITIVE_UNSPECIFIED}
    binary_by_case = {"a": 1, "b": 0, "c": 1}
    assert resolve_positive_classes(
        ["hcc", POSITIVE_UNSPECIFIED], class_by_case, binary_by_case
    ) == sorted(["hcc", POSITIVE_UNSPECIFIED])


def test_resolve_positive_classes_rejects_incomplete_declaration():
    class_by_case = {"a": "hcc", "b": "hepatic_cyst", "c": POSITIVE_UNSPECIFIED}
    binary_by_case = {"a": 1, "b": 0, "c": 1}
    # omits positive_unspecified, which the protected labels imply is positive
    with pytest.raises(PipelineError, match="divergem da polaridade"):
        resolve_positive_classes(["hcc"], class_by_case, binary_by_case)


def test_resolve_positive_classes_rejects_absent_class():
    class_by_case = {"a": "hcc"}
    binary_by_case = {"a": 1}
    with pytest.raises(PipelineError, match="ausente da coorte"):
        resolve_positive_classes(["hcc", "metastasis"], class_by_case, binary_by_case)


def _separable_setup():
    rng = np.random.RandomState(0)
    embedding_map = {}
    class_by_case = {}
    # three classes; hcc separable from the two benign ones
    for i in range(6):
        embedding_map[f"h{i}"] = [rng.randn(4) + np.array([5.0, 0, 0, 0])]
        class_by_case[f"h{i}"] = "hcc"
    for i in range(6):
        embedding_map[f"c{i}"] = [rng.randn(4) + np.array([-5.0, 3.0, 0, 0])]
        class_by_case[f"c{i}"] = "hepatic_cyst"
    for i in range(6):
        embedding_map[f"g{i}"] = [rng.randn(4) + np.array([-5.0, -3.0, 0, 0])]
        class_by_case[f"g{i}"] = "hemangioma"
    class_index = {"hcc": 0, "hemangioma": 1, "hepatic_cyst": 2}
    return embedding_map, class_by_case, class_index


def test_fit_model_requires_both_polarities_present():
    embedding_map, class_by_case, class_index = _separable_setup()
    only_benign = [k for k in class_by_case if not k.startswith("h")]
    with pytest.raises(PipelineError, match="sem classe positiva"):
        _fit_model(
            only_benign, embedding_map, class_index, class_by_case, {0},
            c_value=1.0, seed=1, max_iter=200,
        )
    # Two classes present but BOTH declared positive -> no negative to learn
    # against. Needs >=2 classes so the "duas classes" guard passes first.
    hcc_and_cyst = [k for k in class_by_case if class_by_case[k] in ("hcc", "hepatic_cyst")]
    with pytest.raises(PipelineError, match="sem classe negativa"):
        _fit_model(
            hcc_and_cyst, embedding_map, class_index, class_by_case, {0, 2},
            c_value=1.0, seed=1, max_iter=200,
        )


def test_positive_probability_sums_mass_over_positive_classes():
    embedding_map, class_by_case, class_index = _separable_setup()
    model = _fit_model(
        list(class_by_case), embedding_map, class_index, class_by_case, {0},
        c_value=1.0, seed=1, max_iter=500,
    )
    hcc_vector = np.stack(embedding_map["h0"])
    cyst_vector = np.stack(embedding_map["c0"])
    assert _positive_probability(model, hcc_vector, {0})[0] > 0.5
    assert _positive_probability(model, cyst_vector, {0})[0] < 0.5
    # summing mass over ALL classes must be 1.0 regardless of class order
    everything = _positive_probability(model, hcc_vector, {0, 1, 2})[0]
    assert everything == pytest.approx(1.0)


def test_domain_balanced_case_weighting_trains_with_unequal_domains():
    embedding_map, class_by_case, class_index = _separable_setup()
    dataset_by_case = {
        case_id: ("large" if index < 14 else "small")
        for index, case_id in enumerate(sorted(class_by_case))
    }
    model = _fit_model(
        list(class_by_case), embedding_map, class_index, class_by_case, {0},
        c_value=1.0, seed=1, max_iter=500,
        dataset_by_case=dataset_by_case,
        case_weighting="equal_dataset_class_case",
    )
    assert np.isfinite(_positive_probability(model, np.stack(embedding_map["h0"]), {0})).all()


def test_iterative_topk_mil_learns_from_sparse_positive_instances():
    embedding_map = {}
    class_by_case = {}
    for index in range(8):
        embedding_map[f"p{index}"] = [
            np.array([4.0, index / 100]),
            np.array([-2.0, 0.0]),
            np.array([-1.5, 0.1]),
        ]
        class_by_case[f"p{index}"] = "positive"
        embedding_map[f"n{index}"] = [
            np.array([-4.0, index / 100]),
            np.array([1.0, 0.0]),
            np.array([-2.0, -0.1]),
        ]
        class_by_case[f"n{index}"] = "negative"
    model = _fit_model(
        sorted(class_by_case),
        embedding_map,
        {"negative": 0, "positive": 1},
        class_by_case,
        {1},
        c_value=0.1,
        seed=7,
        max_iter=500,
        instance_selection={
            "mode": "iterative_topk_mil",
            "positive_top_k": 1,
            "negative_hard_top_k": 1,
            "negative_easy_anchors_per_case": 1,
            "iterations": 2,
        },
    )
    positive = _positive_probability(model, np.array([[4.0, 0.0]]), {1})[0]
    negative = _positive_probability(model, np.array([[-4.0, 0.0]]), {1})[0]
    assert np.isfinite([positive, negative]).all()
    assert positive > negative


def test_aggregate_methods():
    assert _aggregate([0.1, 0.9], "max") == 0.9
    assert _aggregate([0.2, 0.4], "mean") == pytest.approx(0.3)
    assert _aggregate([0.9, 0.7, 0.1], "top2_mean") == pytest.approx(0.8)
    with pytest.raises(PipelineError, match="Agregação desconhecida"):
        _aggregate([0.5], "median")


def test_confusion_counts_missing_score_as_error_on_correct_axis():
    scores = {"n": 0.9}  # positive case 'p' has no score -> technical failure
    binary = {"p": 1, "n": 0}
    result = _confusion(["p", "n"], scores, binary, threshold=0.5)
    assert result["fn"] == 1
    assert result["fp"] == 1
    assert result["technical_failures"] == 1


def test_binary_granularity_collapses_fine_labels():
    # The ablation's control arm: same code path, fine labels discarded.
    cases = [_case("l1", "POSITIVE"), _case("l2", "NEGATIVE")]
    subtypes = {"l1": "hcc", "l2": "hepatic_cyst"}
    class_by_case, _ = build_multiclass_labels(cases, subtypes, granularity=BINARY_GRANULARITY)
    assert class_by_case == {"l1": POSITIVE_UNSPECIFIED, "l2": NEGATIVE_UNSPECIFIED}
    # ...while the default granularity keeps them
    fine, _ = build_multiclass_labels(cases, subtypes, granularity=CLINICAL_GRANULARITY)
    assert fine == {"l1": "hcc", "l2": "hepatic_cyst"}


def test_build_labels_rejects_unknown_granularity():
    with pytest.raises(PipelineError, match="label_granularity inválido"):
        build_multiclass_labels([_case("a", "POSITIVE")], {}, granularity="whatever")


def test_config_rejects_unknown_granularity_and_empty_restriction(tmp_path):
    path = tmp_path / "c.yaml"
    path.write_text(yaml.safe_dump(_config(label_granularity="nope")), encoding="utf-8")
    with pytest.raises(PipelineError, match="label_granularity inválido"):
        load_multiclass_config(path)
    path.write_text(yaml.safe_dump(_config(restrict_to_dataset_ids=[])), encoding="utf-8")
    with pytest.raises(PipelineError, match="restrict_to_dataset_ids"):
        load_multiclass_config(path)


def test_config_validates_label_blind_subtype_probability_options(tmp_path):
    path = tmp_path / "c.yaml"
    path.write_text(
        yaml.safe_dump(_config(persist_label_blind_class_probabilities="yes")),
        encoding="utf-8",
    )
    with pytest.raises(PipelineError, match="deve ser booleano"):
        load_multiclass_config(path)
    path.write_text(
        yaml.safe_dump(_config(subtype_probability_aggregation="median")),
        encoding="utf-8",
    )
    with pytest.raises(PipelineError, match="subtype_probability_aggregation"):
        load_multiclass_config(path)


def test_config_defaults_preserve_unrestricted_clinical_behaviour(tmp_path):
    # Etapa C's committed run must keep working unchanged when the new options
    # are absent from the config.
    path = tmp_path / "c.yaml"
    path.write_text(yaml.safe_dump(_config()), encoding="utf-8")
    loaded = load_multiclass_config(path)
    assert loaded.get("label_granularity", CLINICAL_GRANULARITY) == CLINICAL_GRANULARITY
    assert loaded.get("restrict_to_dataset_ids") is None


def test_config_validates_monophase_deployment_contract(tmp_path):
    deployment = {
        "analysis_scenario": "monophase_medsiglip",
        "panel_image_mode": "single_phase_portal_venous_grayscale_liver_enriched",
        "expected_panel_counts": [2, 3],
        "source_phase_contract": "exactly_one_real_series",
        "dynamic_enhancement_information_present": False,
        "generalization_estimate_source": "nested_oof_lld_monophase_ablation",
    }
    path = tmp_path / "c.yaml"
    path.write_text(yaml.safe_dump(_config(deployment=deployment)), encoding="utf-8")
    assert load_multiclass_config(path)["deployment"] == deployment
    deployment["expected_panel_counts"] = []
    path.write_text(yaml.safe_dump(_config(deployment=deployment)), encoding="utf-8")
    with pytest.raises(PipelineError, match="expected_panel_counts"):
        load_multiclass_config(path)


def test_restrict_splits_keeps_original_fold_membership():
    splits = {
        "schema": "argos-hybrid-nested-splits-v1",
        "case_count": 4,
        "outer_folds": [
            {
                "outer_fold": 0,
                "train_case_ids": ["c3", "c4"],
                "test_case_ids": ["c1", "c2"],
                "inner_folds": [
                    {"inner_fold": 0, "train_case_ids": ["c3"], "validation_case_ids": ["c4"]}
                ],
            }
        ],
    }
    restricted = restrict_splits(splits, {"c1", "c3"})
    fold = restricted["outer_folds"][0]
    assert fold["test_case_ids"] == ["c1"]      # c2 dropped, c1 stays in fold 0
    assert fold["train_case_ids"] == ["c3"]     # c4 dropped
    assert fold["inner_folds"][0]["validation_case_ids"] == []


def test_best_threshold_selected_from_supplied_scores_only():
    scores = {"p1": 0.9, "p2": 0.7, "n1": 0.3, "n2": 0.1}
    binary = {"p1": 1, "p2": 1, "n1": 0, "n2": 0}
    threshold, metrics = _best_threshold(["p1", "p2", "n1", "n2"], scores, binary)
    assert metrics["sensitivity"] == 1.0
    assert metrics["specificity"] == 1.0
    assert 0.3 < threshold <= 0.7


def test_cross_validated_scores_cover_each_case_exactly_once():
    # Two outer folds; every case is scored exactly once, by the fold where it is
    # in test (never by a model that trained on it).
    rng = np.random.RandomState(0)
    embedding_map = {}
    class_by_case = {}
    for i in range(4):
        embedding_map[f"h{i}"] = [rng.randn(4) + np.array([4.0, 0, 0, 0])]
        class_by_case[f"h{i}"] = "hcc"
    for i in range(4):
        embedding_map[f"c{i}"] = [rng.randn(4) + np.array([-4.0, 0, 0, 0])]
        class_by_case[f"c{i}"] = "hepatic_cyst"
    class_index = {"hcc": 0, "hepatic_cyst": 1}
    fold_a = {"h0", "h1", "c0", "c1"}
    fold_b = {"h2", "h3", "c2", "c3"}
    splits = {
        "outer_folds": [
            {"outer_fold": 0, "train_case_ids": sorted(fold_b), "test_case_ids": sorted(fold_a),
             "inner_folds": []},
            {"outer_fold": 1, "train_case_ids": sorted(fold_a), "test_case_ids": sorted(fold_b),
             "inner_folds": []},
        ]
    }
    scores = _cross_validated_case_scores(
        splits=splits, embedding_map=embedding_map, class_index=class_index,
        class_by_case=class_by_case, positive_indices={0}, c_value=1.0,
        aggregation="mean", seed=1, max_iter=500,
    )
    assert set(scores) == set(class_by_case)  # every case scored exactly once
    # separable synthetic -> hcc scored above cysts
    assert min(scores[f"h{i}"] for i in range(4)) > max(scores[f"c{i}"] for i in range(4))


def test_case_class_probability_mass_is_label_blind_and_normalized():
    embedding_map, class_by_case, class_index = _separable_setup()
    model = _fit_model(
        list(class_by_case), embedding_map, class_index, class_by_case, {0},
        c_value=1.0, seed=1, max_iter=500,
    )
    mass = _case_class_probability_mass(
        model, ["h0", "c0"], embedding_map,
        ["hcc", "hemangioma", "hepatic_cyst"], "max",
    )
    assert set(mass) == {"h0", "c0"}
    assert sum(mass["h0"].values()) == pytest.approx(1.0)
    assert max(mass["h0"], key=mass["h0"].get) == "hcc"
    assert "label" not in mass["h0"]


def test_subtype_metrics_count_failure_as_error_and_report_macro_recall():
    rows = [
        {
            "case_id": "a", "technical_failure": False, "predicted_class": "hcc",
            "class_probabilities": {"hcc": 0.8, "fnh": 0.2},
        },
        {
            "case_id": "b", "technical_failure": False, "predicted_class": "hcc",
            "class_probabilities": {"hcc": 0.7, "fnh": 0.3},
        },
        {"case_id": "c", "technical_failure": True},
    ]
    metrics = _subtype_classification_metrics(
        rows, {"a": "hcc", "b": "fnh", "c": "fnh"}, ["fnh", "hcc"]
    )
    assert metrics["top1_accuracy"] == pytest.approx(1 / 3)
    assert metrics["recall_by_subtype"] == {"fnh": 0.0, "hcc": 1.0}
    assert metrics["balanced_accuracy"] == pytest.approx(0.5)
    assert metrics["technical_failures_count_as_errors"] == 1
    assert metrics["confusion_matrix"]["fnh"]["UNDETERMINED"] == 1
