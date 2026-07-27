import json
from pathlib import Path

import numpy as np
import pytest
import SimpleITK as sitk
from PIL import Image

from dtwin.benchmark.openswisshcc_highdimensional import (
    _orient_pair_lps,
    _publish_staging_directory,
    _scaled_rgb_slice,
    _select_slice_indices,
    build_highdimensional_stack,
)
from dtwin.core import PipelineError, sha256_of


CASE_ID = "anon-openswiss-0123456789abcdef"


def _write_inputs(tmp_path: Path, *, geometry_mismatch=False, forbidden=False):
    input_root = tmp_path / "inputs"
    case = input_root / CASE_ID
    (case / "dyn").mkdir(parents=True)
    (case / "masks").mkdir()
    volume_array = np.arange(10 * 18 * 20, dtype=np.float32).reshape(10, 18, 20)
    mask_array = np.zeros_like(volume_array, dtype=np.uint8)
    mask_array[2:8, 4:14, 5:16] = 1
    volume = sitk.GetImageFromArray(volume_array)
    volume.SetSpacing((1.2, 1.2, 3.0))
    mask = sitk.GetImageFromArray(mask_array)
    mask.CopyInformation(volume)
    if geometry_mismatch:
        mask.SetOrigin((1.0, 0.0, 0.0))
    volume_path = case / "dyn" / "t1_venous.nii.gz"
    mask_path = case / "masks" / "liver_mask_venous.nii.gz"
    sitk.WriteImage(volume, str(volume_path))
    sitk.WriteImage(mask, str(mask_path))
    files = [
        {
            "role": "t1_venous",
            "relative_path": f"{CASE_ID}/dyn/t1_venous.nii.gz",
            "sha256": sha256_of(volume_path),
            "bytes": volume_path.stat().st_size,
        },
        {
            "role": "liver_mask_venous",
            "relative_path": f"{CASE_ID}/masks/liver_mask_venous.nii.gz",
            "sha256": sha256_of(mask_path),
            "bytes": mask_path.stat().st_size,
        },
    ]
    if forbidden:
        files.append(
            {
                "role": "lesion_mask_manual",
                "relative_path": f"{CASE_ID}/masks/lesion_mask.nii.gz",
                "sha256": "0" * 64,
                "bytes": 0,
            }
        )
    manifest = tmp_path / "development_inputs.jsonl"
    manifest.write_text(
        json.dumps(
            {
                "schema": "argos-public-liver-mri-input-v1",
                "case_id": CASE_ID,
                "split": "development",
                "research_only": True,
                "clinical_use_allowed": False,
                "files": files,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    return manifest, input_root


def test_select_slice_indices_preserves_short_intervals_and_official_max85():
    assert _select_slice_indices(2, 6, 10) == [2, 3, 4, 5, 6]
    assert _select_slice_indices(4, 4, 10) == [2, 3, 4, 5, 6]
    assert _select_slice_indices(0, 84, 85) == list(range(85))
    assert _select_slice_indices(0, 85, 86) == list(range(1, 86))


def test_select_slice_indices_rejects_volume_with_fewer_than_five_slices():
    with pytest.raises(PipelineError, match="ao menos 5"):
        _select_slice_indices(0, 3, 4)


def test_scaled_slice_stays_grayscale_rgb_and_under_512():
    source = np.arange(4 * 520, dtype=np.float32).reshape(4, 520)
    image = _scaled_rgb_slice(source, float(source.min()), float(source.max()))
    assert image.mode == "RGB"
    assert image.size == (512, 4)
    bands = np.asarray(image)
    assert np.array_equal(bands[..., 0], bands[..., 1])
    assert np.array_equal(bands[..., 1], bands[..., 2])


def test_lps_orientation_harmonizes_only_accumulated_float_metadata_noise():
    array = np.zeros((10, 18, 320), dtype=np.float32)
    volume = sitk.GetImageFromArray(array)
    mask = sitk.GetImageFromArray(array.astype(np.uint8))
    volume.SetSpacing((1.2812999486923218, 1.2, 3.0))
    mask.SetSpacing((1.2813000679016113, 1.2, 3.0))
    direction = (-1.0, 0.0, 0.0, 0.0, -1.0, 0.0, 0.0, 0.0, 1.0)
    volume.SetDirection(direction)
    mask.SetDirection(direction)

    volume_lps, mask_lps, audit = _orient_pair_lps(volume, mask)

    assert audit["mask_metadata_harmonized_after_orientation"] is True
    assert audit["post_orientation_max_origin_delta_before_harmonization"] > 1e-5
    assert audit["voxel_array_alignment_preserved"] is True
    assert volume_lps.GetSize() == mask_lps.GetSize()
    assert volume_lps.GetSpacing() == mask_lps.GetSpacing()
    assert volume_lps.GetOrigin() == mask_lps.GetOrigin()
    assert volume_lps.GetDirection() == mask_lps.GetDirection()

def test_atomic_publish_retries_transient_windows_permission_error(monkeypatch):
    class Staging:
        calls = 0

        def rename(self, _destination):
            self.calls += 1
            if self.calls < 3:
                raise PermissionError("transient lock")

    class Destination:
        @staticmethod
        def exists():
            return False

    monkeypatch.setattr(
        "dtwin.benchmark.openswisshcc_highdimensional.time.sleep",
        lambda _value: None,
    )
    staging = Staging()
    _publish_staging_directory(staging, Destination())
    assert staging.calls == 3

def test_build_stack_is_deterministic_auditable_and_reusable(tmp_path):
    manifest_path, input_root = _write_inputs(tmp_path)
    out_root = tmp_path / "stacks"

    result = build_highdimensional_stack(
        manifest_path=manifest_path,
        input_root=input_root,
        out_root=out_root,
        case_id=CASE_ID,
    )
    reused = build_highdimensional_stack(
        manifest_path=manifest_path,
        input_root=input_root,
        out_root=out_root,
        case_id=CASE_ID,
    )

    assert result == reused
    assert result["sampling"]["selected_indices_lps_z"] == [2, 3, 4, 5, 6, 7]
    assert result["slice_count"] == 6
    assert result["liver_mask_audit"]["coverage_fraction"] == 1.0
    assert result["gate"] == {
        "count_within_configured_limit": True,
        "all_images_at_most_512": True,
        "all_hashes_present": True,
        "ground_truth_used": False,
        "lesion_mask_used": False,
        "phi_metadata_included": False,
        "passed": True,
    }
    assert set(result["source"]) == {
        "volume_role",
        "volume_sha256",
        "liver_mask_role",
        "liver_mask_sha256",
    }
    for item in result["images"]:
        path = out_root / CASE_ID / item["filename"]
        assert sha256_of(path) == item["sha256"]
        with Image.open(path) as image:
            assert image.format == "PNG"
            assert image.mode == "RGB"
            assert max(image.size) <= 512


def test_build_stack_honors_configured_time_safe_slice_cap(tmp_path):
    manifest_path, input_root = _write_inputs(tmp_path)
    result = build_highdimensional_stack(
        manifest_path=manifest_path,
        input_root=input_root,
        out_root=tmp_path / "capped-stacks",
        case_id=CASE_ID,
        maximum_slices=5,
    )

    assert result["slice_count"] == 5
    assert result["sampling"]["maximum_slices"] == 5
    assert result["sampling"]["selected_indices_lps_z"] == [3, 4, 5, 6, 7]
    assert result["gate"]["count_within_configured_limit"] is True

def test_build_stack_rejects_any_lesion_or_ground_truth_entry(tmp_path):
    manifest_path, input_root = _write_inputs(tmp_path, forbidden=True)
    with pytest.raises(PipelineError, match="entrada proibida"):
        build_highdimensional_stack(
            manifest_path=manifest_path,
            input_root=input_root,
            out_root=tmp_path / "stacks",
            case_id=CASE_ID,
        )


def test_build_stack_rejects_hash_and_geometry_mismatch(tmp_path):
    manifest_path, input_root = _write_inputs(tmp_path)
    record = json.loads(manifest_path.read_text(encoding="utf-8"))
    record["files"][0]["sha256"] = "f" * 64
    manifest_path.write_text(json.dumps(record) + "\n", encoding="utf-8")
    with pytest.raises(PipelineError, match="Hash do volume"):
        build_highdimensional_stack(
            manifest_path=manifest_path,
            input_root=input_root,
            out_root=tmp_path / "hash-stacks",
            case_id=CASE_ID,
        )

    mismatch_manifest, mismatch_root = _write_inputs(
        tmp_path / "geometry", geometry_mismatch=True
    )
    with pytest.raises(PipelineError, match="Geometria"):
        build_highdimensional_stack(
            manifest_path=mismatch_manifest,
            input_root=mismatch_root,
            out_root=tmp_path / "geometry-stacks",
            case_id=CASE_ID,
        )


def test_reuse_rejects_tampered_png(tmp_path):
    manifest_path, input_root = _write_inputs(tmp_path)
    out_root = tmp_path / "stacks"
    result = build_highdimensional_stack(
        manifest_path=manifest_path,
        input_root=input_root,
        out_root=out_root,
        case_id=CASE_ID,
    )
    (out_root / CASE_ID / result["images"][0]["filename"]).write_bytes(b"tampered")

    with pytest.raises(PipelineError, match="Hash inconsistente"):
        build_highdimensional_stack(
            manifest_path=manifest_path,
            input_root=input_root,
            out_root=out_root,
            case_id=CASE_ID,
        )
