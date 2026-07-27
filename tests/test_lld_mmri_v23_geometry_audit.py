from __future__ import annotations

import json
from pathlib import Path

import SimpleITK as sitk

from dtwin.benchmark import lld_mmri_v23_geometry_audit as module
from dtwin.benchmark.lld_mmri_v23_download import PHASE_SUFFIXES


def _image(origin=(0.0, 0.0, 0.0)):
    image = sitk.Image([5, 6, 7], sitk.sitkFloat32)
    image.SetSpacing((1.0, 1.1, 2.0))
    image.SetOrigin(origin)
    return image


def _manifest(tmp_path: Path, monkeypatch, *, mismatch=False):
    root = tmp_path / "download"
    images = root / "images"
    images.mkdir(parents=True)
    records = {}
    for role in PHASE_SUFFIXES:
        path = images / f"{role}.nii.gz"
        origin = (1.0, 0.0, 0.0) if mismatch and role == "t1_arterial" else (0.0, 0.0, 0.0)
        sitk.WriteImage(_image(origin), str(path), useCompression=True)
        records[role] = {"relative_path": f"images/{path.name}"}
    value = {
        "protocol_signature": "p" * 64,
        "manifest_signature": "m" * 64,
        "cases": [{"case_id": "anon-lld-0000000000000000", "images": records}],
    }
    monkeypatch.setattr(module, "validate_lld_mmri_v23_download", lambda **_: value)
    return root


def test_geometry_audit_passes_complete_label_blind_case(monkeypatch, tmp_path: Path):
    root = _manifest(tmp_path, monkeypatch)
    output = tmp_path / "audit"
    result = module.audit_lld_mmri_v23_geometry(
        protocol_root=tmp_path / "protocol", download_root=root, output_root=output
    )
    row = json.loads((output / "cases.jsonl").read_text(encoding="utf-8"))
    assert result["technical_gate_passed"] is True
    assert result["image_count"] == 8
    assert result["ground_truth_read"] is False
    assert result["lesion_masks_read"] == 0
    assert row["dynamic_t1_same_physical_grid"] is True
    assert row["case_audit_signature"]


def test_geometry_audit_freezes_failure_before_segmentation(monkeypatch, tmp_path: Path):
    root = _manifest(tmp_path, monkeypatch, mismatch=True)
    output = tmp_path / "audit"
    result = module.audit_lld_mmri_v23_geometry(
        protocol_root=tmp_path / "protocol", download_root=root, output_root=output
    )
    row = json.loads((output / "cases.jsonl").read_text(encoding="utf-8"))
    assert result["technical_gate_passed"] is False
    assert result["status"] == "failed_do_not_segment"
    assert row["failure_code"] == "dynamic_t1_geometry_mismatch"
    assert row["dynamic_t1_mismatch_roles"] == ["t1_arterial"]
