from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import SimpleITK as sitk

from dtwin.benchmark.lld_mmri_v23_mask_quality import (
    anatomically_gated_segmenter,
    evaluate_liver_mask_quality,
)
from dtwin.core import PipelineError


def _image(array: np.ndarray, spacing=(2.0, 2.0, 3.0)) -> sitk.Image:
    image = sitk.GetImageFromArray(array)
    image.SetSpacing(spacing)
    return image


def test_gate_accepts_plausible_connected_liver(tmp_path: Path):
    array = np.zeros((50, 100, 100), dtype=np.uint8)
    array[10:40, 20:80, 20:85] = 1
    mask = _image(array)
    path = tmp_path / "mask.nii.gz"
    sitk.WriteImage(mask, str(path), useCompression=True)
    quality = evaluate_liver_mask_quality(path, mask)
    assert quality["gate_passed"] is True
    assert quality["largest_component_volume_ml"] > 300
    assert quality["largest_component_fraction"] == 1.0


def test_gate_rejects_tiny_fragmented_mask(tmp_path: Path):
    array = np.zeros((50, 100, 100), dtype=np.uint8)
    array[5:8, 5:10, 5:10] = 1
    array[30:32, 70:75, 70:75] = 1
    mask = _image(array)
    path = tmp_path / "mask.nii.gz"
    sitk.WriteImage(mask, str(path), useCompression=True)
    quality = evaluate_liver_mask_quality(path, mask)
    assert quality["gate_passed"] is False
    assert "physical_volume_below_minimum" in quality["failure_reasons"]
    assert "excessive_fragmentation" in quality["failure_reasons"]


def test_gated_segmenter_removes_small_remote_island(tmp_path: Path):
    source_array = np.ones((50, 100, 100), dtype=np.float32)
    source = _image(source_array)
    source_path = tmp_path / "source.nii.gz"
    destination = tmp_path / "mask.nii.gz"
    sitk.WriteImage(source, str(source_path), useCompression=True)

    def segmenter(_source: Path, output: Path):
        array = np.zeros((50, 100, 100), dtype=np.uint8)
        array[10:40, 20:80, 20:85] = 1
        array[1, 1, 1] = 1
        mask = _image(array)
        sitk.WriteImage(mask, str(output), useCompression=True)
        return {"engine": "synthetic"}

    receipt = anatomically_gated_segmenter(
        source_path, destination, segmenter=segmenter
    )
    result = sitk.GetArrayFromImage(sitk.ReadImage(str(destination))) > 0
    assert result[1, 1, 1] == 0
    assert receipt["postprocessing"] == "largest_3d_connected_component_only"


def test_gated_segmenter_deletes_rejected_mask(tmp_path: Path):
    source = _image(np.ones((20, 30, 30), dtype=np.float32))
    source_path = tmp_path / "source.nii.gz"
    destination = tmp_path / "mask.nii.gz"
    sitk.WriteImage(source, str(source_path), useCompression=True)

    def segmenter(_source: Path, output: Path):
        mask = _image(np.ones((2, 2, 2), dtype=np.uint8))
        sitk.WriteImage(mask, str(output), useCompression=True)
        return {}

    with pytest.raises(PipelineError, match="gate anatomico"):
        anatomically_gated_segmenter(source_path, destination, segmenter=segmenter)
    assert not destination.exists()
