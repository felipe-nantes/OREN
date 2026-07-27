from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
import SimpleITK as sitk

from dtwin.benchmark import openswisshcc_axial_atlas_audit as audit
from dtwin.benchmark.openswisshcc_axial_atlas import (
    CASE_SCHEMA,
    COHORT_SCHEMA,
    PROTOCOL_SIGNATURE,
)
from dtwin.core import PipelineError


def test_mask_audit_distinguishes_any_from_full_visibility() -> None:
    mask = np.zeros((6, 8, 9), dtype=bool)
    mask[1, 3, 3] = True
    mask[2, 3, 3] = True
    mask[2, 7, 8] = True
    result = audit.audit_mask_array(
        mask,
        represented_axial_indices=[1, 2, 3],
        crop_bounds_zyx=[[1, 5], [2, 7], [2, 8]],
        spacing_xyz=[1.0, 1.0, 2.0],
    )
    assert result["any_voxel_visible"] is True
    assert result["all_voxels_visible"] is False
    assert result["visible_voxels"] == 2
    assert result["visible_fraction"] == pytest.approx(2 / 3)
    assert result["all_lesion_axial_indices_represented"] is True


def test_mask_audit_can_prove_exact_full_coverage() -> None:
    mask = np.zeros((5, 6, 7), dtype=bool)
    mask[1:4, 2:4, 2:5] = True
    result = audit.audit_mask_array(
        mask,
        represented_axial_indices=[1, 2, 3],
        crop_bounds_zyx=[[0, 5], [1, 5], [1, 6]],
        spacing_xyz=[1.0, 1.0, 1.0],
    )
    assert result["all_voxels_visible"] is True
    assert result["visible_fraction"] == 1.0
    assert result["lesion_axial_indices"] == [1, 2, 3]


@pytest.mark.parametrize(
    "represented,crop,error",
    [
        ([1, 1], [[0, 5], [0, 6], [0, 7]], "duplicados"),
        ([1], [[0, 7], [0, 6], [0, 7]], "fora dos limites"),
        ([1], [[0, 5], [3, 3], [0, 7]], "fora dos limites"),
    ],
)
def test_mask_audit_rejects_invalid_geometry(represented, crop, error) -> None:
    mask = np.zeros((5, 6, 7), dtype=bool)
    mask[1, 2, 2] = True
    with pytest.raises(PipelineError, match=error):
        audit.audit_mask_array(
            mask,
            represented_axial_indices=represented,
            crop_bounds_zyx=crop,
            spacing_xyz=[1.0, 1.0, 1.0],
        )


def test_holdout_is_always_rejected(tmp_path: Path) -> None:
    with pytest.raises(PipelineError, match="holdout"):
        audit._refuse_holdout(tmp_path / "holdout" / "masks")


def test_wilson_metric_is_deterministic() -> None:
    assert audit._metric(0, 0)["fraction"] is None
    metric = audit._metric(3, 4)
    assert metric["fraction"] == 0.75
    assert metric["wilson_95_fraction"] == pytest.approx(
        [0.3006418426, 0.9544127392]
    )


def test_fallback_crop_reconstruction_matches_panel_algorithm() -> None:
    mask = np.zeros((10, 12), dtype=bool)
    mask[3:7, 4:9] = True
    # spans 4x5, margin 30% -> ceil(1.2)=2 minimum and ceil(1.5)=2
    assert audit._mask_bbox_2d(mask, 0.3) == (1, 9, 2, 11)


