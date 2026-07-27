from __future__ import annotations

import numpy as np

from dtwin.benchmark.openswisshcc_enhancement_proposal_selection import select_top_components


def test_selects_exactly_five_largest_components_deterministically():
    mask = np.zeros((20, 30, 30), dtype=bool)
    for index, size in enumerate((2, 3, 4, 5, 6, 7, 8)):
        mask[index * 2, 2:2 + size, 2:4] = True
    selected, records = select_top_components(mask, maximum=5)
    assert len(records) == 5
    assert [item["voxels"] for item in records] == [16, 14, 12, 10, 8]
    assert int(selected.sum()) == 60
