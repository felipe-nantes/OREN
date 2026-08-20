from __future__ import annotations

import json

import pytest
import yaml

from dtwin.core import PipelineError
from dtwin.learning.multi_signal_fusion import (
    _best_threshold,
    _confusion,
    _feature_vector,
    _fit_meta_model,
    _restrict_splits_to_case_universe,
    align_signals,
    load_fusion_config,
    score_correlation,
)
from dtwin.learning.schemas import ProtectedTrainingCase


def _config(**overrides):
    base = {
        "schema": "argos-hybrid-multi-signal-fusion-config-v1",
        "signals": [
            {
                "name": "medsiglip_phase5",
                "prediction_schema": "argos-hybrid-medsiglip-oof-prediction-v1",
                "freeze_schema": "argos-hybrid-medsiglip-oof-freeze-v1",
            },
            {
                "name": "medsiglip_lora_stage3",
                "prediction_schema": "argos-hybrid-medsiglip-partial-oof-prediction-v1",
                "freeze_schema": "argos-hybrid-medsiglip-partial-oof-freeze-v1",
            },
        ],
        "regularization_c_grid": [0.1, 1.0],
        "weight_selection": "inner_oof_only",
        "threshold_selection": "inner_oof_only",
        "technical_failures_count_as_errors": True,
    }
    base.update(overrides)
    return base


def test_load_fusion_config_requires_at_least_two_signals(tmp_path):
    path = tmp_path / "fusion.yaml"
    config = _config()
    config["signals"] = config["signals"][:1]
    path.write_text(yaml.safe_dump(config), encoding="utf-8")
    with pytest.raises(PipelineError, match="ao menos dois sinais"):
        load_fusion_config(path)


def test_load_fusion_config_rejects_fixed_weight_selection(tmp_path):
    path = tmp_path / "fusion.yaml"
    config = _config(weight_selection="fixed_before_fusion_evaluation")
    path.write_text(yaml.safe_dump(config), encoding="utf-8")
    with pytest.raises(PipelineError, match="inner CV"):
        load_fusion_config(path)


def test_load_fusion_config_accepts_valid_config(tmp_path):
    path = tmp_path / "fusion.yaml"
    path.write_text(yaml.safe_dump(_config()), encoding="utf-8")
    loaded = load_fusion_config(path)
    assert [item["name"] for item in loaded["signals"]] == [
        "medsiglip_phase5",
        "medsiglip_lora_stage3",
    ]


def test_load_fusion_config_validates_missing_signal_policy(tmp_path):
    path = tmp_path / "fusion.yaml"
    path.write_text(
        yaml.safe_dump(_config(missing_signal_policy="zero_margin_with_indicator")),
        encoding="utf-8",
    )
    assert load_fusion_config(path)["missing_signal_policy"] == "zero_margin_with_indicator"
    path.write_text(
        yaml.safe_dump(_config(missing_signal_policy="silently_drop")), encoding="utf-8"
    )
    with pytest.raises(PipelineError, match="missing_signal_policy"):
        load_fusion_config(path)


def _case(case_id, label, dataset_id="lld_mmri", patient_group_id=None):
    return ProtectedTrainingCase(
        case_id=case_id,
        patient_group_id=patient_group_id or case_id,
        dataset_id=dataset_id,
        label=label,
    )


def test_align_signals_intersects_all_sources_and_protected_cases():
    signal_scores = {
        "a": {"c1": {"score": 0.1, "threshold": 0.0, "technical_failure": False},
              "c2": {"score": 0.2, "threshold": 0.0, "technical_failure": False}},
        "b": {"c1": {"score": 0.3, "threshold": 0.0, "technical_failure": False}},
    }
    protected = [_case("c1", "POSITIVE"), _case("c2", "NEGATIVE")]
    common, by_id = align_signals(signal_scores, protected)
    assert common == ["c1"]
    assert by_id["c1"].label == "POSITIVE"


