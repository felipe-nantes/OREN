from __future__ import annotations

import numpy as np
import pytest
import SimpleITK as sitk

from dtwin.core import PipelineError
from dtwin.learning.radiomics_features import (
    PHASES,
    extract_case_features_from_images,
)


def _image(array: np.ndarray, spacing=(1.0, 1.0, 1.0)) -> sitk.Image:
    image = sitk.GetImageFromArray(array.astype(np.float32))
    image.SetSpacing(spacing)
    return image


def _synthetic():
    shape = (20, 24, 28)
    z, y, x = np.indices(shape)
    mask = (
        ((z - 10) / 7) ** 2
        + ((y - 12) / 9) ** 2
        + ((x - 14) / 11) ** 2
        <= 1
    )
    base = 100 + x * 0.5 + y * 0.2 + z * 0.1
    focus = ((z - 10) ** 2 + (y - 12) ** 2 + (x - 14) ** 2) <= 9
    arrays = {
        "arterial": base + focus * 40,
        "venous": base + focus * 10,
        "delayed": base + focus * 2,
    }
    return {key: _image(value) for key, value in arrays.items()}, _image(mask)


def test_multiphase_features_are_deterministic_and_finite():
    phases, mask = _synthetic()
    first, audit = extract_case_features_from_images(
        phase_images=phases,
        liver_mask_image=mask,
        erosion_mm=1.0,
        local_sigma_mm=2.0,
        minimum_mask_voxels=100,
    )
    second, _ = extract_case_features_from_images(
        phase_images=phases,
        liver_mask_image=mask,
        erosion_mm=1.0,
        local_sigma_mm=2.0,
        minimum_mask_voxels=100,
    )
    assert first == second
    assert all(np.isfinite(value) for value in first.values())
    assert audit["feature_count"] == len(first)
    assert first["joint_arterial_dominance_q99"] > 0


def test_geometry_mismatch_is_rejected():
    phases, mask = _synthetic()
    phases["arterial"].SetOrigin((1.0, 0.0, 0.0))
    with pytest.raises(PipelineError, match="geometria"):
        extract_case_features_from_images(
            phase_images=phases,
            liver_mask_image=mask,
            erosion_mm=1.0,
            local_sigma_mm=2.0,
            minimum_mask_voxels=100,
        )


def test_small_mask_is_rejected():
    phases, mask = _synthetic()
    with pytest.raises(PipelineError, match="mínimo"):
        extract_case_features_from_images(
            phase_images=phases,
            liver_mask_image=mask,
            erosion_mm=1.0,
            local_sigma_mm=2.0,
            minimum_mask_voxels=100000,
        )


def test_missing_phase_is_rejected():
    phases, mask = _synthetic()
    phases.pop(PHASES[0])
    with pytest.raises(PipelineError, match="incompleto"):
        extract_case_features_from_images(
            phase_images=phases,
            liver_mask_image=mask,
            erosion_mm=1.0,
            local_sigma_mm=2.0,
            minimum_mask_voxels=100,
        )
