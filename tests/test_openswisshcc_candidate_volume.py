from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
import SimpleITK as sitk
from PIL import Image

from dtwin.benchmark.openswisshcc_alignment import _sha256
from dtwin.benchmark.openswisshcc_candidate_volume import (
    CANDIDATE_SCHEMA,
    CASE_SCHEMA,
    OUTPUT_SIDE,
    _original_dynamic_inputs,
    _registered_or_none,
    _validate_manifest_files,
    build_candidate_volume_case,
    centered_slice_indices,
    select_candidate_components,
    _valid_localizer_run_schema,
    preview_frame_indices,
)
from dtwin.benchmark.openswisshcc_lesion_localizer import CASE_SCHEMA as LOCALIZER_CASE_SCHEMA
from dtwin.core import PipelineError


CASE_ID = "anon-openswiss-0123456789abcdef"


def test_gallery_preview_uses_start_center_end_without_duplicates():
    assert preview_frame_indices(1) == [0]
    assert preview_frame_indices(3) == [0, 1, 2]
    assert preview_frame_indices(5) == [0, 2, 4]

def test_localizer_summary_accepts_only_official_single_or_merged_schema():
    assert _valid_localizer_run_schema({"schema": "argos-openswisshcc-lesion-localizer-run-v1"})
    assert _valid_localizer_run_schema({
        "schema": "argos-openswisshcc-lesion-localizer-merged-run-v1",
        "source_run_schema": "argos-openswisshcc-lesion-localizer-run-v1",
    })
    assert not _valid_localizer_run_schema({
        "schema": "argos-openswisshcc-lesion-localizer-merged-run-v1",
        "source_run_schema": "unexpected",
    })


def _write_image(path: Path, array: np.ndarray, pixel_type=sitk.sitkFloat32) -> Path:
    image = sitk.GetImageFromArray(array)
    image.SetSpacing((1.25, 1.5, 2.0))
    image.SetOrigin((-20.0, -30.0, 5.0))
    sitk.WriteImage(sitk.Cast(image, pixel_type), str(path))
    return path


def _sources(tmp_path: Path, *, constant_venous=False, constant_t2=False, candidate=True):
    tmp_path.mkdir(parents=True, exist_ok=True)
    shape = (9, 32, 32)
    z, y, x = np.indices(shape)
    base = (x * 2.0 + y * 3.0 + z * 7.0).astype(np.float32)
    arrays = {
        "t1_native": base + 10,
        "t1_arterial_registered": base * 1.2 + 20,
        "t1_arterial_ttc_3": base * 1.2 + 21,
        "t1_venous": np.ones(shape, dtype=np.float32) if constant_venous else base * 1.1 + 30,
        "t1_delayed_registered": base * 0.9 + 40,
        "t1_delayed": base * 0.9 + 41,
        "t2_blade": np.ones(shape, dtype=np.float32) if constant_t2 else base * 0.8 + 50,
        "dwi_trace_run_03": base * 1.4 + 60,
        "dwi_adc": base * 0.6 + 70,
    }
    paths, hashes = {}, {}
    for role, array in arrays.items():
        paths[role] = _write_image(tmp_path / f"{role}.nii.gz", array)
        hashes[role] = _sha256(paths[role])
    liver = np.zeros(shape, dtype=np.uint8)
    liver[:, 4:28, 4:28] = 1
    paths["liver_mask_venous"] = _write_image(tmp_path / "liver_mask_venous.nii.gz", liver, sitk.sitkUInt8)
    hashes["liver_mask_venous"] = _sha256(paths["liver_mask_venous"])

    mask = np.zeros(shape, dtype=np.uint8)
    if candidate:
        mask[3:6, 14:18, 15:19] = 1
    localizer = tmp_path / "localizer"
    localizer.mkdir()
    candidate_path = _write_image(localizer / "liver_lesion_candidates_in_liver.nii.gz", mask, sitk.sitkUInt8)
    voxels = int(mask.sum())
    components = [] if not candidate else [{
        "component_id": 1,
        "voxels": voxels,
        "volume_mm3": voxels * 3.75,
        "centroid_index_xyz": np.argwhere(mask > 0).mean(axis=0)[::-1].tolist(),
        "rank_by_volume": 1,
    }]
    (localizer / "localizer_manifest.json").write_text(json.dumps({
        "schema": LOCALIZER_CASE_SCHEMA,
        "case_id": CASE_ID,
        "status": "candidate_scores_only_no_decision",
        "input_sha256": hashes["t1_venous"],
        "filtered_candidate_mask_sha256": _sha256(candidate_path),
        "candidate_mask_is_model_derived": True,
        "ground_truth_read": False,
        "ground_truth_lesion_mask_used": False,
        "final_decision": None,
        "features": {"inside_liver_voxels": voxels, "component_count": len(components), "components": components},
    }), encoding="utf-8")
    morph_roles = ("t1_venous", "t2_blade", "dwi_trace_run_03", "dwi_adc", "liver_mask_venous")
    morphology = {"roles": list(morph_roles), "paths": {r: paths[r] for r in morph_roles}, "hashes": {r: hashes[r] for r in morph_roles}}
    dynamic_roles = ("t1_native", "t1_venous", "t1_delayed", "liver_mask_venous", "t1_arterial_ttc_3")
    dynamic = {"arterial_role": "t1_arterial_ttc_3", "paths": {r: paths[r] for r in dynamic_roles}, "hashes": {r: hashes[r] for r in dynamic_roles}}
    registered = {
        "t1_arterial_registered": {"path": paths["t1_arterial_registered"], "sha256": hashes["t1_arterial_registered"], "source_role": "t1_arterial_ttc_3"},
        "t1_delayed_registered": {"path": paths["t1_delayed_registered"], "sha256": hashes["t1_delayed_registered"], "source_role": "t1_delayed"},
    }
    return morphology, dynamic, registered, localizer


