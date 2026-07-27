from __future__ import annotations

import numpy as np
import pytest
import SimpleITK as sitk

from dtwin.benchmark.openswisshcc_candidate_shape import (
    ALGORITHM_VERSION,
    compute_candidate_shape_features,
)
from dtwin.core import PipelineError


def _image(array: np.ndarray, spacing=(1.0, 1.0, 1.0)) -> sitk.Image:
    image = sitk.GetImageFromArray(array.astype(np.uint8))
    image.SetSpacing(spacing)
    return image


def test_empty_candidate_is_explicit_and_finite():
    result = compute_candidate_shape_features(_image(np.zeros((12, 12, 12))))
    assert result["algorithm_version"] == ALGORITHM_VERSION
    assert result["features"]["candidate_present"] == 0
    assert result["features"]["candidate_weighted_linearity"] == 0.0


def test_tube_is_more_linear_than_compact_cube():
    tube = np.zeros((24, 24, 24), dtype=np.uint8)
    tube[11:14, 11:14, 2:22] = 1
    cube = np.zeros_like(tube)
    cube[7:17, 7:17, 7:17] = 1
    tube_features = compute_candidate_shape_features(_image(tube))["features"]
    cube_features = compute_candidate_shape_features(_image(cube))["features"]
    assert tube_features["candidate_weighted_linearity"] > 0.8
    assert tube_features["candidate_weighted_linearity"] > cube_features["candidate_weighted_linearity"]
    assert tube_features["candidate_largest_axis_ratio"] > cube_features["candidate_largest_axis_ratio"]


def test_weighted_linearity_uses_physical_spacing():
    mask = np.zeros((12, 12, 12), dtype=np.uint8)
    mask[3:9, 3:9, 3:9] = 1
    isotropic = compute_candidate_shape_features(_image(mask))["features"]
    anisotropic = compute_candidate_shape_features(_image(mask, spacing=(4.0, 1.0, 1.0)))["features"]
    assert anisotropic["candidate_weighted_linearity"] > isotropic["candidate_weighted_linearity"]


def test_components_are_aggregated_by_voxel_count():
    mask = np.zeros((30, 30, 30), dtype=np.uint8)
    mask[2:18, 2:5, 2:5] = 1
    mask[22:27, 22:27, 22:27] = 1
    features = compute_candidate_shape_features(_image(mask))["features"]
    assert features["candidate_component_count"] == 2
    assert 0.5 < features["candidate_largest_fraction"] < 1.0
    assert features["candidate_weighted_linearity"] <= features["candidate_max_linearity"]


def test_too_small_component_fails_closed():
    mask = np.zeros((5, 5, 5), dtype=np.uint8)
    mask[1, 1, 1] = 1
    mask[1, 1, 2] = 1
    mask[1, 2, 1] = 1
    with pytest.raises(PipelineError, match="pequeno demais"):
        compute_candidate_shape_features(_image(mask))


def test_invalid_spacing_fails_closed():
    mask = np.zeros((8, 8, 8), dtype=np.uint8)
    mask[2:6, 2:6, 2:6] = 1
    image = _image(mask)
    with pytest.raises(RuntimeError):
        image.SetSpacing((1.0, 0.0, 1.0))