def test_align_signals_raises_when_no_common_case():
    signal_scores = {
        "a": {"c1": {"score": 0.1, "threshold": 0.0, "technical_failure": False}},
        "b": {"c2": {"score": 0.1, "threshold": 0.0, "technical_failure": False}},
    }
    with pytest.raises(PipelineError, match="Nenhum caso comum"):
        align_signals(signal_scores, [_case("c1", "POSITIVE"), _case("c2", "NEGATIVE")])


def test_feature_vector_is_signed_margin_and_none_on_failure():
    signal_scores = {
        "a": {"c1": {"score": 0.8, "threshold": 0.5, "technical_failure": False}},
        "b": {"c1": {"score": 0.2, "threshold": 0.5, "technical_failure": False}},
    }
    vector = _feature_vector("c1", signal_scores, ["a", "b"])
    assert vector is not None
    assert list(vector) == pytest.approx([0.3, -0.3])

    failed_scores = {
        "a": {"c1": {"score": 0.8, "threshold": 0.5, "technical_failure": True}},
        "b": {"c1": {"score": 0.2, "threshold": 0.5, "technical_failure": False}},
    }
    assert _feature_vector("c1", failed_scores, ["a", "b"]) is None

    fallback = _feature_vector(
        "c1", failed_scores, ["a", "b"], "zero_margin_with_indicator"
    )
    assert fallback is not None
    assert list(fallback) == pytest.approx([0.0, -0.3, 1.0, 0.0])


def test_feature_vector_rejects_case_when_every_signal_is_missing():
    failed = {
        "a": {"c": {"score": None, "threshold": 0.5, "technical_failure": True}},
        "b": {"c": {"score": None, "threshold": 0.5, "technical_failure": True}},
    }
    assert _feature_vector("c", failed, ["a", "b"], "zero_margin_with_indicator") is None


def test_score_correlation_perfect_positive():
    signal_scores = {
        "a": {f"c{i}": {"score": float(i), "threshold": 0.0, "technical_failure": False} for i in range(5)},
        "b": {f"c{i}": {"score": float(i) * 2.0, "threshold": 0.0, "technical_failure": False} for i in range(5)},
    }
    correlation = score_correlation(signal_scores, "a", "b")
    assert correlation == pytest.approx(1.0)


def test_score_correlation_none_when_insufficient_overlap():
    signal_scores = {
        "a": {"c1": {"score": 0.1, "threshold": 0.0, "technical_failure": False}},
        "b": {"c1": {"score": 0.1, "threshold": 0.0, "technical_failure": False}},
    }
    assert score_correlation(signal_scores, "a", "b") is None


def test_fit_meta_model_rejects_single_class_training_set():
    signal_scores = {
        "a": {"c1": {"score": 0.1, "threshold": 0.0, "technical_failure": False},
              "c2": {"score": 0.2, "threshold": 0.0, "technical_failure": False}},
    }
    label_map = {"c1": 1, "c2": 1}
    with pytest.raises(PipelineError, match="duas classes"):
        _fit_meta_model(["c1", "c2"], signal_scores, ["a"], label_map, c_value=1.0, seed=1, max_iter=200)


def test_fit_meta_model_learns_a_separable_boundary():
    signal_scores = {
        "a": {
            "pos1": {"score": 5.0, "threshold": 0.0, "technical_failure": False},
            "pos2": {"score": 4.5, "threshold": 0.0, "technical_failure": False},
            "neg1": {"score": -5.0, "threshold": 0.0, "technical_failure": False},
            "neg2": {"score": -4.5, "threshold": 0.0, "technical_failure": False},
        },
    }
    label_map = {"pos1": 1, "pos2": 1, "neg1": 0, "neg2": 0}
    model = _fit_meta_model(
        ["pos1", "pos2", "neg1", "neg2"], signal_scores, ["a"], label_map, c_value=1.0, seed=1, max_iter=500
    )
    from dtwin.learning.multi_signal_fusion import _meta_scores

    scores = _meta_scores(model, ["pos1", "neg1"], signal_scores, ["a"])
    assert scores["pos1"] > 0.5
    assert scores["neg1"] < 0.5


