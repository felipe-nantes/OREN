from __future__ import annotations

import inspect
import json
from pathlib import Path

import numpy as np
import SimpleITK as sitk

from dtwin.medgemma_client import load_screening_config
from dtwin.medgemma_panel_full_fov import (
    FULL_FOV_MULTIPANEL_POLICY,
    FULL_FOV_POLICY,
    generate_full_fov_panel_multiphase,
    generate_full_fov_panel_set_multiphase,
)


def _write_volume(path: Path, offset: float) -> None:
    array = np.zeros((24, 48, 56), dtype=np.float32)
    zz, yy, xx = np.ogrid[:24, :48, :56]
    body = ((yy - 24) / 20) ** 2 + ((xx - 28) / 23) ** 2 <= 1
    array[:, body[0]] = offset + zz[:, 0, 0, None] + 10
    image = sitk.GetImageFromArray(array)
    image.SetSpacing((1.2, 1.3, 3.0))
    sitk.WriteImage(image, str(path), useCompression=True)


def _case(tmp_path: Path):
    phases = {}
    for name, offset in (("art", 10.0), ("pv", 20.0), ("del", 30.0)):
        path = tmp_path / f"{name}.nii.gz"
        _write_volume(path, offset)
        phases[name] = path
    manifest = tmp_path / "case_manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "case_id": "anon-full-fov-test",
                "policy": "anonymize",
                "regulatory_state": "PESQUISA",
                "modality": "MRI",
            }
        ),
        encoding="utf-8",
    )
    config = load_screening_config(
        Path("configs/medgemma_local_4b_lld_v23_full_fov_no_mask_pilot.yaml")
    )
    return phases, manifest, config


def test_full_fov_panel_is_mask_independent_and_systematic(tmp_path: Path):
    phases, manifest_path, config = _case(tmp_path)
    result = generate_full_fov_panel_multiphase(
        phase_paths=phases,
        case_manifest_path=manifest_path,
        screening_config=config,
        output_dir=tmp_path / "output",
        model_trace={"model_id": "test"},
    )
    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    assert result.panel_path.is_file()
    assert len(result.axial_indices) == 9
    assert len(set(result.axial_indices)) == 9
    assert manifest["spatial_policy"] == FULL_FOV_POLICY
    assert manifest["organ_mask_used"] is False
    assert manifest["lesion_mask_used"] is False
    assert manifest["ground_truth_used"] is False
    assert manifest["crop_to_liver"] is False
    assert manifest["contour_rendered"] is False
    assert manifest["views"]["axial_source_range"] == [0, 23]
    assert manifest["png_metadata_keys"] == []


def test_full_fov_api_has_no_mask_parameter():
    parameters = inspect.signature(generate_full_fov_panel_multiphase).parameters
    assert "liver_mask_path" not in parameters
    assert "lesion_mask_path" not in parameters
    assert "ground_truth" not in parameters


def test_full_fov_three_panels_use_27_distinct_planes_and_deterministic_names(tmp_path: Path):
    phases, manifest_path, _config = _case(tmp_path)
    config = load_screening_config(
        Path("configs/medgemma_local_4b_lld_v23_full_fov_no_mask_3x9_pilot.yaml")
    )
    # The common fixture has only 24 planes; make a 36-plane case for 3x9.
    for name, offset in (("art", 10.0), ("pv", 20.0), ("del", 30.0)):
        array = np.zeros((36, 48, 56), dtype=np.float32)
        yy, xx = np.ogrid[:48, :56]
        body = ((yy - 24) / 20) ** 2 + ((xx - 28) / 23) ** 2 <= 1
        array[:, body] = offset + np.arange(36)[:, None] + 10
        image = sitk.GetImageFromArray(array)
        image.SetSpacing((1.2, 1.3, 3.0))
        sitk.WriteImage(image, str(phases[name]), useCompression=True)
    result = generate_full_fov_panel_set_multiphase(
        phase_paths=phases,
        case_manifest_path=manifest_path,
        screening_config=config,
        output_dir=tmp_path / "set-output",
        model_trace={"model_id": "test"},
    )
    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    assert [path.name for path in result.panel_paths] == [
        "medgemma_liver_screening_panel_001_of_003.png",
        "medgemma_liver_screening_panel_002_of_003.png",
        "medgemma_liver_screening_panel_003_of_003.png",
    ]
    assert len(result.axial_indices) == len(set(result.axial_indices)) == 27
    assert tuple(index for group in result.panel_axial_indices for index in group) == result.axial_indices
    assert manifest["spatial_policy"] == FULL_FOV_MULTIPANEL_POLICY
    assert manifest["panel_image_count"] == 3
    assert manifest["views"]["total_distinct_axial_indices"] == 27
    assert manifest["organ_mask_used"] is False
    assert manifest["lesion_mask_used"] is False
    assert manifest["ground_truth_used"] is False
    assert all(panel["png_metadata_keys"] == [] for panel in manifest["panels"])


def test_full_fov_three_panel_api_has_no_mask_parameter():
    parameters = inspect.signature(generate_full_fov_panel_set_multiphase).parameters
    assert "liver_mask_path" not in parameters
    assert "lesion_mask_path" not in parameters
    assert "ground_truth" not in parameters
