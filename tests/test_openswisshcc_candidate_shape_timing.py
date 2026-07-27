from dtwin.benchmark.openswisshcc_candidate_shape_timing import _percentile_higher


def test_percentile_higher_is_conservative():
    assert _percentile_higher([1.0, 2.0, 3.0, 4.0], 0.95) == 4.0
    assert _percentile_higher([4.0, 1.0, 3.0, 2.0], 0.50) == 2.0
