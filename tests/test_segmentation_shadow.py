from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
import SimpleITK as sitk

from dtwin.core import PipelineError, sha256_of
from dtwin.segmentation_shadow import (
    mask_agreement,
    protected_adaptive_fusion,
    run_phase_aware_shadow,
    select_phase_aware_source,
    should_run_secondary,
)


def _image(path: Path, *, origin=(0.0, 0.0, 0.0)) -> None:
    array = np.zeros((10, 11, 12), dtype=np.float32)
    image = sitk.GetImageFromArray(array)
    image.SetOrigin(origin)
    sitk.WriteImage(image, str(path), useCompression=True)


def test_selection_prefers_registered_arterial_and_falls_back(tmp_path: Path) -> None:
    reference = tmp_path / "reference.nii.gz"
    arterial = tmp_path / "arterial.nii.gz"
    shifted = tmp_path / "shifted.nii.gz"
    _image(reference)
    _image(arterial)
    _image(shifted, origin=(20.0, 0.0, 0.0))
    selected = select_phase_aware_source(
        phase_paths={"t1_arterial": arterial}, reference_volume=reference
    )
    assert selected["selected_phase"] == "arterial"
    assert selected["fallback_used"] is False
    fallback = select_phase_aware_source(
        phase_paths={"t1_arterial": shifted}, reference_volume=reference
    )
    assert fallback["selected_phase"] == "reference"
    assert fallback["fallback_reason"] == "arterial_geometry_not_registered"


def test_shadow_writes_only_v2_artifacts_and_preserves_production(tmp_path: Path) -> None:
    case = tmp_path / "case"
    case.mkdir()
    reference = case / "volume.nii.gz"
    arterial = case / "arterial.nii.gz"
    production_mask = case / "mask_organ.nii.gz"
    report = case / "medgemma_report.json"
    executable = tmp_path / "mrsegmentator.exe"
    executable.write_bytes(b"fake")
    _image(reference)
    _image(arterial)
    mask = np.zeros((10, 11, 12), dtype=np.uint8)
    mask[2:8, 2:9, 2:10] = 1
    mask_image = sitk.GetImageFromArray(mask)
    sitk.WriteImage(mask_image, str(production_mask), useCompression=True)
    report.write_text('{"status":"frozen"}', encoding="utf-8")
    protected = {path.name: sha256_of(path) for path in (reference, production_mask, report)}

    def fake_segmenter(**kwargs):
        destination = kwargs["staging"] / "masks" / "visualization-shadow.nii.gz"
        destination.parent.mkdir(parents=True)
        sitk.WriteImage(mask_image, str(destination), useCompression=True)
        return {"elapsed_seconds": 12.5}

    result = run_phase_aware_shadow(
        case_root=case,
        phase_paths={"t1_arterial": arterial},
        reference_volume=reference,
        mrsegmentator_exe=executable,
        segmenter=fake_segmenter,
    )
    assert result["status"] == "APPROVED"
    assert result["selection"]["selected_phase"] == "arterial"
    assert result["ground_truth_read"] is False
    assert result["lesion_masks_read"] == 0
    assert (case / "mask_organ_visualization_v2.nii.gz").is_file()
    assert (case / "segmentation_input_manifest_v2.json").is_file()
    assert (case / "segmentation_quality_manifest_v2.json").is_file()
    assert protected == {path.name: sha256_of(path) for path in (reference, production_mask, report)}
    input_manifest = json.loads(
        (case / "segmentation_input_manifest_v2.json").read_text(encoding="utf-8")
    )
    serialized = json.dumps(input_manifest)
    assert str(arterial.resolve()) not in serialized
    assert input_manifest["privacy"]["source_path_stored"] is False


def test_shadow_refuses_overwrite_and_cleans_partial_candidate(tmp_path: Path) -> None:
    case = tmp_path / "case"
    case.mkdir()
    reference = case / "reference.nii.gz"
    executable = tmp_path / "mrsegmentator.exe"
    executable.write_bytes(b"fake")
    _image(reference)
    (case / "segmentation_quality_manifest_v2.json").write_text("{}", encoding="utf-8")
    with pytest.raises(PipelineError, match="sobrescrita recusada"):
        run_phase_aware_shadow(
            case_root=case,
            phase_paths={},
            reference_volume=reference,
            mrsegmentator_exe=executable,
            segmenter=lambda **_: {},
        )


def test_protected_fusion_accepts_small_nearby_extension_and_rejects_large_growth():
    primary = np.zeros((24, 24, 24), dtype=bool)
    primary[5:19, 5:19, 5:19] = True
    nearby = primary.copy()
    nearby[8:16, 19:21, 8:16] = True
    fused, receipt = protected_adaptive_fusion(
        primary, nearby, spacing_xyz=(1.0, 1.0, 1.0)
    )
    assert receipt["accepted"] is True
    assert fused.sum() > primary.sum()

    oversized = np.ones_like(primary)
    refused, receipt = protected_adaptive_fusion(
        primary, oversized, spacing_xyz=(1.0, 1.0, 1.0)
    )
    assert receipt["accepted"] is False
    assert np.array_equal(refused, primary)


def test_secondary_is_quality_triggered_and_agreement_is_deterministic():
    clean = {
        "component_count": 1,
        "largest_component_fraction": 1.0,
        "touches_image_border": False,
        "volume_ml": 1000.0,
    }
    trigger, reasons = should_run_secondary(
        clean, {"volume_ml": 980.0}, fallback_used=False
    )
    assert trigger is False and reasons == []
    trigger, reasons = should_run_secondary(
        clean, {"volume_ml": 500.0}, fallback_used=False
    )
    assert trigger is True
    assert "primary_baseline_volume_disagreement" in reasons
    array = np.zeros((4, 4, 4), dtype=bool)
    array[1:3, 1:3, 1:3] = True
    assert mask_agreement(array, array) == {
        "dice": 1.0, "jaccard": 1.0, "left_to_right_volume_ratio": 1.0,
    }


def test_secondary_failure_preserves_valid_primary_mask(tmp_path: Path) -> None:
    case = tmp_path / "case"
    case.mkdir()
    reference = case / "volume.nii.gz"
    delayed = case / "delayed.nii.gz"
    executable = tmp_path / "mrsegmentator.exe"
    executable.write_bytes(b"fake")
    _image(reference)
    _image(delayed)
    primary = np.zeros((10, 11, 12), dtype=np.uint8)
    primary[2:8, 2:9, 2:10] = 1
    primary_image = sitk.GetImageFromArray(primary)
    calls = []

    def fake_segmenter(**kwargs):
        calls.append(kwargs["case_id"])
        if kwargs["case_id"].endswith("secondary"):
            raise TimeoutError("simulated")
        destination = kwargs["staging"] / "masks" / f'{kwargs["case_id"]}.nii.gz'
        destination.parent.mkdir(parents=True)
        sitk.WriteImage(primary_image, str(destination), useCompression=True)
        return {"elapsed_seconds": 10.0}

    result = run_phase_aware_shadow(
        case_root=case,
        phase_paths={"t1_delayed": delayed},
        reference_volume=reference,
        mrsegmentator_exe=executable,
        segmenter=fake_segmenter,
    )
    assert calls == ["visualization-shadow-primary", "visualization-shadow-secondary"]
    assert result["status"] == "APPROVED_WITH_WARNING"
    assert result["adaptive"]["selected_output"] == "primary"
    assert result["adaptive"]["fusion"]["reason"] == "secondary_technical_failure_primary_preserved"
    assert (case / "mask_organ_visualization_v2.nii.gz").is_file()
