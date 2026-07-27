from __future__ import annotations

import json

import numpy as np
import pytest
from PIL import Image

from dtwin.benchmark.openswisshcc_candidate_volume_full87 import (
    CONTACT_SHEET_SCHEMA,
    _contact_sheet,
    _validate_contact_sheet_file,
)
from dtwin.core import PipelineError, sha256_of


def _candidate(tmp_path):
    candidate_dir = tmp_path / "candidate_001"
    candidate_dir.mkdir()
    groups = []
    order = 0
    for role, count in (("t1_venous", 5), ("dwi_adc", 3)):
        frames = []
        for index in range(count):
            order += 1
            filename = f"frame_{order:03d}_{role}_z{index:04d}.png"
            path = candidate_dir / filename
            array = np.full((384, 384, 3), 20 + order, dtype=np.uint8)
            Image.fromarray(array, mode="RGB").save(path)
            frames.append({"filename": filename, "source_index_z": index})
        groups.append({"role": role, "frames": frames})
    return candidate_dir, {
        "case_id": "anon-0123456789abcdef",
        "candidate_number": 1,
        "candidate_total": 1,
        "frame_count": order,
        "groups": groups,
    }


def test_contact_sheet_is_deterministic_audit_only_and_uses_three_frames_per_group(tmp_path):
    candidate_dir, manifest = _candidate(tmp_path)
    first = tmp_path / "first.png"
    second = tmp_path / "second.png"
    record = _contact_sheet(candidate_dir, manifest, first)
    _contact_sheet(candidate_dir, manifest, second)
    assert record["schema"] == CONTACT_SHEET_SCHEMA
    assert record["preview_frame_count"] == 6
    assert record["source_frame_count"] == 8
    assert record["audit_only_not_model_input"] is True
    assert sha256_of(first) == sha256_of(second)
    with Image.open(first) as image:
        assert image.mode == "RGB"
        assert image.width == 384


def test_contact_sheet_preview_does_not_modify_source_frames(tmp_path):
    candidate_dir, manifest = _candidate(tmp_path)
    before = {path.name: sha256_of(path) for path in candidate_dir.glob("*.png")}
    _contact_sheet(candidate_dir, manifest, tmp_path / "sheet.png")
    after = {path.name: sha256_of(path) for path in candidate_dir.glob("*.png")}
    assert before == after


def test_contact_sheet_manifest_is_json_serializable(tmp_path):
    candidate_dir, manifest = _candidate(tmp_path)
    record = _contact_sheet(candidate_dir, manifest, tmp_path / "sheet.png")
    assert json.loads(json.dumps(record))["sha256"] == record["sha256"]


def test_contact_sheet_validator_rejects_tampering(tmp_path):
    candidate_dir, manifest = _candidate(tmp_path)
    case_id = manifest["case_id"]
    case_dir = tmp_path / case_id
    case_dir.mkdir()
    path = case_dir / "audit_candidate_001.png"
    record = _contact_sheet(candidate_dir, manifest, path)
    record["relative_path"] = f"{case_id}/{path.name}"
    assert _validate_contact_sheet_file(tmp_path.resolve(), case_id, record) == path.resolve()
    path.write_bytes(path.read_bytes() + b"tampered")
    with pytest.raises(PipelineError, match="adulterada"):
        _validate_contact_sheet_file(tmp_path.resolve(), case_id, record)