from __future__ import annotations

import pytest

from dtwin.benchmark.openswisshcc_v20_fusion import V11_WEIGHTS
from dtwin.benchmark.openswisshcc_v24_planarity_contrast import (
    WEIGHT_GRID,
    _candidate_scores,
    _nested_loocv,
    _select_weight_nested,
    planarity_contrast,
)
from dtwin.core import PipelineError


def _rows(count: int) -> list[dict]:
    return [
        {
            "case_id": f"anon-{index:03d}",
            "signals": {name: 0.0 for name in V11_WEIGHTS},
        }
        for index in range(count)
    ]


def test_planarity_contrast_is_exact_and_label_free():
    assert planarity_contrast({
        "candidate_weighted_planarity": 0.7,
        "candidate_weighted_linearity": 0.2,
    }) == pytest.approx(0.5)


def test_planarity_contrast_rejects_invalid_geometry():
    with pytest.raises(PipelineError, match=r"fora de \[0, 1\]"):
        planarity_contrast({
            "candidate_weighted_planarity": 1.2,
            "candidate_weighted_linearity": 0.2,
        })


def test_candidate_weight_must_be_predeclared():
    with pytest.raises(PipelineError, match="grade predefinida"):
        _candidate_scores(
            _rows(2), [0.0, 0.0], [0.0, 1.0], [0], [1], 0.07
        )


def test_weight_selection_does_not_read_excluded_case():
    rows = _rows(20)
    linearity = [0.5] * 20
    contrast = [float(index) / 20.0 for index in range(20)]
    truth = [index >= 10 for index in range(20)]
    train = list(range(19))
    first = _select_weight_nested(
        rows=rows,
        linearity=linearity,
        contrast=contrast,
        truth=truth,
        train_indices=train,
    )
    contrast[19] = -999.0
    truth[19] = not truth[19]
    second = _select_weight_nested(
        rows=rows,
        linearity=linearity,
        contrast=contrast,
        truth=truth,
        train_indices=train,
    )
    assert first == second


def test_predeclared_grid_includes_anchor_and_bounded_extensions():
    assert WEIGHT_GRID == (0.0, 0.05, 0.10, 0.15, 0.20)


def test_nested_loocv_is_deterministic():
    rows = _rows(20)
    linearity = [0.5] * 20
    contrast = [float(index) / 20.0 for index in range(20)]
    truth = [index >= 10 for index in range(20)]
    first = _nested_loocv(rows, linearity, contrast, truth)
    second = _nested_loocv(rows, linearity, contrast, truth)
    assert first == second