def _build(tmp_path: Path, *, use_registered=True, **options):
    morphology, dynamic, registered, localizer = _sources(tmp_path / "sources", **options)
    destination = tmp_path / "output"
    manifest = build_candidate_volume_case(
        case_id=CASE_ID,
        morphology_source=morphology,
        dynamic_source=dynamic,
        registered_source=registered if use_registered else None,
        localizer_dir=localizer,
        destination=destination,
    )
    return manifest, destination


def test_candidate_selection_uses_three_then_expands_to_coverage():
    components = [{"component_id": n, "voxels": v} for n, v in enumerate([25, 20, 15, 10, 10, 8, 7, 5], 1)]
    selected, coverage = select_candidate_components(components, total_candidate_voxels=100)
    assert len(selected) == 5
    assert coverage == 0.80


def test_candidate_selection_rejects_if_five_do_not_cover_75_percent():
    with pytest.raises(PipelineError, match="cobrem apenas"):
        select_candidate_components([{"component_id": n, "voxels": 10} for n in range(1, 11)], total_candidate_voxels=100)


def test_candidate_selection_can_be_frozen_to_exact_top_five():
    components = [
        {"component_id": n, "voxels": value}
        for n, value in enumerate([50, 20, 15, 10, 5], 1)
    ]
    selected, coverage = select_candidate_components(
        components,
        total_candidate_voxels=100,
        minimum_components=5,
        maximum_components=5,
        target_fraction=1.0,
    )
    assert [item["component_id"] for item in selected] == [1, 2, 3, 4, 5]
    assert coverage == 1.0


@pytest.mark.parametrize(("center", "expected"), [(0.0, [0, 1, 2, 3, 4]), (8.0, [4, 5, 6, 7, 8]), (4.2, [2, 3, 4, 5, 6])])
def test_centered_indices_are_unique_and_shift_at_boundaries(center, expected):
    assert centered_slice_indices(center, 9, 5) == expected


def test_case_builds_exactly_29_source_only_rgb_frames(tmp_path):
    manifest, destination = _build(tmp_path)
    assert manifest["schema"] == CASE_SCHEMA
    candidate_dir = destination / "candidate_001"
    candidate = json.loads((candidate_dir / "manifest.json").read_text(encoding="utf-8"))
    assert candidate["schema"] == CANDIDATE_SCHEMA
    assert candidate["frame_count"] == 29
    assert [g["frame_count"] for g in candidate["groups"]] == [5, 5, 5, 5, 3, 3, 3]
    assert candidate["dynamic_alignment_mode"] == "registered_to_venous"
    assert [g["role"] for g in candidate["groups"][:4]] == ["t1_native", "t1_arterial_registered", "t1_venous", "t1_delayed_registered"]
    assert candidate["gate"]["candidate_contour_rendered"] is False
    assert candidate["gate"]["dataset_lesion_mask_used"] is False
    for group in candidate["groups"]:
        for frame in group["frames"]:
            image = Image.open(candidate_dir / frame["filename"])
            assert image.size == (OUTPUT_SIDE, OUTPUT_SIDE)
            pixels = np.asarray(image)
            assert np.array_equal(pixels[..., 0], pixels[..., 1])
            assert np.array_equal(pixels[..., 1], pixels[..., 2])


