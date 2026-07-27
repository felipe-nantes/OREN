from __future__ import annotations

import inspect
import json
from pathlib import Path

import numpy as np
import SimpleITK as sitk

from dtwin.medgemma_client import load_screening_config
from dtwin.medgemma_panel_liver_enriched import (
    LIVER_ENRICHED_POLICY,
    generate_liver_enriched_panel_set_multiphase,
    select_liver_enriched_indices,
)


def test_stable_localizer_creates_three_interleaved_full_range_panels():
    mask = np.zeros((60, 32, 32), dtype=bool)
    mask[10:41, 8:24, 8:24] = True
    groups, audit = select_liver_enriched_indices(
        mask=mask, body_present=np.ones(60, dtype=bool), spacing_z=3.0,
    )
    assert len(groups) == 3
    assert all(len(group) == 9 for group in groups)
    assert all(group[0] < 10 and group[-1] > 40 for group in groups)
    flattened = [index for group in groups for index in group]
    assert len(flattened) == len(set(flattened)) == 27
    assert audit["localizer_stable"] is True
    assert audit["selection_mode"] == "stable_coarse_localizer_interleaved_3x9"
    assert all(value >= 5 for value in audit["panel_localizer_supported_tile_counts"])


def test_weak_localizer_creates_two_mask_independent_interleaved_panels():
    mask = np.zeros((60, 32, 32), dtype=bool)
    mask[30:32, 10:12, 10:12] = True
    groups, audit = select_liver_enriched_indices(
        mask=mask, body_present=np.ones(60, dtype=bool), spacing_z=3.0,
    )
    assert len(groups) == 2
    assert all(len(group) == 9 for group in groups)
    flattened = [index for group in groups for index in group]
    assert len(flattened) == len(set(flattened)) == 18
    assert max(flattened) <= 44
    assert audit["localizer_stable"] is False
    assert audit["selection_mode"].startswith("weak_localizer_mask_independent")


def _write_image(path: Path, array: np.ndarray) -> None:
    image = sitk.GetImageFromArray(array)
    image.SetSpacing((1.2, 1.3, 3.0))
    sitk.WriteImage(image, str(path), useCompression=True)


def test_renderer_uses_mask_only_for_localization_and_never_renders_it(tmp_path: Path):
    shape = (60, 48, 56)
    yy, xx = np.ogrid[:48, :56]
    body = ((yy - 24) / 20) ** 2 + ((xx - 28) / 23) ** 2 <= 1
    phases = {}
    for name, offset in (("art", 10.0), ("pv", 20.0), ("del", 30.0)):
        array = np.zeros(shape, dtype=np.float32)
        array[:, body] = offset + np.arange(shape[0])[:, None] + 10
        path = tmp_path / f"{name}.nii.gz"
        _write_image(path, array)
        phases[name] = path
    mask = np.zeros(shape, dtype=np.uint8)
    mask[12:43, 12:35, 10:38] = 1
    mask_path = tmp_path / "coarse_liver_mask.nii.gz"
    _write_image(mask_path, mask)
    case_manifest = tmp_path / "case_manifest.json"
    case_manifest.write_text(json.dumps({
        "case_id": "anon-liver-enriched-test",
        "policy": "anonymize",
        "regulatory_state": "PESQUISA",
        "modality": "MRI",
    }), encoding="utf-8")
    config = load_screening_config(
        Path("configs/medgemma_local_4b_lld_v23_liver_enriched_pilot.yaml")
    )
    result = generate_liver_enriched_panel_set_multiphase(
        phase_paths=phases,
        coarse_liver_mask_path=mask_path,
        case_manifest_path=case_manifest,
        screening_config=config,
        output_dir=tmp_path / "output",
        model_trace={"model_id": "test"},
    )
    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    assert result.panel_count == 3
    assert len(result.panel_paths) == 3
    assert manifest["spatial_policy"] == LIVER_ENRICHED_POLICY
    assert manifest["organ_mask_used"] is True
    assert manifest["organ_mask_use_scope"] == "coarse_axial_localization_only_not_rendered_not_cropped"
    assert manifest["organ_mask_rendered"] is False
    assert manifest["crop_to_liver"] is False
    assert manifest["contour_rendered"] is False
    assert manifest["lesion_mask_used"] is False
    assert manifest["ground_truth_used"] is False
    assert all(panel["png_metadata_keys"] == [] for panel in manifest["panels"])


def test_hbp_single_phase_is_replicated_as_grayscale_without_dynamic_claim(tmp_path):
    shape = (60, 48, 56)
    volume = np.zeros(shape, dtype=np.float32)
    volume[:, 6:42, 8:48] = np.arange(60, dtype=np.float32)[:, None, None] + 10
    image_path = tmp_path / "hbp.nii.gz"
    _write_image(image_path, volume)
    mask = np.zeros(shape, dtype=np.uint8)
    mask[12:43, 12:35, 10:38] = 1
    mask_path = tmp_path / "automatic_liver_mask.nii.gz"
    _write_image(mask_path, mask)
    case_manifest = tmp_path / "case_manifest.json"
    case_manifest.write_text(
        json.dumps(
            {
                "case_id": "anon-gdeob-testcase00000",
                "policy": "anonymize",
                "regulatory_state": "PESQUISA",
                "modality": "MRI",
            }
        ),
        encoding="utf-8",
    )
    config = load_screening_config(
        Path("configs/medgemma_local_4b_gd_eob_hbp_liver_enriched_pilot.yaml")
    )
    result = generate_liver_enriched_panel_set_multiphase(
        phase_paths={"hbp": image_path},
        coarse_liver_mask_path=mask_path,
        case_manifest_path=case_manifest,
        screening_config=config,
        output_dir=tmp_path / "output",
        model_trace={"model_id": "test"},
    )
    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    assert manifest["input_type"] == (
        "mri_single_phase_replicated_grayscale_full_fov_liver_enriched"
    )
    assert manifest["single_phase_replicated_across_rgb"] is True
    assert manifest["dynamic_enhancement_information_present"] is False
    assert manifest["fusion_channel_map"] == {
        "red": "hbp",
        "green": "hbp",
        "blue": "hbp",
    }


def test_renderer_api_does_not_accept_lesion_or_ground_truth():
    parameters = inspect.signature(generate_liver_enriched_panel_set_multiphase).parameters
    assert "lesion_mask_path" not in parameters
    assert "ground_truth" not in parameters
