from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
import SimpleITK as sitk

from dtwin.benchmark.liver_mask_phase_fusion import fuse_arrays, verify_fusion
from dtwin.core import PipelineError, sha256_of


def _phases(shape=(9, 9, 9)) -> dict[str, np.ndarray]:
    result = {}
    for name in ("native", "arterial", "venous", "delayed"):
        array = np.zeros(shape, dtype=np.uint8)
        array[2:7, 2:7, 2:7] = 1
        result[name] = array
    return result


def test_majority_requires_two_phases() -> None:
    phases = _phases()
    phases["native"][0, 0, 0] = 1
    phases["arterial"][7, 6, 6] = 1
    phases["delayed"][7, 6, 6] = 1
    fused = fuse_arrays(phases, policy="majority_2_of_4", spacing_xyz=(1, 1, 1))
    assert not fused[0, 0, 0]
    assert fused[7, 6, 6]


def test_guarded_union_fills_internal_hole_and_rejects_far_island() -> None:
    phases = _phases(shape=(21, 21, 21))
    for array in phases.values():
        array[4:17, 4:17, 4:17] = 1
        array[10, 10, 10] = 0
    phases["native"][0, 0, 0] = 1
    fused = fuse_arrays(
        phases,
        policy="venous_guarded_union_fill_12mm",
        spacing_xyz=(2, 2, 2),
    )
    assert fused[10, 10, 10]
    assert not fused[0, 0, 0]


def test_venous_fill_uses_only_venous_and_fills_hole() -> None:
    phases = _phases(shape=(21, 21, 21))
    phases["venous"][4:17, 4:17, 4:17] = 1
    phases["venous"][10, 10, 10] = 0
    phases["native"][:] = 0
    phases["arterial"][:] = 0
    phases["delayed"][:] = 0
    phases["native"][0:2, 0:2, 0:2] = 1
    fused = fuse_arrays(
        phases,
        policy="venous_fill_largest",
        spacing_xyz=(1, 1, 1),
    )
    assert fused[10, 10, 10]
    assert not fused[0, 0, 0]


def test_rejects_missing_phase_and_unknown_policy() -> None:
    phases = _phases()
    phases.pop("native")
    with pytest.raises(PipelineError):
        fuse_arrays(phases, policy="majority_2_of_4", spacing_xyz=(1, 1, 1))
    with pytest.raises(PipelineError):
        fuse_arrays(_phases(), policy="union", spacing_xyz=(1, 1, 1))


def test_verify_detects_changed_mask(tmp_path: Path) -> None:
    root = tmp_path / "fusion"
    (root / "masks").mkdir(parents=True)
    image = sitk.GetImageFromArray(np.ones((2, 2, 2), dtype=np.uint8))
    mask = root / "masks" / "case-a.nii.gz"
    sitk.WriteImage(image, str(mask))
    row = {
        "case_id": "case-a",
        "mask_sha256": sha256_of(mask),
        "ground_truth_read": False,
        "lesion_masks_read": 0,
    }
    receipts = root / "cases.jsonl"
    receipts.write_text(json.dumps(row) + "\n", encoding="utf-8")
    summary = {
        "schema": "argos-liver-mask-phase-fusion-v1",
        "policy": "majority_2_of_4",
        "case_ids": ["case-a"],
        "case_count": 1,
        "completed_cases": 1,
        "receipts_sha256": sha256_of(receipts),
    }
    (root / "run_summary.json").write_text(json.dumps(summary), encoding="utf-8")
    assert verify_fusion(root)["completed_cases"] == 1
    sitk.WriteImage(sitk.GetImageFromArray(np.zeros((2, 2, 2), dtype=np.uint8)), str(mask))
    with pytest.raises(PipelineError, match="adulterada"):
        verify_fusion(root)
