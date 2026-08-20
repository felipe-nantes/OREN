import importlib.util
from pathlib import Path

import pytest

_PATH = Path(__file__).parents[1] / "tools" / "download_http_ranges.py"
_SPEC = importlib.util.spec_from_file_location("download_http_ranges", _PATH)
assert _SPEC and _SPEC.loader
module = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(module)


def test_split_ranges_covers_every_byte_exactly_once():
    ranges = module.split_ranges(10, 4)
    assert ranges == [(0, 2), (3, 5), (6, 8), (9, 9)]
    represented = [value for start, end in ranges for value in range(start, end + 1)]
    assert represented == list(range(10))


def test_split_ranges_supports_more_workers_than_bytes():
    assert module.split_ranges(3, 8) == [(0, 0), (1, 1), (2, 2)]


@pytest.mark.parametrize("total,workers", [(0, 1), (1, 0), (-1, 2)])
def test_split_ranges_rejects_invalid_values(total, workers):
    with pytest.raises(ValueError):
        module.split_ranges(total, workers)
