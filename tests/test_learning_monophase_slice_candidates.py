from __future__ import annotations

import os

import numpy as np
import pytest

import dtwin.learning.monophase_slice_candidates as slice_module
from dtwin.core import PipelineError
from dtwin.learning.monophase_slice_candidates import (
    case_intensity_window,
    is_proven_label_blind_input,
    liver_slice_indices,
    liver_xy_bbox,
    publish_immutable_directory,
    render_axial_candidate,
)


def test_public_holdout_contract_is_label_blind_only_without_forbidden_roles():
    row = {
        "schema": "argos-public-liver-mri-holdout-input-v1",
        "split": "holdout_blind",
        "research_only": True,
        "clinical_use_allowed": False,
        "files": [
            {"role": "t1_delayed", "relative_path": "case/dyn/t1_delayed.nii.gz"},
            {"role": "liver_mask_venous", "relative_path": "case/masks/liver.nii.gz"},
        ],
    }
    assert is_proven_label_blind_input(row) is True
    row["files"].append(
        {"role": "lesion_mask", "relative_path": "case/masks/lesion.nii.gz"}
    )
    assert is_proven_label_blind_input(row) is False


def test_untyped_manifest_requires_explicit_label_blind_flags():
    assert is_proven_label_blind_input({"research_only": True, "files": []}) is False
    assert is_proven_label_blind_input(
        {"ground_truth_read": False, "lesion_mask_present": False}
    ) is True


@pytest.mark.skipif(
    os.name != "nt",
    reason="fallback de publicação só existe sob os.name=='nt' (monophase_slice_candidates.py); em POSIX o PermissionError simulado propaga por construção",
)
def test_windows_publish_fallback_copies_manifest_last_and_verifies_hashes(
    tmp_path, monkeypatch
):
    staging = tmp_path / "staging"
    destination = tmp_path / "published"
    (staging / "nested").mkdir(parents=True)
    (staging / "nested/image.png").write_bytes(b"image")
    (staging / "dataset_manifest.json").write_text("{}\n", encoding="utf-8")
    original_replace = slice_module.os.replace

    def fail_directory_replace(source, target):
        if source == staging:
            raise PermissionError("simulated Windows directory lock")
        return original_replace(source, target)

    monkeypatch.setattr(slice_module.os, "replace", fail_directory_replace)
    publish_immutable_directory(staging, destination)
    assert not staging.exists()
    assert (destination / "nested/image.png").read_bytes() == b"image"
    assert (destination / "dataset_manifest.json").read_text() == "{}\n"


@pytest.mark.parametrize("indices", [[2], [1, 2, 3, 4, 5], list(range(9)), list(range(10)), list(range(40))])
def test_every_liver_slice_is_selected_exactly_once(indices):
    mask = np.zeros((45, 20, 20), dtype=bool)
    for index in indices:
        mask[index, 3:8, 4:9] = True
    assert liver_slice_indices(mask) == indices
    covered = sum(int(mask[index].sum()) for index in liver_slice_indices(mask))
    assert covered == int(mask.sum())


def test_empty_intervals_do_not_create_fake_slices():
    mask = np.zeros((12, 8, 8), dtype=bool)
    mask[2, 1:3, 1:3] = True
    mask[9, 1:3, 1:3] = True
    assert liver_slice_indices(mask) == [2, 9]


def test_bbox_has_margin_and_stays_in_bounds():
    mask = np.zeros((2, 10, 12), dtype=bool)
    mask[:, 1:9, 2:11] = True
    assert liver_xy_bbox(mask, 0.5) == (0, 10, 0, 12)


def test_window_uses_only_liver_and_is_case_level():
    volume = np.full((2, 4, 4), 10000.0, dtype=np.float32)
    mask = np.zeros_like(volume, dtype=bool)
    mask[:, 1:3, 1:3] = True
    volume[mask] = np.arange(8, dtype=np.float32) + 10
    low, high = case_intensity_window(volume, mask)
    assert 9 < low < high < 18


def test_render_is_exact_rgb_grayscale_and_448():
    plane = np.arange(100, dtype=np.float32).reshape(10, 10)
    image = render_axial_candidate(plane, (1, 9, 2, 8), (0.0, 99.0), 448)
    assert image.mode == "RGB"
    assert image.size == (448, 448)
    array = np.asarray(image)
    assert np.array_equal(array[..., 0], array[..., 1])
    assert np.array_equal(array[..., 1], array[..., 2])


def test_empty_mask_and_degenerate_window_fail_closed():
    with pytest.raises(PipelineError, match="vazia"):
        liver_xy_bbox(np.zeros((2, 2, 2), dtype=bool), 0.1)
    with pytest.raises(PipelineError, match="degenerada"):
        case_intensity_window(np.ones((2, 2, 2)), np.ones((2, 2, 2), dtype=bool))
