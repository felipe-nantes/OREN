from __future__ import annotations

import pytest

from dtwin.benchmark.openswisshcc_v20_fusion import V11_WEIGHTS
from dtwin.benchmark.openswisshcc_v24_planarity_contrast import (
    WEIGHT_GRID,
    _candidate_scores,
    _nested_loocv,
    _select_weight_nested,
)
from dtwin.benchmark.openswisshcc_v26_bbox_fill import bbox_fill
from dtwin.core import PipelineError


def _rows(count: int) -> list[dict]:
    return [
        {
            "case_id": f"anon-{index:03d}",
            "signals": {name: 0.0 for name in V11_WEIGHTS},
        }
        for index in range(count)
    ]


def test_bbox_fill_is_exact_and_label_free():
    assert bbox_fill({"candidate_weighted_bbox_fill": 0.23}) == pytest.approx(0.23)


@pytest.mark.parametrize("value", [-0.01, 1.01, "invalid", None])
def test_bbox_fill_rejects_invalid_geometry(value):
    with pytest.raises(PipelineError):
        bbox_fill({"candidate_weighted_bbox_fill": value})


def test_candidate_weight_stays_inside_predeclared_grid():
    with pytest.raises(PipelineError, match="grade predefinida"):
        _candidate_scores(
            _rows(2),
            [0.0, 0.0],
            [0.0, 1.0],
            [0],
            [1],
            0.07,
        )
    assert WEIGHT_GRID == (0.0, 0.05, 0.10, 0.15, 0.20)


def test_weight_selection_does_not_read_excluded_case():
    rows = _rows(20)
    linearity = [0.5] * 20
    feature = [float(index) / 20.0 for index in range(20)]
    truth = [index >= 10 for index in range(20)]
    train = list(range(19))
    first = _select_weight_nested(
        rows=rows,
        linearity=linearity,
        contrast=feature,
        truth=truth,
        train_indices=train,
    )
    feature[19] = -999.0
    truth[19] = not truth[19]
    second = _select_weight_nested(
        rows=rows,
        linearity=linearity,
        contrast=feature,
        truth=truth,
        train_indices=train,
    )
    assert first == second


def test_nested_loocv_is_deterministic():
    rows = _rows(20)
    linearity = [0.5] * 20
    feature = [float(index) / 20.0 for index in range(20)]
    truth = [index >= 10 for index in range(20)]
    assert _nested_loocv(rows, linearity, feature, truth) == _nested_loocv(
        rows,
        linearity,
        feature,
        truth,
    )
