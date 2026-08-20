from __future__ import annotations

import json

import pytest

import dtwin.benchmark.v23_retrospective_multicohort_phase4 as subject
from dtwin.core import PipelineError


def _signal(a: float, b: float, c: float, shape: float) -> dict:
    return {
        "v11_signals": {
            "medgemma_v4_uncertainty_margin": a,
            "medsiglip_v5_inverse_sagittal": b,
            "localizer_v10_log_volume": c,
        },
        "candidate_weighted_linearity": shape,
    }


def _pred(case_id: str, prediction: str, score: float | None = None) -> dict:
    return {
        "case_id": case_id,
        "prediction": prediction,
        "score": score,
    }


def test_references_use_only_training_ids():
    signals = {
        "a": _signal(1, 2, 3, 0.1),
        "b": _signal(4, 5, 6, 0.2),
        "held": _signal(999, 999, 999, 0.99),
    }
    result = subject._references(signals, ["a", "b"])
    assert result["medgemma_v4_uncertainty_margin"] == [1.0, 4.0]
    assert result["candidate_weighted_linearity"] == [0.1, 0.2]
    assert 999 not in result["medgemma_v4_uncertainty_margin"]


def test_score_preserves_frozen_80_20_weights():
    signals = {
        "low": _signal(0, 0, 0, 0),
        "high": _signal(1, 1, 1, 1),
    }
    refs = subject._references(signals, ["low", "high"])
    assert subject._score(signals["high"], refs) == pytest.approx(0.75)
    assert subject._score(signals["low"], refs) == pytest.approx(0.25)


def test_fit_threshold_receives_training_truth_only(monkeypatch):
    signals = {
        "p": _signal(1, 1, 1, 1),
        "n": _signal(0, 0, 0, 0),
        "held": _signal(0.5, 0.5, 0.5, 0.5),
    }
    folds = {
        "p": {"label": "POSITIVE"},
        "n": {"label": "NEGATIVE"},
        "held": {"label": "POSITIVE"},
    }
    seen: dict = {}

    def fake(scores, truth):
        seen["scores"] = scores
        seen["truth"] = truth
        return 0.6, {}

    monkeypatch.setattr(subject, "_best_threshold", fake)
    refs = subject._references(signals, ["p", "n"])
    threshold = subject._fit_threshold(
        signals=signals,
        folds=folds,
        training_ids=["p", "n"],
        references=refs,
    )
    assert threshold == 0.6
    assert seen["truth"] == [True, False]
    assert len(seen["scores"]) == 2


def test_technical_failure_is_error_for_each_class():
    rows = [
        _pred("p-ok", "POSITIVE"),
        _pred("p-fail", "TECHNICAL_FAILURE"),
        _pred("n-ok", "NEGATIVE"),
        _pred("n-fail", "TECHNICAL_FAILURE"),
    ]
    labels = {
        "p-ok": "POSITIVE",
        "p-fail": "POSITIVE",
        "n-ok": "NEGATIVE",
        "n-fail": "NEGATIVE",
    }
    result = subject._confusion(rows, labels)
    assert (result["tp"], result["fn"], result["tn"], result["fp"]) == (1, 1, 1, 1)
    assert result["technical_failures_counted_as_errors"] == 2
    assert result["sensitivity"] == result["specificity"] == 0.5


def test_roc_auc_handles_ties_and_excludes_undefined_scores():
    rows = [
        _pred("p1", "POSITIVE", 0.8),
        _pred("p2", "POSITIVE", 0.5),
        _pred("n1", "NEGATIVE", 0.5),
        _pred("n2", "TECHNICAL_FAILURE", None),
    ]
    labels = {"p1": "POSITIVE", "p2": "POSITIVE", "n1": "NEGATIVE", "n2": "NEGATIVE"}
    result = subject._roc_auc(rows, labels)
    assert result["roc_auc"] == pytest.approx(0.75)
    assert result["computable_case_count"] == 3


def test_bootstrap_is_deterministic(monkeypatch):
    monkeypatch.setattr(subject, "BOOTSTRAP_REPLICATES", 100)
    rows = [
        _pred("p1", "POSITIVE"),
        _pred("p2", "NEGATIVE"),
        _pred("n1", "NEGATIVE"),
        _pred("n2", "POSITIVE"),
    ]
    labels = {"p1": "POSITIVE", "p2": "POSITIVE", "n1": "NEGATIVE", "n2": "NEGATIVE"}
    assert subject._bootstrap(rows, labels) == subject._bootstrap(rows, labels)


def test_prediction_record_never_contains_label():
    row = subject._prediction(
        schema=subject.LOOCV_SCHEMA,
        case_id="anon-a",
        score=None,
        threshold=None,
        status="technical_failure_count_as_error",
        extra={"outer_fold_id": "anon-a"},
    )
    assert row["prediction"] == "TECHNICAL_FAILURE"
    assert "label" not in row
    assert row["held_out_label_used_for_threshold"] is False


def test_fold_rows_reject_invalid_assignment_count(tmp_path):
    path = tmp_path / "protected_ground_truth/fold_assignments.jsonl"
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps(
            {
                "case_id": "anon-a",
                "label": "POSITIVE",
                "repeated_5fold_outer_assignments": [0],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    with pytest.raises(PipelineError, match="atribuição"):
        subject._fold_rows(tmp_path, 1)


def test_confusion_gate_requires_both_metrics():
    rows = [
        _pred("p1", "POSITIVE"),
        _pred("p2", "POSITIVE"),
        _pred("n1", "POSITIVE"),
        _pred("n2", "NEGATIVE"),
    ]
    labels = {"p1": "POSITIVE", "p2": "POSITIVE", "n1": "NEGATIVE", "n2": "NEGATIVE"}
    result = subject._confusion(rows, labels)
    assert result["sensitivity"] == 1.0
    assert result["specificity"] == 0.5
    assert result["passed_75_75"] is False
