from __future__ import annotations

import numpy as np

from dtwin.learning.patch25d_dataset import _render_patch, _top_components


def test_top_components_are_ordered_by_volume_and_limited():
    mask = np.zeros((5, 20, 20), dtype=bool)
    mask[1, 1:3, 1:3] = True
    mask[2, 5:10, 5:10] = True
    mask[3, 15:17, 15:18] = True
    components = _top_components(mask, 2)
    assert [int(item.sum()) for item in components] == [25, 6]


def test_patch_render_is_deterministic_448_rgb_without_overlay():
    component = np.zeros((7, 32, 32), dtype=bool)
    component[3, 14:18, 14:18] = True
    phases = {
        "arterial": np.full((7, 32, 32), 20, dtype=np.uint8),
        "venous": np.full((7, 32, 32), 80, dtype=np.uint8),
        "delayed": np.full((7, 32, 32), 140, dtype=np.uint8),
    }
    first = _render_patch(phases, component, (1.0, 1.0, 3.0), crop_mm=20, image_size=448)
    second = _render_patch(phases, component, (1.0, 1.0, 3.0), crop_mm=20, image_size=448)
    assert first.mode == "RGB"
    assert first.size == (448, 448)
    assert np.array_equal(np.asarray(first), np.asarray(second))
