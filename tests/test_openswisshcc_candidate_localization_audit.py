import json
import zipfile
from pathlib import Path

import numpy as np
import pytest
import SimpleITK as sitk

from dtwin.benchmark import openswisshcc_candidate_localization_audit as audit
from dtwin.core import PipelineError


def _image(*, origin=(0.0, 0.0, 0.0), direction=None):
    image = sitk.Image([8, 7, 6], sitk.sitkUInt8)
    image.SetSpacing((1.25, 1.25, 3.0))
    image.SetOrigin(origin)
    if direction is not None:
        image.SetDirection(direction)
    return image


def test_manual_mask_alignment_accepts_only_header_roundoff():
    reference = _image()
    accepted = _image(origin=(0.0002, 0.0, 0.0))
    rejected = _image(origin=(0.002, 0.0, 0.0))

    assert audit._manual_mask_index_aligned(accepted, reference)
    assert not audit._manual_mask_index_aligned(rejected, reference)


def test_manual_mask_alignment_rejects_size_and_spacing_changes():
    reference = _image()
    wrong_size = sitk.Image([9, 7, 6], sitk.sitkUInt8)
    wrong_size.SetSpacing(reference.GetSpacing())
    wrong_spacing = _image()
    wrong_spacing.SetSpacing((1.251, 1.25, 3.0))

    assert not audit._manual_mask_index_aligned(wrong_size, reference)
    assert not audit._manual_mask_index_aligned(wrong_spacing, reference)


def test_component_matching_uses_volume_and_centroid_not_source_id():
    candidate = np.zeros((3, 5, 5), dtype=bool)
    candidate[0, 0, 0] = True
    candidate[2, 3, 3:5] = True
    manifest = {
        "features": {
            "components": [
                {
                    "component_id": 99,
                    "rank_by_volume": 2,
                    "voxels": 1,
                    "centroid_index_xyz": [0.0, 0.0, 0.0],
                },
                {
                    "component_id": 77,
                    "rank_by_volume": 1,
                    "voxels": 2,
                    "centroid_index_xyz": [3.5, 3.0, 2.0],
                },
            ]
        }
    }

    labels, rank_to_id = audit._component_labels(candidate, manifest)

    assert int((labels == rank_to_id[1]).sum()) == 2
    assert int((labels == rank_to_id[2]).sum()) == 1


def test_component_matching_rejects_changed_centroid():
    candidate = np.zeros((2, 2, 2), dtype=bool)
    candidate[0, 0, 0] = True
    manifest = {
        "features": {
            "components": [
                {
                    "component_id": 1,
                    "rank_by_volume": 1,
                    "voxels": 1,
                    "centroid_index_xyz": [1.0, 0.0, 0.0],
                }
            ]
        }
    }

    with pytest.raises(PipelineError, match="Volume/centro"):
        audit._component_labels(candidate, manifest)


def test_actual_visibility_is_exact_union_of_rendered_venous_regions(tmp_path):
    case_dir = tmp_path / "anon-case"
    candidate_dir = case_dir / "candidate_001"
    candidate_dir.mkdir(parents=True)
    candidate_manifest = {
        "groups": [
            {
                "role": "t1_venous",
                "selected_source_indices_z": [1, 3],
                "crop_bbox_yxyx": [2, 5, 1, 4],
            }
        ]
    }
    manifest_path = candidate_dir / "manifest.json"
    manifest_path.write_text(json.dumps(candidate_manifest), encoding="utf-8")
    case_manifest = {
        "candidate_stacks": [
            {
                "relative_directory": "candidate_001",
                "manifest_sha256": audit._sha256(manifest_path),
            }
        ]
    }
    (case_dir / "case_manifest.json").write_text(json.dumps(case_manifest), encoding="utf-8")

    visible = audit._actual_venous_visibility(case_dir, (5, 7, 8))

    assert int(visible.sum()) == 18
    assert visible[1, 2, 1]
    assert visible[3, 4, 3]
    assert not visible[2, 3, 2]
    assert not visible[1, 5, 1]


def test_holdout_path_is_always_rejected(tmp_path):
    with pytest.raises(PipelineError, match="holdout"):
        audit._refuse_holdout(tmp_path / "holdout" / "mask.nii.gz")


def test_wilson_and_empty_metric_are_deterministic():
    assert audit._metric(0, 0)["fraction"] is None
    metric = audit._metric(21, 37)
    assert metric["fraction"] == pytest.approx(21 / 37)
    assert metric["wilson_95_fraction"] == pytest.approx([0.4091418109, 0.7132828072])


def test_extraction_supports_multiple_masks_and_excludes_unrequested(tmp_path, monkeypatch):
    archive_path = tmp_path / "derivatives.zip"
    names = [
        "derivatives/manual_lesion_annotations/sub-001/dyn/sub-001_acq-water_phase-venous_T1w-L1_seg.nii.gz",
        "derivatives/manual_lesion_annotations/sub-001/dyn/sub-001_acq-water_phase-venous_T1w-L2_seg.nii.gz",
    ]
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr(names[0], b"mask-one")
        archive.writestr(names[1], b"mask-two")
        archive.writestr("derivatives/manual_lesion_annotations/sub-001/anat/unrequested.nii.gz", b"no")
    monkeypatch.setattr(audit, "EXPECTED_ARCHIVE_MD5", audit._md5(archive_path))
    protocol = {
        "schema": audit.PROTOCOL_SCHEMA,
        "archive": {"sha256": audit._sha256(archive_path)},
        "safety": {"holdout_opened": False, "development_only": True},
        "cases": [
            {
                "case_id": "anon-case",
                "venous_masks": [
                    {"lesion_id": "L1", "archive_member": names[0]},
                    {"lesion_id": "L2", "archive_member": names[1]},
                ],
            }
        ],
    }
    protocol["protocol_signature"] = audit._canonical_sha(protocol)
    protocol_path = tmp_path / "protocol.json"
    protocol_path.write_text(json.dumps(protocol), encoding="utf-8")

    result = audit.extract_authorized_venous_masks(
        archive_path=archive_path,
        protocol_path=protocol_path,
        output_root=tmp_path / "extracted",
    )

    assert result["mask_count"] == 2
    assert (tmp_path / "extracted" / "anon-case" / "L1_t1_venous_seg.nii.gz").read_bytes() == b"mask-one"
    assert (tmp_path / "extracted" / "anon-case" / "L2_t1_venous_seg.nii.gz").read_bytes() == b"mask-two"
    assert not list((tmp_path / "extracted").rglob("*unrequested*"))
