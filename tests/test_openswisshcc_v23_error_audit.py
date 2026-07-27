from __future__ import annotations

from dtwin.benchmark.openswisshcc_v23_error_audit import (
    _audit_flags,
    _finite,
    _shape_rank_band,
    _transition,
)
from dtwin.core import PipelineError
import pytest


def test_transition_classifies_corrections_and_regressions():
    assert _transition(truth=True, v11_prediction=False, v23_prediction=True) == (
        "corrected_by_v23_shape_fusion"
    )
    assert _transition(truth=False, v11_prediction=False, v23_prediction=True) == (
        "introduced_by_v23_shape_fusion"
    )
    assert _transition(truth=True, v11_prediction=False, v23_prediction=False) == (
        "persistent_error_from_v11"
    )
    assert _transition(truth=False, v11_prediction=False, v23_prediction=False) == (
        "correct_in_v11_and_v23"
    )


def test_shape_rank_bands_are_predeclared_quartiles():
    assert _shape_rank_band(0.75) == "upper_quartile_more_linear"
    assert _shape_rank_band(0.25) == "lower_quartile_less_linear"
    assert _shape_rank_band(0.5) == "middle_half"


def test_audit_flags_are_descriptive_and_do_not_change_prediction():
    flags = _audit_flags(
        v23_margin=-0.01,
        shape_percentile=0.8,
        candidate_present=0,
        transition="persistent_error_from_v11",
    )
    assert flags == [
        "persistent_error_from_v11",
        "upper_quartile_more_linear",
        "near_v23_threshold",
        "no_automatic_candidate",
    ]


def test_non_finite_audit_value_fails_closed():
    with pytest.raises(PipelineError, match="não é finito"):
        _finite("nan", "score")
