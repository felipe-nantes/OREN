from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
import SimpleITK as sitk

from dtwin.benchmark import lld_mmri_v23_harmonization as module
from dtwin.benchmark.lld_mmri_v23_geometry_audit import AUDIT_SCHEMA
from dtwin.benchmark.lld_mmri_v23_geometry_audit import CASE_SCHEMA as AUDIT_CASE_SCHEMA
from dtwin.benchmark.openswisshcc_alignment import _sha256
from dtwin.benchmark.openswisshcc_v20_fusion import _canonical_sha
from dtwin.core import PipelineError


def _image(*, origin=(0.0, 0.0, 0.0), size=(10, 12, 8)):
    array = np.arange(np.prod(tuple(reversed(size))), dtype=np.uint8).reshape(tuple(reversed(size)))
    image = sitk.GetImageFromArray(array)
    image.SetSpacing((1.0, 1.0, 2.0))
    image.SetOrigin(origin)
    return image


def _sources(tmp_path: Path, monkeypatch):
    download = tmp_path / "download"
    cases = []
    audit_rows = []
    for index in range(2):
        case_id = f"anon-lld-{index:016d}"
        images = {}
        for role in module.DYNAMIC_ROLES:
            mismatch = index == 1 and role == "t1_native"
            image = _image(origin=(0.0, 0.0, -2.0), size=(10, 12, 10)) if mismatch else _image()
            path = download / "images" / f"{case_id}_{role}.nii.gz"
            path.parent.mkdir(parents=True, exist_ok=True)
            sitk.WriteImage(image, str(path), useCompression=True)
            images[role] = {"relative_path": f"images/{path.name}", "sha256": _sha256(path)}
        cases.append({"case_id": case_id, "images": images})
        audit_base = {
            "schema": AUDIT_CASE_SCHEMA,
            "case_id": case_id,
            "status": "failed" if index == 1 else "passed",
            "ground_truth_read": False,
            "lesion_masks_read": 0,
        }
        audit_row = dict(audit_base)
        audit_row["case_audit_signature"] = _canonical_sha(audit_base)
        audit_rows.append(audit_row)
    manifest = {
        "case_count": 2,
        "image_count": 8,
        "cases": cases,
        "protocol_signature": "p" * 64,
        "manifest_signature": "m" * 64,
    }
    monkeypatch.setattr(module, "validate_lld_mmri_v23_download", lambda **_: manifest)
    audit = tmp_path / "audit"
    audit.mkdir()
    cases_path = audit / "cases.jsonl"
    cases_path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in audit_rows), encoding="utf-8"
    )
    summary_base = {
        "schema": AUDIT_SCHEMA,
        "status": "failed_do_not_segment",
        "technical_gate_passed": False,
        "cases_sha256": _sha256(cases_path),
        "protocol_signature": manifest["protocol_signature"],
        "download_manifest_signature": manifest["manifest_signature"],
        "case_count": 2,
        "image_count": 8,
        "case_ids": [case["case_id"] for case in cases],
        "ground_truth_read": False,
        "labels_read": False,
        "lesion_masks_read": 0,
    }
    summary = dict(summary_base)
    summary["audit_signature"] = _canonical_sha(summary_base)
    (audit / "summary.json").write_text(json.dumps(summary), encoding="utf-8")
    return download, audit, manifest


def test_harmonizes_only_mismatched_dynamic_phase(monkeypatch, tmp_path: Path):
    download, audit, manifest = _sources(tmp_path, monkeypatch)
    output = tmp_path / "harmonized"
    result = module.harmonize_lld_mmri_v23_dynamic_t1(
        protocol_root=tmp_path / "protocol",
        download_root=download,
        failed_audit_root=audit,
        output_root=output,
    )
    assert result["case_count"] == 2
    assert result["transformed_image_count"] == 1
    assert result["unchanged_image_count"] == 7
    assert result["motion_correction_claimed"] is False
    assert result["anatomical_registration_claimed"] is False
    assert result["eligible_for_inference"] is False
    assert result["ground_truth_read"] is False
    assert result["lesion_masks_read"] == 0
    verified = module.verify_lld_mmri_v23_harmonization(
        protocol_root=tmp_path / "protocol",
        download_root=download,
        failed_audit_root=audit,
        harmonization_root=output,
    )
    assert verified["harmonization_signature"] == result["harmonization_signature"]
    assert result["case_ids"] == [case["case_id"] for case in manifest["cases"]]


def test_verifier_rejects_tampered_harmonized_phase(monkeypatch, tmp_path: Path):
    download, audit, _ = _sources(tmp_path, monkeypatch)
    output = tmp_path / "harmonized"
    module.harmonize_lld_mmri_v23_dynamic_t1(
        protocol_root=tmp_path / "protocol",
        download_root=download,
        failed_audit_root=audit,
        output_root=output,
    )
    phase = next((output / "cases").rglob("t1_native.nii.gz"))
    phase.write_bytes(b"tampered")
    with pytest.raises(PipelineError, match="ausente ou adulterado"):
        module.verify_lld_mmri_v23_harmonization(
            protocol_root=tmp_path / "protocol",
            download_root=download,
            failed_audit_root=audit,
            harmonization_root=output,
        )
