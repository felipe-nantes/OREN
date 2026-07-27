from dtwin.benchmark.lld_mmri_v23_external import _case_id


def test_lld_case_id_is_deterministic_and_anonymous():
    first = _case_id("MR-123456")
    assert first == _case_id("MR-123456")
    assert first.startswith("anon-lld-")
    assert "123456" not in first
    assert first != _case_id("MR-123457")