def test_confusion_counts_technical_failure_as_error_on_correct_axis():
    scores = {"p": None, "n": 0.9}
    label_map = {"p": 1, "n": 0}
    result = _confusion(["p", "n"], scores, label_map, threshold=0.5)
    assert result["fn"] == 1  # missing positive counts as false negative
    assert result["fp"] == 1  # negative predicted positive
    assert result["technical_failures"] == 1


def test_best_threshold_prefers_balanced_operating_point():
    scores = {"p1": 0.9, "p2": 0.6, "n1": 0.4, "n2": 0.1}
    label_map = {"p1": 1, "p2": 1, "n1": 0, "n2": 0}
    threshold, metrics = _best_threshold(["p1", "p2", "n1", "n2"], scores, label_map)
    assert metrics["sensitivity"] == 1.0
    assert metrics["specificity"] == 1.0
    assert 0.4 < threshold <= 0.6


def test_restrict_splits_preserves_fold_membership_and_drops_missing_cases():
    splits = {
        "schema": "argos-hybrid-nested-splits-v1",
        "seed": 1,
        "outer_fold_count": 2,
        "inner_fold_count": 1,
        "case_count": 4,
        "patient_group_count": 4,
        "outer_folds": [
            {
                "outer_fold": 0,
                "train_case_ids": ["c3", "c4"],
                "test_case_ids": ["c1", "c2"],
                "inner_folds": [
                    {"inner_fold": 0, "train_case_ids": ["c3"], "validation_case_ids": ["c4"]}
                ],
            },
            {
                "outer_fold": 1,
                "train_case_ids": ["c1", "c2"],
                "test_case_ids": ["c3", "c4"],
                "inner_folds": [
                    {"inner_fold": 0, "train_case_ids": ["c1"], "validation_case_ids": ["c2"]}
                ],
            },
        ],
    }
    restricted = _restrict_splits_to_case_universe(splits, {"c1", "c3", "c4"})
    fold0 = restricted["outer_folds"][0]
    assert fold0["test_case_ids"] == ["c1"]  # c2 excluded, c1 stays in its original fold
    assert fold0["train_case_ids"] == ["c3", "c4"]
    fold1 = restricted["outer_folds"][1]
    assert fold1["test_case_ids"] == ["c3", "c4"]
    assert fold1["train_case_ids"] == ["c1"]


def test_v23_style_source_loads_via_freeze_schema(tmp_path):
    from dtwin.learning.multi_signal_fusion import load_signal_scores
    from dtwin.learning.protocol import sha256_file

    root = tmp_path / "v23"
    root.mkdir()
    predictions_path = root / "loocv_predictions.jsonl"
    rows = [
        {"case_id": f"c{i}", "score": 0.1 * i, "threshold": 0.5, "status": "complete_out_of_fold_prediction"}
        for i in range(132)
    ]
    predictions_path.write_text(
        "".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8"
    )
    summary = {
        "schema": "argos-v23-retrospective-phase4-prediction-freeze-v1",
        "status": "phase4_patient_level_oof_predictions_frozen",
        "threshold_fit_on_outer_training_only": True,
        "technical_failures_must_count_as_errors_during_evaluation": True,
        "artifacts": {"loocv_predictions_sha256": sha256_file(predictions_path)},
    }
    (root / "summary.json").write_text(json.dumps(summary), encoding="utf-8")
    scores = load_signal_scores(
        root,
        prediction_schema="unused",
        freeze_schema="argos-v23-retrospective-phase4-prediction-freeze-v1",
    )
    assert len(scores) == 132
    assert scores["c0"]["score"] == pytest.approx(0.0)
