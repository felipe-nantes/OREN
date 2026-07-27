from __future__ import annotations

from dtwin.benchmark.openswisshcc_volumetric_evaluation import (
    _best_threshold,
    _binary_metrics,
    _case_signals,
    _loocv,
    _repeated_stratified_cv,
)


def test_case_signals_preserve_panel_probability_evidence():
    signals = _case_signals([
        {"POSITIVA": 0.6, "NEGATIVA": 0.3, "INCONCLUSIVA": 0.1},
        {"POSITIVA": 0.2, "NEGATIVA": 0.5, "INCONCLUSIVA": 0.3},
    ])
    assert signals["mean_positive"] == 0.4
    assert signals["max_positive"] == 0.6
    assert signals["positive_vote_fraction"] == 0.5
    assert abs(signals["mean_positive_minus_negative"] - 0.0) < 1e-12


def test_threshold_search_finds_perfect_separation_when_present():
    scores = [0.9, 0.8, 0.2, 0.1]
    truth = [True, True, False, False]
    threshold, metrics = _best_threshold(scores, truth)
    assert 0.2 < threshold < 0.8
    assert metrics["sensitivity"] == 1.0
    assert metrics["specificity"] == 1.0
    assert metrics["passed_75_75"] is True


def test_binary_metrics_uses_both_gates():
    metrics = _binary_metrics(
        [True, True, False, False],
        [True, False, False, True],
    )
    assert metrics == {
        "tp": 1, "tn": 1, "fp": 1, "fn": 1,
        "sensitivity": 0.5, "specificity": 0.5,
        "balanced_accuracy": 0.5, "minimum_gate_metric": 0.5,
        "passed_75_75": False,
    }


def test_loocv_and_repeated_cv_do_not_report_apparent_fit_only():
    scores = [0.95, 0.9, 0.85, 0.8, 0.2, 0.15, 0.1, 0.05, 0.01, 0.0]
    truth = [True, True, True, True, False, False, False, False, False, False]
    loo = _loocv(scores, truth)
    repeated = _repeated_stratified_cv(scores, truth, repeats=5, folds=2)
    assert loo["passed_75_75"] is True
    assert repeated["runs_passing_75_75"] == 5
    assert repeated["minimum_sensitivity"] >= 0.75
    assert repeated["minimum_specificity"] >= 0.75