def _write_freeze_fixture(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    atlas_root = tmp_path / "atlas"
    source_root = tmp_path / "source"
    input_root = tmp_path / "inputs"
    atlas_root.mkdir()
    records = []
    input_rows = []
    for index in range(87):
        case_id = f"anon-openswiss-{index:016x}"
        case_atlas = atlas_root / case_id
        case_source = source_root / case_id
        case_atlas.mkdir()
        case_source.mkdir(parents=True)
        source_manifest = {"crop_bounds_zyx": [[0, 3], [0, 4], [0, 5]]}
        source_path = case_source / "medgemma_liver_screening_manifest.json"
        source_path.write_text(json.dumps(source_manifest), encoding="utf-8")
        atlas_manifest = {
            "schema_version": CASE_SCHEMA,
            "source": {"panel_manifest_sha256": audit._sha256(source_path)},
            "atlas": {
                "represented_axial_indices": [0, 1, 2],
                "expected_axial_indices": [0, 1, 2],
            },
        }
        atlas_path = case_atlas / "axial_atlas_manifest.json"
        atlas_path.write_text(json.dumps(atlas_manifest), encoding="utf-8")
        reference_relative = f"{case_id}/dyn/t1_venous.nii.gz"
        reference = input_root / reference_relative
        reference.parent.mkdir(parents=True)
        reference.write_bytes(f"reference-{index}".encode())
        records.append(
            {
                "case_id": case_id,
                "manifest": f"{case_id}/axial_atlas_manifest.json",
                "manifest_sha256": audit._sha256(atlas_path),
                "atlas_set_sha256": f"{index:064x}",
            }
        )
        input_rows.append(
            {
                "case_id": case_id,
                "split": "development",
                "files": [
                    {
                        "role": "t1_venous",
                        "relative_path": reference_relative,
                        "sha256": audit._sha256(reference),
                    }
                ],
            }
        )
    cohort = {
        "schema_version": COHORT_SCHEMA,
        "protocol_signature": PROTOCOL_SIGNATURE,
        "case_count": 87,
        "all_gates_passed": True,
        "ground_truth_read": False,
        "lesion_mask_read": False,
        "holdout_read": False,
        "cases": records,
    }
    (atlas_root / "cohort_manifest.json").write_text(
        json.dumps(cohort), encoding="utf-8"
    )
    input_manifest = tmp_path / "development_inputs.jsonl"
    input_manifest.write_text(
        "\n".join(json.dumps(row) for row in input_rows) + "\n", encoding="utf-8"
    )
    return atlas_root, source_root, input_manifest, input_root


def test_freeze_reads_no_lesion_mask_or_label(tmp_path: Path) -> None:
    atlas_root, source_root, input_manifest, input_root = _write_freeze_fixture(tmp_path)
    protocol = audit.freeze_protocol(
        atlas_root=atlas_root,
        source_panel_root=source_root,
        input_manifest_path=input_manifest,
        input_root=input_root,
        output_path=tmp_path / "protocol.json",
    )
    assert protocol["case_count"] == 87
    assert protocol["safety"]["lesion_mask_read_during_freeze"] is False
    assert protocol["safety"]["ground_truth_label_read"] is False
    assert protocol["safety"]["holdout_opened"] is False
    assert len(protocol["protocol_signature"]) == 64


def _write_image(path: Path, array: np.ndarray, *, origin=(0.0, 0.0, 0.0)) -> None:
    image = sitk.GetImageFromArray(array.astype(np.uint8))
    image.SetSpacing((1.0, 1.0, 2.0))
    image.SetOrigin(origin)
    path.parent.mkdir(parents=True, exist_ok=True)
    sitk.WriteImage(image, str(path))


def _write_run_fixture(
    tmp_path: Path, *, shifted_mask: bool = False
) -> tuple[Path, Path, Path, Path]:
    case_id = "anon-openswiss-test0001"
    input_root = tmp_path / "inputs"
    reference_path = input_root / case_id / "dyn" / "t1_venous.nii.gz"
    reference_array = np.zeros((5, 6, 7), dtype=np.uint8)
    _write_image(reference_path, reference_array)
    mask = np.zeros_like(reference_array)
    mask[1:3, 2:4, 2:4] = 1
    mask_root = tmp_path / "authorized_masks"
    mask_path = mask_root / case_id / "L1_t1_venous_seg.nii.gz"
    _write_image(
        mask_path,
        mask,
        origin=(0.002, 0.0, 0.0) if shifted_mask else (0.0, 0.0, 0.0),
    )
    protocol = {
        "schema_version": audit.PROTOCOL_SCHEMA,
        "cases": [
            {
                "case_id": case_id,
                "represented_axial_indices": [1, 2, 3],
                "crop_bounds_zyx": [[0, 5], [1, 5], [1, 6]],
                "reference_relative_path": f"{case_id}/dyn/t1_venous.nii.gz",
                "reference_sha256": audit._sha256(reference_path),
            }
        ],
    }
    protocol["protocol_signature"] = audit._canonical_sha(protocol)
    protocol_path = tmp_path / "protocol.json"
    protocol_path.write_text(json.dumps(protocol), encoding="utf-8")
    extraction_manifest = mask_root / "extraction_manifest.json"
    extraction_manifest.write_text(
        json.dumps(
            {
                "schema": audit.AUTHORIZED_EXTRACTION_SCHEMA,
                "mask_count": 1,
                "masks": [
                    {
                        "case_id": case_id,
                        "lesion_id": "L1",
                        "relative_path": f"{case_id}/L1_t1_venous_seg.nii.gz",
                        "bytes": mask_path.stat().st_size,
                        "sha256": audit._sha256(mask_path),
                    }
                ],
                "safety": {
                    "retrospective_only": True,
                    "inference_executed": False,
                    "medgemma_called": False,
                    "lesion_masks_used_for_inference": False,
                    "lesion_masks_sent_to_medgemma": False,
                    "holdout_opened": False,
                    "development_only": True,
                },
            }
        ),
        encoding="utf-8",
    )
    return protocol_path, mask_root, extraction_manifest, input_root


def test_run_audit_persists_exact_metrics_and_safety(tmp_path: Path) -> None:
    protocol, masks, extraction, inputs = _write_run_fixture(tmp_path)
    report = audit.run_audit(
        protocol_path=protocol,
        authorized_mask_root=masks,
        extraction_manifest_path=extraction,
        input_root=inputs,
        output_root=tmp_path / "out",
    )
    assert report["summary"]["lesion_count"] == 1
    assert report["summary"]["lesion_full_voxel_coverage"]["percent"] == 100.0
    assert report["safety"]["medgemma_called"] is False
    assert report["safety"]["holdout_opened"] is False
    assert (tmp_path / "out" / "audit_report.json").is_file()
    assert (tmp_path / "out" / "lesion_rows.csv").is_file()


def test_run_audit_never_resamples_shifted_mask(tmp_path: Path) -> None:
    protocol, masks, extraction, inputs = _write_run_fixture(
        tmp_path, shifted_mask=True
    )
    with pytest.raises(PipelineError, match="desalinhada"):
        audit.run_audit(
            protocol_path=protocol,
            authorized_mask_root=masks,
            extraction_manifest_path=extraction,
            input_root=inputs,
            output_root=tmp_path / "out",
        )


def test_run_audit_rejects_mask_not_listed_in_authorized_manifest(
    tmp_path: Path,
) -> None:
    protocol, masks, extraction, inputs = _write_run_fixture(tmp_path)
    extra = masks / "anon-openswiss-test0001" / "L2_t1_venous_seg.nii.gz"
    _write_image(extra, np.ones((5, 6, 7), dtype=np.uint8))
    with pytest.raises(PipelineError, match="extras ou ausentes"):
        audit.run_audit(
            protocol_path=protocol,
            authorized_mask_root=masks,
            extraction_manifest_path=extraction,
            input_root=inputs,
            output_root=tmp_path / "out",
        )
