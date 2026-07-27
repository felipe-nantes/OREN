import json
from pathlib import Path

import numpy as np
import pytest
import SimpleITK as sitk
from PIL import Image

from dtwin.benchmark.openswisshcc_alignment import _sha256
from dtwin.benchmark.openswisshcc_multisequence_panel import generate_multisequence_panel_set
from dtwin.core import PipelineError


def _fixture(tmp_path: Path, *, dwi_origin=(0.0, 0.0, 0.0)):
    case_id = "anon-test-multisequence"
    inputs = tmp_path / "inputs"
    files = []
    rng = np.random.default_rng(7)
    roles = [
        ("t1_venous", "dyn/t1_venous.nii.gz"),
        ("liver_mask_venous", "masks/liver_mask_venous.nii.gz"),
        ("dwi_adc", "dwi/dwi_adc.nii.gz"),
        ("dwi_trace_run_01", "dwi/dwi_trace_run_01.nii.gz"),
        ("dwi_trace_run_02", "dwi/dwi_trace_run_02.nii.gz"),
        ("dwi_trace_run_03", "dwi/dwi_trace_run_03.nii.gz"),
        ("t2_blade", "anat/t2_blade.nii.gz"),
    ]
    mask = np.zeros((12, 32, 32), dtype=np.uint8)
    mask[3:9, 8:24, 8:24] = 1
    for number, (role, relative) in enumerate(roles, start=1):
        path = inputs / case_id / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        if role == "liver_mask_venous":
            array = mask
            image = sitk.GetImageFromArray(array)
        else:
            array = rng.normal(100 + number * 10, 20, size=(12, 32, 32)).astype(np.float32)
            image = sitk.GetImageFromArray(array)
            if role.startswith("dwi_"):
                image.SetOrigin(dwi_origin)
        sitk.WriteImage(image, str(path))
        files.append({
            "role": role,
            "relative_path": f"{case_id}/{relative}",
            "bytes": path.stat().st_size,
            "sha256": _sha256(path),
        })
    manifest = tmp_path / "inputs.jsonl"
    manifest.write_text(json.dumps({
        "schema": "argos-public-liver-mri-input-v1", "case_id": case_id,
        "dataset_id": "test", "split": "development", "files": files,
        "research_only": True, "clinical_use_allowed": False,
    }) + "\n", encoding="utf-8")
    return case_id, inputs, manifest


def test_generates_every_projected_trace_plane_once(tmp_path: Path):
    case_id, inputs, manifest = _fixture(tmp_path)
    result = generate_multisequence_panel_set(
        case_id=case_id, input_root=inputs, manifest_path=manifest,
        output_root=tmp_path / "out",
    )
    assert result["panel_count"] == 6
    assert result["trace_role"] == "dwi_trace_run_03"
    assert result["trace_semantics"] == "last_ordered_run_not_claimed_as_high_b"
    assert result["coverage"]["expected_trace_planes"] == [3, 4, 5, 6, 7, 8]
    assert result["coverage"]["rendered_trace_planes"] == [3, 4, 5, 6, 7, 8]
    assert result["coverage"]["gate_passed"] is True
    assert result["ground_truth_read"] is False
    assert result["lesion_mask_used"] is False
    panel = tmp_path / "out" / case_id / result["panels"][0]["image"]
    with Image.open(panel) as image:
        assert image.size == (896, 896)
    assert sum(tile["show_liver_contour"] for tile in result["panels"][0]["tiles"]) == 1


def test_aborts_when_trace_does_not_cover_liver_physical_points(tmp_path: Path):
    case_id, inputs, manifest = _fixture(tmp_path, dwi_origin=(500.0, 0.0, 0.0))
    with pytest.raises(PipelineError, match="95%"):
        generate_multisequence_panel_set(
            case_id=case_id, input_root=inputs, manifest_path=manifest,
            output_root=tmp_path / "out",
        )
