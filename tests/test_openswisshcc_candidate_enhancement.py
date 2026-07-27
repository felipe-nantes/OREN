from __future__ import annotations

import numpy as np
import pytest
import SimpleITK as sitk

from dtwin.benchmark.openswisshcc_candidate_enhancement import (
    ALGORITHM_VERSION,
    compute_candidate_enhancement_features,
)
from dtwin.core import PipelineError


def _image(array: np.ndarray, *, spacing=(1.5, 1.5, 2.0)) -> sitk.Image:
    image = sitk.GetImageFromArray(array)
    image.SetSpacing(spacing)
    return image


def _sources(*, candidate: bool = True):
    shape = (12, 24, 24)
    z, y, x = np.indices(shape)
    base = (40.0 + 0.2 * x + 0.3 * y + 0.4 * z).astype(np.float32)
    liver = np.zeros(shape, dtype=np.uint8)
    liver[1:11, 2:22, 2:22] = 1
    mask = np.zeros(shape, dtype=np.uint8)
    if candidate:
        mask[5:8, 10:14, 10:14] = 1
    arterial = base.copy()
    venous = base.copy() + 2.0
    delayed = base.copy() + 1.0
    arterial[mask > 0] += 25.0
    delayed[mask > 0] -= 5.0
    return tuple(
        _image(array)
        for array in (arterial, venous, delayed, liver, mask)
    )


def test_candidate_enhancement_detects_dynamic_signal_without_labels():
    arterial, venous, delayed, liver, candidate = _sources()
    result = compute_candidate_enhancement_features(
        arterial=arterial,
        venous=venous,
        delayed=delayed,
        liver_mask=liver,
        candidate_mask=candidate,
    )
    features = result["features"]
    assert result["algorithm_version"] == ALGORITHM_VERSION
    assert features["candidate_present"] == 1
    assert features["candidate_component_count"] == 1
    assert features["candidate_total_voxels"] == 48
    assert features["arterial_over_delayed_core_mean"] > 1.0
    assert features["core_aphe_washout_fraction"] > 0.9
    assert not any("label" in key or "lesion" in key for key in features)


def test_absent_candidate_is_retained_with_neutral_features():
    arterial, venous, delayed, liver, candidate = _sources(candidate=False)
    result = compute_candidate_enhancement_features(
        arterial=arterial,
        venous=venous,
        delayed=delayed,
        liver_mask=liver,
        candidate_mask=candidate,
    )
    features = result["features"]
    assert features["candidate_present"] == 0
    assert features["candidate_total_voxels"] == 0
    assert features["joint_enhancement_core_q95"] == 0.0


def test_candidate_outside_shared_multiphase_fov_is_retained():
    arterial, venous, delayed, liver, candidate = _sources()
    mask = sitk.GetArrayFromImage(candidate) > 0
    arterial_array = sitk.GetArrayFromImage(arterial)
    delayed_array = sitk.GetArrayFromImage(delayed)
    arterial_array[mask] = 0.0
    delayed_array[mask] = 0.0
    result = compute_candidate_enhancement_features(
        arterial=_image(arterial_array),
        venous=venous,
        delayed=_image(delayed_array),
        liver_mask=liver,
        candidate_mask=candidate,
    )
    features = result["features"]
    assert features["candidate_present"] == 1
    assert features["candidate_total_voxels"] == 48
    assert features["candidate_shared_fov_voxels"] == 0
    assert features["candidate_shared_fov_fraction"] == 0.0
    assert features["joint_enhancement_core_q95"] == 0.0


def test_candidate_outside_liver_is_rejected():
    arterial, venous, delayed, liver, candidate = _sources()
    array = sitk.GetArrayFromImage(candidate)
    array[0, 0, 0] = 1
    outside = _image(array)
    with pytest.raises(PipelineError, match="saiu do figado"):
        compute_candidate_enhancement_features(
            arterial=arterial,
            venous=venous,
            delayed=delayed,
            liver_mask=liver,
            candidate_mask=outside,
        )


def test_candidate_geometry_mismatch_is_rejected():
    arterial, venous, delayed, liver, candidate = _sources()
    candidate.SetOrigin((3.0, 0.0, 0.0))
    with pytest.raises(PipelineError, match="Geometria"):
        compute_candidate_enhancement_features(
            arterial=arterial,
            venous=venous,
            delayed=delayed,
            liver_mask=liver,
            candidate_mask=candidate,
        )
