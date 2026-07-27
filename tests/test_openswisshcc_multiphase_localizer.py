from __future__ import annotations

from pathlib import Path

import nibabel as nib
import numpy as np
import pytest

from dtwin.benchmark.openswisshcc_multiphase_localizer import (
    combine_candidate_masks,
)
from dtwin.core import PipelineError


def _write(path: Path, data: np.ndarray, affine: np.ndarray | None = None) -> Path:
    nib.save(
        nib.Nifti1Image(data.astype(np.uint8), np.eye(4) if affine is None else affine),
        path,
    )
    return path


def test_candidate_union_is_exact_and_reports_new_arterial_voxels(tmp_path: Path):
    venous = np.zeros((5, 5, 5), dtype=np.uint8)
    arterial = np.zeros_like(venous)
    venous[1, 1, 1] = 1
    arterial[1, 1, 1] = 1
    arterial[3, 3, 3] = 1
    output = tmp_path / "union.nii.gz"
    result = combine_candidate_masks(
        venous_candidate_path=_write(tmp_path / "ven.nii.gz", venous),
        arterial_candidate_path=_write(tmp_path / "art.nii.gz", arterial),
        output_path=output,
    )
    assert result == {
        "venous_voxels": 1,
        "arterial_voxels": 2,
        "intersection_voxels": 1,
        "union_voxels": 2,
        "new_arterial_voxels": 1,
    }
    assert int((np.asarray(nib.load(output).dataobj) > 0).sum()) == 2


def test_candidate_union_rejects_geometry_mismatch(tmp_path: Path):
    data = np.zeros((5, 5, 5), dtype=np.uint8)
    shifted = np.eye(4)
    shifted[0, 3] = 2.0
    with pytest.raises(PipelineError, match="Geometria"):
        combine_candidate_masks(
            venous_candidate_path=_write(tmp_path / "ven.nii.gz", data),
            arterial_candidate_path=_write(tmp_path / "art.nii.gz", data, shifted),
            output_path=tmp_path / "union.nii.gz",
        )
