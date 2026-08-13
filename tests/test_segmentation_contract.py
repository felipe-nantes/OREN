from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
import SimpleITK as sitk
import yaml

from dtwin.core import PipelineError
from dtwin.segmentation_contract import (
    INPUT_SCHEMA,
    QUALITY_SCHEMA,
    assert_experimental_output,
    atomic_write_experimental_json,
    build_native_input_manifest,
    build_quality_manifest,
    experimental_paths,
    image_geometry,
    validate_visualization_mask,
    approved_visualization_mask,
)


def _write_image(path: Path, array: np.ndarray, *, spacing=(1.2, 1.3, 2.5)) -> None:
    image = sitk.GetImageFromArray(array)
    image.SetSpacing(spacing)
    image.SetOrigin((10.0, -4.0, 30.0))
    sitk.WriteImage(image, str(path), useCompression=True)


def test_native_contract_is_phi_safe_and_preserves_geometry(tmp_path):
    source = tmp_path / "patient-name-must-not-leak.nii.gz"
    reference = tmp_path / "volume.nii.gz"
    array = np.linspace(-200.0, 800.0, 8 * 9 * 10, dtype=np.float32).reshape(8, 9, 10)
    _write_image(source, array)
    _write_image(reference, array)

    manifest = build_native_input_manifest(
        source_volume=source,
        reference_volume=reference,
        source_role="t1_venous_native",
    )

    serialized = json.dumps(manifest)
    assert manifest["schema"] == INPUT_SCHEMA
    assert manifest["source"]["intensity_policy"] == "native_preserved"
    assert manifest["source_already_on_reference_grid"] is True
    assert manifest["classification_input_immutable"] is True
    assert "patient-name-must-not-leak" not in serialized
    assert str(tmp_path) not in serialized
    assert manifest["privacy"]["patient_identifiers_stored"] is False


def test_experimental_paths_cannot_overwrite_production(tmp_path):
    paths = experimental_paths(tmp_path)
    assert assert_experimental_output(paths.visualization_mask, tmp_path) == paths.visualization_mask
    with pytest.raises(PipelineError, match="producao protegido"):
        assert_experimental_output(tmp_path / "mask_organ.nii.gz", tmp_path)
    with pytest.raises(PipelineError, match="fora do contrato"):
        assert_experimental_output(tmp_path / "unapproved.json", tmp_path)


def test_quality_manifest_validates_binary_mask_on_reference_grid(tmp_path):
    source = tmp_path / "native.nii.gz"
    reference = tmp_path / "volume.nii.gz"
    mask = experimental_paths(tmp_path).visualization_mask
    volume = np.ones((8, 9, 10), dtype=np.float32)
    binary = np.zeros_like(volume, dtype=np.uint8)
    binary[2:7, 2:8, 2:9] = 1
    _write_image(source, volume)
    _write_image(reference, volume)
    _write_image(mask, binary)
    input_manifest = build_native_input_manifest(
        source_volume=source,
        reference_volume=reference,
        source_role="t1_venous_native",
    )

    result = build_quality_manifest(
        backend_id="mrsegmentator",
        backend_version="test",
        input_manifest=input_manifest,
        visualization_mask=mask,
        reference_volume=reference,
        elapsed_seconds=12.5,
    )

    assert result["schema"] == QUALITY_SCHEMA
    assert result["mask"]["foreground_voxels"] == int(binary.sum())
    assert result["mask"]["same_reference_grid"] is True
    assert result["classification_input_immutable"] is True


def test_empty_or_nonbinary_visualization_mask_is_rejected(tmp_path):
    reference = tmp_path / "volume.nii.gz"
    mask = tmp_path / "mask.nii.gz"
    _write_image(reference, np.ones((4, 5, 6), dtype=np.float32))
    _write_image(mask, np.zeros((4, 5, 6), dtype=np.uint8))
    with pytest.raises(PipelineError, match="vazia"):
        validate_visualization_mask(mask, reference)
    values = np.zeros((4, 5, 6), dtype=np.uint8)
    values[1, 2, 3] = 2
    _write_image(mask, values)
    with pytest.raises(PipelineError, match="binaria"):
        validate_visualization_mask(mask, reference)


