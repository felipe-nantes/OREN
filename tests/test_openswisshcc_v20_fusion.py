from __future__ import annotations

import pytest

from dtwin.benchmark import openswisshcc_v20_fusion as fusion
from dtwin.core import PipelineError


def _rows() -> list[dict]:
    return [
        {
            "case_id": f"case-{index}",
            "signals": {
                name: float(index) + offset / 10
                for offset, name in enumerate(fusion.WEIGHTS)
            },
        }
        for index in range(10)
    ]


def test_weights_preserve_v11_ratio_and_add_twenty_percent_rag():
    assert sum(fusion.WEIGHTS.values()) == pytest.approx(1.0)
    assert fusion.WEIGHTS[fusion.V19_SIGNAL] == 0.20
    assert fusion.WEIGHTS["medgemma_v4_uncertainty_margin"] == 0.32
    assert fusion.WEIGHTS["medsiglip_v5_inverse_sagittal"] == 0.32
    assert fusion.WEIGHTS["localizer_v10_log_volume"] == 0.16


def test_fold_scores_fit_ecdf_only_on_training_indices():
    rows = _rows()
    scores = fusion._fold_scores(rows, list(range(8)), [8, 9], fusion.WEIGHTS)
    assert scores == [1.0, 1.0]


def test_loocv_ordered_signal_is_strong_and_deterministic():
    rows = _rows()
    truth = [False] * 5 + [True] * 5
    result = fusion._loocv(rows, truth, fusion.WEIGHTS)
    assert result["sensitivity"] == 1.0
    assert result["specificity"] >= 0.8
    assert len(result["scores"]) == len(rows)
    assert result == fusion._loocv(rows, truth, fusion.WEIGHTS)


def test_repeated_validation_is_fully_nested():
    rows = _rows() * 2
    for index, row in enumerate(rows):
        row = {**row, "case_id": f"case-{index}"}
        rows[index] = row
    truth = [False] * 10 + [True] * 10
    result = fusion._repeated(rows, truth)
    assert result["repeats"] == 50
    assert result["folds"] == 5
    assert result["transform_and_threshold_fit_inside_each_training_fold"] is True


def test_invalid_empty_ecdf_reference_fails_closed():
    with pytest.raises(PipelineError):
        fusion._ecdf(1.0, [])
