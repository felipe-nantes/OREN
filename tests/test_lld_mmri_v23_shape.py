from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
import SimpleITK as sitk

from dtwin.benchmark.lld_mmri_v23_shape import (
    BRANCH_ALGORITHM_VERSION,
    build_lld_mmri_v23_shape_branch,
    compute_lld_mmri_v23_candidate_shape,
)
from dtwin.benchmark.openswisshcc_alignment import _sha256
from dtwin.core import PipelineError


def _images():
    shape = (12, 32, 32)
    z, y, x = np.indices(shape)
    base = 40.0 + 0.2 * x + 0.1 * y + 0.05 * z
    arterial = base * 1.02
    venous = base.copy()
    delayed = base * 0.99
    hotspot = (z - 6) ** 2 + (y - 16) ** 2 + (x - 17) ** 2 <= 9
    arterial[hotspot] += 50.0
    delayed[hotspot] -= 20.0
    mask = np.zeros(shape, dtype=np.uint8)
    mask[:, 3:29, 3:29] = 1

    def image(array):
        result = sitk.GetImageFromArray(array)
        result.SetSpacing((1.5, 1.5, 2.0))
        return result

    return image(arterial.astype(np.float32)), image(venous.astype(np.float32)), image(delayed.astype(np.float32)), image(mask)


def test_candidate_shape_uses_frozen_t3_top5_branch():
    arterial, venous, delayed, mask = _images()
    candidate, result = compute_lld_mmri_v23_candidate_shape(
        arterial=arterial,
        venous=venous,
        delayed=delayed,
        liver_mask=mask,
    )
    assert result["branch_algorithm_version"] == BRANCH_ALGORITHM_VERSION
    assert result["proposal_threshold_key"] == "t3"
    assert result["maximum_components"] == 5
    assert result["features"]["candidate_present"] == 1
    assert result["valid_multiphase_liver_fraction"] == 1.0
    assert 0.0 <= result["features"]["candidate_weighted_linearity"] <= 1.0
    assert np.asarray(sitk.GetArrayFromImage(candidate)).sum() > 0


def test_candidate_shape_rejects_dynamic_geometry_mismatch():
    arterial, venous, delayed, mask = _images()
    arterial.SetOrigin((2.0, 0.0, 0.0))
    with pytest.raises(PipelineError, match="Geometrias"):
        compute_lld_mmri_v23_candidate_shape(
            arterial=arterial,
            venous=venous,
            delayed=delayed,
            liver_mask=mask,
        )


def test_shape_branch_persists_label_blind_features(tmp_path: Path):
    case_id = "anon-lld-0000000000000000"
    prepared = tmp_path / "prepared"
    case = prepared / "inputs" / case_id
    case.mkdir(parents=True)
    arterial, venous, delayed, mask = _images()
    files = []
    for role, image in (
        ("t1_arterial", arterial),
        ("t1_venous", venous),
        ("t1_delayed", delayed),
        ("liver_mask_venous", mask),
    ):
        path = case / f"{role}.nii.gz"
        sitk.WriteImage(image, str(path), useCompression=True)
        files.append(
            {
                "role": role,
                "relative_path": f"{case_id}/{path.name}",
                "bytes": path.stat().st_size,
                "sha256": _sha256(path),
            }
        )
    (prepared / "inputs.jsonl").write_text(
        json.dumps(
            {
                "case_id": case_id,
                "files": files,
                "dynamic_liver_support_fraction": {
                    "t1_native": 1.0,
                    "t1_arterial": 1.0,
                    "t1_venous": 1.0,
                    "t1_delayed": 0.75,
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )
    output = tmp_path / "shape"
    result = build_lld_mmri_v23_shape_branch(
        context={
            "protocol_case_count": 2,
            "case_ids": [case_id],
            "technical_failure_case_count": 1,
            "technical_failure_case_ids": ["anon-lld-9999999999999999"],
            "technical_failures_count_as_primary_metric_errors": True,
            "review_signature": "r" * 64,
        },
        prepared_root=prepared,
        output_root=output,
    )
    assert result["case_count"] == 1
    assert result["protocol_case_count"] == 2
    assert result["technical_failure_case_count"] == 1
    assert result["labels_read"] is False
    assert result["ground_truth_lesion_masks_read"] == 0
    row = json.loads((output / "features.jsonl").read_text(encoding="utf-8"))
    assert row["candidate_mask_is_deterministic_enhancement"] is True
    assert row["partial_dynamic_fov_roles"] == ["t1_delayed"]
    assert 0.0 < row["valid_multiphase_liver_fraction"] <= 1.0
    assert row["ground_truth_read"] is False
    assert (output / row["candidate_mask"]).is_file()