def test_mask_with_different_grid_is_rejected(tmp_path):
    reference = tmp_path / "volume.nii.gz"
    mask = tmp_path / "mask.nii.gz"
    _write_image(reference, np.ones((4, 5, 6), dtype=np.float32))
    _write_image(mask, np.ones((4, 5, 6), dtype=np.uint8), spacing=(2.0, 2.0, 2.0))
    with pytest.raises(PipelineError, match="fora da grade"):
        validate_visualization_mask(mask, reference)


def test_non_3d_input_is_rejected():
    with pytest.raises(PipelineError, match="3-D"):
        image_geometry(sitk.GetImageFromArray(np.zeros((5, 6), dtype=np.float32)))


def test_atomic_writer_only_writes_authorized_manifest(tmp_path):
    paths = experimental_paths(tmp_path)
    atomic_write_experimental_json(
        paths.input_manifest,
        {"schema": INPUT_SCHEMA, "ok": True},
        case_root=tmp_path,
    )
    assert json.loads(paths.input_manifest.read_text(encoding="utf-8"))["ok"] is True
    assert not (tmp_path / "mask_organ.nii.gz").exists()
    with pytest.raises(PipelineError, match="NIfTI"):
        atomic_write_experimental_json(
            paths.visualization_mask,
            {"not": "an image"},
            case_root=tmp_path,
        )


def test_research_default_config_has_safe_fallback_and_protects_classifier_artifacts():
    repo = Path(__file__).resolve().parents[1]
    config = yaml.safe_load(
        (repo / "configs" / "segmentation_visualization_v2.yaml").read_text(
            encoding="utf-8"
        )
    )
    assert config["enabled"] is True
    assert config["status"] == "research_default_with_safe_fallback"
    assert config["webapp"]["selected_by_default"] is True
    assert config["webapp"]["multiphase_only"] is True
    assert config["candidate_backends"][0]["id"] == "mrsegmentator"
    assert config["candidate_backends"][0]["enabled"] is True
    adaptive = config["candidate_backends"][0]["selection_policy"]["adaptive_confirmation"]
    assert adaptive["trigger_only_on_technical_uncertainty"] is True
    assert adaptive["maximum_added_fraction"] == 0.18
    assert config["scope"]["may_change_classification_input"] is False
    assert config["protected_artifacts"]["classification_mask"] == "mask_organ.nii.gz"
    assert (
        config["experimental_artifacts"]["visualization_mask"]
        == "mask_organ_visualization_v2.nii.gz"
    )


def test_only_complete_safe_receipt_authorizes_shadow_mask(tmp_path):
    reference = tmp_path / "volume.nii.gz"
    source = tmp_path / "arterial.nii.gz"
    paths = experimental_paths(tmp_path)
    volume = np.ones((6, 7, 8), dtype=np.float32)
    mask = np.zeros((6, 7, 8), dtype=np.uint8)
    mask[1:5, 1:6, 1:7] = 1
    _write_image(reference, volume)
    _write_image(source, volume)
    _write_image(paths.visualization_mask, mask)
    input_manifest = build_native_input_manifest(
        source_volume=source,
        reference_volume=reference,
        source_role="t1_arterial_registered",
    )
    quality = build_quality_manifest(
        backend_id="mrsegmentator",
        backend_version="test",
        input_manifest=input_manifest,
        visualization_mask=paths.visualization_mask,
        reference_volume=reference,
        elapsed_seconds=1.0,
    )
    quality.update(
        ground_truth_read=False,
        lesion_masks_read=0,
        production_files_written=False,
    )
    atomic_write_experimental_json(paths.quality_manifest, quality, case_root=tmp_path)
    assert approved_visualization_mask(tmp_path) == paths.visualization_mask

    quality["lesion_masks_read"] = 1
    atomic_write_experimental_json(paths.quality_manifest, quality, case_root=tmp_path)
    assert approved_visualization_mask(tmp_path) is None
