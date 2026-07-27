from pathlib import Path

import pytest
from PIL import Image

from dtwin.benchmark.openswisshcc_slice_pairwise import crop_axial_tiles
from dtwin.core import PipelineError


def test_crop_axial_tiles_preserves_first_n_grid_cells(tmp_path: Path):
    tile = 32
    panel = Image.new("RGB", (tile * 4, tile * 3), "black")
    colors = [(index * 20, index * 10, 255 - index * 20) for index in range(9)]
    for index, color in enumerate(colors):
        patch = Image.new("RGB", (tile, tile), color)
        panel.paste(patch, ((index % 3) * tile, (index // 3) * tile))
    path = tmp_path / "panel.png"
    panel.save(path)
    crops = crop_axial_tiles(path, [10, 11, 12, 13, 14])
    assert [index for index, _ in crops] == [10, 11, 12, 13, 14]
    assert all(crop.size == (tile, tile) for _, crop in crops)
    assert [crop.getpixel((5, 5)) for _, crop in crops] == colors[:5]


@pytest.mark.parametrize("indices", [[], list(range(10)), [1, 1]])
def test_crop_axial_tiles_rejects_invalid_indices(tmp_path: Path, indices):
    path = tmp_path / "panel.png"
    Image.new("RGB", (128, 96)).save(path)
    with pytest.raises(PipelineError):
        crop_axial_tiles(path, indices)


def test_crop_axial_tiles_rejects_non_square_grid_cells(tmp_path: Path):
    path = tmp_path / "panel.png"
    Image.new("RGB", (128, 90)).save(path)
    with pytest.raises(PipelineError):
        crop_axial_tiles(path, [1])
