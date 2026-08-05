from __future__ import annotations

import numpy as np
import pytest

from dtwin.core import PipelineError
from dtwin.learning.localized_candidate_supervision import (
    _render_localized_patch,
    cover_component_with_boxes,
    lesion_visibility_in_box,
)


def _union(shape, boxes):
    result = np.zeros(shape, dtype=bool)
    for box in boxes:
        (z0, z1), (y0, y1), (x0, x1) = box["bounds_zyx_exclusive"]
        result[z0:z1, y0:y1, x0:x1] = True
    return result


def test_localized_boxes_cover_every_automatic_voxel_deterministically():
    component = np.zeros((11, 80, 90), dtype=bool)
    component[1:10, 5:75, 7:86] = True
    first = cover_component_with_boxes(
        component, (1.0, 1.0, 3.0), crop_mm=32.0, visible_slices=5
    )
    second = cover_component_with_boxes(
        component, (1.0, 1.0, 3.0), crop_mm=32.0, visible_slices=5
    )
    assert first == second
    assert np.all(~component | _union(component.shape, first))
    assert all(item["automatic_proposal_voxels_in_box"] > 0 for item in first)


def test_localized_boxes_remain_inside_small_volume():
    component = np.ones((3, 8, 7), dtype=bool)
    boxes = cover_component_with_boxes(
        component, (2.0, 2.0, 4.0), crop_mm=64.0, visible_slices=7
    )
    assert len(boxes) == 1
    assert boxes[0]["bounds_zyx_exclusive"] == [[0, 3], [0, 8], [0, 7]]


def test_lesion_target_corresponds_to_visible_box_content():
    lesion = np.zeros((7, 20, 20), dtype=bool)
    lesion[3, 10:12, 10:12] = True
    visible, fraction = lesion_visibility_in_box(
        lesion, [[2, 5], [8, 15], [8, 15]]
    )
    assert visible == 4
    assert fraction == 1.0
    hidden, hidden_fraction = lesion_visibility_in_box(
        lesion, [[0, 2], [0, 8], [0, 8]]
    )
    assert hidden == 0
    assert hidden_fraction == 0.0


@pytest.mark.parametrize("visible_slices", [0, 2, 4])
def test_invalid_visible_slice_contract_fails_closed(visible_slices):
    component = np.ones((3, 3, 3), dtype=bool)
    with pytest.raises(PipelineError):
        cover_component_with_boxes(
            component, (1.0, 1.0, 1.0), visible_slices=visible_slices
        )


def test_empty_automatic_component_is_rejected():
    with pytest.raises(PipelineError):
        cover_component_with_boxes(np.zeros((3, 3, 3), dtype=bool), (1, 1, 1))


def test_rendered_localized_patch_contains_seven_dynamic_tiles_without_metadata():
    phases = {
        "arterial": np.full((7, 8, 8), 255, dtype=np.uint8),
        "venous": np.full((7, 8, 8), 128, dtype=np.uint8),
        "delayed": np.zeros((7, 8, 8), dtype=np.uint8),
    }
    image = _render_localized_patch(phases, [[0, 7], [0, 8], [0, 8]])
    assert image.size == (448, 448)
    assert image.mode == "RGB"
    assert image.getpixel((20, 20)) == (255, 128, 0)
    image.close()
