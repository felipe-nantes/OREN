from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
import SimpleITK as sitk

from dtwin.benchmark.openswisshcc_alignment import _sha256
from dtwin.benchmark.openswisshcc_enhancement_maps import (
    ALGORITHM_VERSION,
    CASE_SCHEMA,
    COHORT_SCHEMA,
    build_enhancement_feature_cohort,
    compute_enhancement_features,
)
from dtwin.core import PipelineError


def _image(array: np.ndarray, *, origin=(0.0, 0.0, 0.0)) -> sitk.Image:
    image = sitk.GetImageFromArray(np.asarray(array, dtype=np.float32))
    image.SetSpacing((1.5, 1.5, 2.0))
    image.SetOrigin(origin)
    return image


def _synthetic(*, hotspot: bool = True):
    shape = (12, 32, 32)
    z, y, x = np.indices(shape)
    base = 50.0 + 0.2 * x + 0.1 * y + 0.05 * z
    venous = base.copy()
    arterial = base * 1.05
    delayed = base * 0.98
    if hotspot:
        region = (z - 6) ** 2 + (y - 16) ** 2 + (x - 17) ** 2 <= 9
        arterial[region] += 45.0
        delayed[region] -= 18.0
    mask = np.zeros(shape, dtype=np.float32)
    mask[:, 3:29, 3:29] = 1.0
    return _image(arterial), _image(venous), _image(delayed), _image(mask)


def test_hotspot_increases_joint_enhancement_and_creates_component():
    hot_images = _synthetic(hotspot=True)
    hot = compute_enhancement_features(
        arterial=hot_images[0],
        venous=hot_images[1],
        delayed=hot_images[2],
        liver_mask=hot_images[3],
    )
    normal_images = _synthetic(hotspot=False)
    normal = compute_enhancement_features(
        arterial=normal_images[0],
        venous=normal_images[1],
        delayed=normal_images[2],
        liver_mask=normal_images[3],
    )
    assert hot["algorithm_version"] == ALGORITHM_VERSION
    assert hot["features"]["joint_enhancement_q99"] > normal["features"]["joint_enhancement_q99"]
    assert hot["features"]["largest_component_voxels_ge_3"] > 0
    assert hot["features"]["largest_component_center_lps_xyz"] is not None


def test_geometry_mismatch_is_rejected():
    arterial, venous, delayed, mask = _synthetic()
    delayed.SetOrigin((1.0, 0.0, 0.0))
    with pytest.raises(PipelineError, match="Geometrias"):
        compute_enhancement_features(
            arterial=arterial, venous=venous, delayed=delayed, liver_mask=mask
        )


def test_constant_phase_is_rejected():
    arterial, venous, delayed, mask = _synthetic()
    arterial = _image(np.ones((12, 32, 32), dtype=np.float32) * 5.0)
    with pytest.raises(PipelineError, match="variacao robusta"):
        compute_enhancement_features(
            arterial=arterial, venous=venous, delayed=delayed, liver_mask=mask
        )


def _write_image(path: Path, image: sitk.Image) -> dict:
    path.parent.mkdir(parents=True, exist_ok=True)
    sitk.WriteImage(image, str(path), useCompression=True)
    return {"bytes": path.stat().st_size, "sha256": _sha256(path)}


def test_cohort_builder_is_label_free_and_declares_unregistered_fallback(tmp_path: Path):
    case_registered = "anon-registered"
    case_fallback = "anon-fallback"
    case_ids = [case_registered, case_fallback] + [f"anon-fill-{i:03d}" for i in range(85)]
    inputs = tmp_path / "inputs"
    manifest_rows = []
    images = _synthetic()
    for case_id in case_ids:
        files = []
        for role, image, relative in (
            ("t1_venous", images[1], f"{case_id}/t1_venous.nii.gz"),
            ("liver_mask_venous", images[3], f"{case_id}/liver_mask_venous.nii.gz"),
        ):
            info = _write_image(inputs / relative, image)
            files.append({"role": role, "relative_path": relative, **info})
        manifest_rows.append(
            {
                "schema": "argos-public-liver-mri-input-v1",
                "case_id": case_id,
                "files": files,
                "research_only": True,
                "clinical_use_allowed": False,
            }
        )
    manifest = tmp_path / "inputs.jsonl"
    manifest.write_text(
        "".join(json.dumps(row) + "\n" for row in manifest_rows), encoding="utf-8"
    )
    selection = tmp_path / "selection.json"
    selection.write_text(
        json.dumps(
            {
                "schema": "argos-openswisshcc-candidate-volume-cohort-v16",
                "case_count": 87,
                "cases": [
                    {
                        "case_id": case_id,
                        "dynamic_alignment_mode": (
                            "registered_to_venous"
                            if case_id == case_registered
                            else "original_unregistered_physical_center"
                        ),
                    }
                    for case_id in case_ids
                ],
            }
        ),
        encoding="utf-8",
    )
    alignment = tmp_path / "alignment" / case_registered
    art_info = _write_image(alignment / "art.nii.gz", images[0])
    del_info = _write_image(alignment / "del.nii.gz", images[2])
    (alignment / "alignment_manifest.json").write_text(
        json.dumps(
            {
                "schema": "argos-public-liver-mri-alignment-v1",
                "case_id": case_registered,
                "reference_phase": "venous",
                "outputs": [
                    {"phase": "art", "filename": "art.nii.gz", **art_info},
                    {"phase": "del", "filename": "del.nii.gz", **del_info},
                ],
                "research_only": True,
                "clinical_use_allowed": False,
            }
        ),
        encoding="utf-8",
    )
    out = tmp_path / "out"
    result = build_enhancement_feature_cohort(
        input_manifest_path=manifest,
        input_root=inputs,
        alignment_root=tmp_path / "alignment",
        selection_manifest_path=selection,
        output_dir=out,
    )
    assert result["schema"] == COHORT_SCHEMA
    assert result["case_count"] == 87
    assert result["available_case_count"] == 1
    assert result["unavailable_case_count"] == 86
    assert result["labels_read"] is False
    rows = [json.loads(line) for line in (out / "features.jsonl").read_text().splitlines()]
    assert rows[0]["schema"] == CASE_SCHEMA
    assert rows[0]["status"] == "complete_blind_features"
    assert rows[0]["ground_truth_lesion_mask_used"] is False
    assert rows[1]["status"] == "unavailable_unregistered_fallback"
    assert "label" not in json.dumps(rows).lower()
