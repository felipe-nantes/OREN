import numpy as np
import pytest
from PIL import Image

from dtwin.core import PipelineError, sha256_of
from dtwin.medgemma_spotlight import (
    attenuate_outside_liver,
    render_uniform_spotlight_panel,
)


def test_attenuation_preserves_liver_and_dims_only_context():
    image = np.array([[0.0, 10.0], [20.0, 30.0]], dtype=np.float32)
    mask = np.array([[False, True], [False, True]])
    result = attenuate_outside_liver(
        image, mask, window_low=0.0, outside_fraction=0.2
    )
    assert result[0, 1] == 10.0
    assert result[1, 1] == 30.0
    assert result[0, 0] == 0.0
    assert result[1, 0] == 4.0


@pytest.mark.parametrize("value", [-0.01, 0.51, True, "0.1"])
def test_attenuation_rejects_invalid_fraction(value):
    with pytest.raises(PipelineError, match="outside_fraction"):
        attenuate_outside_liver(
            np.ones((2, 2)),
            np.ones((2, 2), dtype=bool),
            window_low=0.0,
            outside_fraction=value,
        )


def test_spotlight_panel_is_deterministic_and_has_no_metadata_or_yellow_contour(
    synthetic_case, tmp_path
):
    first = render_uniform_spotlight_panel(
        volume_path=synthetic_case.volume,
        liver_mask_path=synthetic_case.mask_organ,
        output_path=tmp_path / "first.png",
    )
    second = render_uniform_spotlight_panel(
        volume_path=synthetic_case.volume,
        liver_mask_path=synthetic_case.mask_organ,
        output_path=tmp_path / "second.png",
    )
    assert first.panel_sha256 == sha256_of(first.panel_path)
    assert first.panel_sha256 == second.panel_sha256
    assert len(first.axial_indices) == 9
    with Image.open(first.panel_path) as image:
        assert image.size == (1280, 960)
        assert image.mode == "RGB"
        assert image.info == {}
        pixels = np.asarray(image)
    assert not np.any(np.all(pixels == np.array([255, 196, 0]), axis=2))
