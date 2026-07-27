from __future__ import annotations

import pytest

from dtwin.benchmark.openswisshcc_axial_atlas_chunk_evaluation import _finite
from dtwin.core import PipelineError


@pytest.mark.parametrize("value", [0, 1.5, -2.0])
def test_finite_accepts_real_scores(value):
    assert _finite(value) == float(value)


@pytest.mark.parametrize("value", [True, float("nan"), float("inf"), "1"])
def test_finite_rejects_non_numeric_or_non_finite(value):
    with pytest.raises(PipelineError):
        _finite(value)