def test_optional_low_contrast_group_is_omitted(tmp_path):
    _, destination = _build(tmp_path, constant_t2=True)
    candidate = json.loads((destination / "candidate_001" / "manifest.json").read_text(encoding="utf-8"))
    assert candidate["frame_count"] == 26
    assert any(item["role"] == "t2" for item in candidate["omitted_groups"])


def test_invalid_venous_group_fails_the_gate(tmp_path):
    with pytest.raises(PipelineError, match="Gate do stack candidato"):
        _build(tmp_path, constant_venous=True)


def test_empty_localizer_uses_one_liver_centered_fallback(tmp_path):
    manifest, destination = _build(tmp_path, candidate=False)
    assert manifest["selection"]["fallback_no_candidate"] is True
    candidate = json.loads((destination / "candidate_001" / "manifest.json").read_text(encoding="utf-8"))
    assert candidate["fallback_no_candidate"] is True
    assert candidate["frame_count"] == 29


def test_frame_hash_tampering_is_rejected(tmp_path):
    _, destination = _build(tmp_path)
    candidate_dir = destination / "candidate_001"
    manifest = json.loads((candidate_dir / "manifest.json").read_text(encoding="utf-8"))
    frame = candidate_dir / manifest["groups"][0]["frames"][0]["filename"]
    frame.write_bytes(frame.read_bytes() + b"tampered")
    with pytest.raises(PipelineError, match="Frame/hash"):
        _validate_manifest_files(candidate_dir, manifest)


def test_unregistered_original_phases_are_explicit_and_keep_complete_stack(tmp_path):
    manifest, destination = _build(tmp_path, use_registered=False)
    candidate = json.loads((destination / "candidate_001" / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["dynamic_alignment_mode"] == "original_unregistered_physical_center"
    assert candidate["dynamic_alignment_mode"] == "original_unregistered_physical_center"
    assert candidate["frame_count"] == 29
    assert max(len(frame["filename"]) for group in candidate["groups"] for frame in group["frames"]) <= 48
    dynamic = candidate["groups"][:4]
    assert [group["role"] for group in dynamic] == [
        "t1_native",
        "t1_arterial_original",
        "t1_venous",
        "t1_delayed_original",
    ]
    assert dynamic[1]["source_role"] == "t1_arterial_ttc_3"
    assert dynamic[1]["alignment_mode"] == "original_unregistered_physical_center"
    assert dynamic[3]["source_role"] == "t1_delayed"


def test_original_dynamic_loader_prefers_ttc3_and_rejects_lesion_files(tmp_path):
    _, dynamic, _, _ = _sources(tmp_path / "inputs")
    root = tmp_path / "inputs"
    roles = ("t1_native", "t1_venous", "t1_delayed", "liver_mask_venous", "t1_arterial_ttc_3")
    files = [{
        "role": role,
        "relative_path": dynamic["paths"][role].relative_to(root).as_posix(),
        "bytes": dynamic["paths"][role].stat().st_size,
        "sha256": dynamic["hashes"][role],
    } for role in roles]
    row = {"schema": "argos-public-liver-mri-input-v1", "case_id": CASE_ID, "files": files, "research_only": True, "clinical_use_allowed": False}
    manifest = tmp_path / "inputs.jsonl"
    manifest.write_text(json.dumps(row) + "\n", encoding="utf-8")
    indexed = _original_dynamic_inputs(manifest, root)
    assert indexed[CASE_ID]["arterial_role"] == "t1_arterial_ttc_3"

    row["files"].append({"role": "lesion_mask", "relative_path": "forbidden.nii.gz", "bytes": 0, "sha256": "0" * 64})
    manifest.write_text(json.dumps(row) + "\n", encoding="utf-8")
    with pytest.raises(PipelineError, match="lesao"):
        _original_dynamic_inputs(manifest, root)


def test_missing_registration_allows_fallback_but_partial_directory_aborts(tmp_path):
    root = tmp_path / "registration"
    root.mkdir()
    assert _registered_or_none(CASE_ID, root) is None
    case_root = root / CASE_ID
    case_root.mkdir()
    assert _registered_or_none(CASE_ID, root) is None
    (case_root / "partial.nii.gz").write_bytes(b"partial")
    with pytest.raises(PipelineError, match="parcial"):
        _registered_or_none(CASE_ID, root)
