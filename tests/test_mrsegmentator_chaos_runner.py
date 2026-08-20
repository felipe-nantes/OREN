from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
import SimpleITK as sitk

from dtwin.benchmark.mrsegmentator_chaos_runner import (
    LIVER_LABEL,
    _publish_directory,
    extract_liver_label,
    verify_run,
)
from dtwin.core import PipelineError, sha256_of


def _write(path: Path, array: np.ndarray, spacing=(1.0, 1.2, 2.0)):
    path.parent.mkdir(parents=True, exist_ok=True)
    image = sitk.GetImageFromArray(array)
    image.SetSpacing(spacing)
    sitk.WriteImage(image, str(path), useCompression=True)


def test_extract_liver_label_ignores_other_organs(tmp_path):
    source = tmp_path / "source.nii.gz"
    labelmap = tmp_path / "labels.nii.gz"
    output = tmp_path / "liver.nii.gz"
    _write(source, np.zeros((8, 9, 10), dtype=np.float32))
    labels = np.zeros((8, 9, 10), dtype=np.uint8)
    labels[1:4, 1:4, 1:4] = 2
    labels[3:7, 3:8, 3:9] = LIVER_LABEL
    _write(labelmap, labels)
    result = extract_liver_label(labelmap, source, output)
    mask = sitk.GetArrayFromImage(sitk.ReadImage(str(output))) > 0
    assert int(mask.sum()) == int((labels == LIVER_LABEL).sum())
    assert result["label_value"] == LIVER_LABEL
    assert result["same_reference_grid"] is True


def test_extract_liver_label_rejects_empty_liver(tmp_path):
    source = tmp_path / "source.nii.gz"
    labelmap = tmp_path / "labels.nii.gz"
    _write(source, np.zeros((8, 9, 10), dtype=np.float32))
    _write(labelmap, np.full((8, 9, 10), 2, dtype=np.uint8))
    with pytest.raises(PipelineError, match="rotulo 5"):
        extract_liver_label(labelmap, source, tmp_path / "liver.nii.gz")


def test_publish_directory_retries_transient_windows_handle(tmp_path, monkeypatch):
    staging = tmp_path / ".run.incomplete"
    output = tmp_path / "run"
    staging.mkdir()
    (staging / "receipt.txt").write_text("ok", encoding="utf-8")
    real_replace = __import__("os").replace
    calls = {"count": 0}

    def flaky_replace(source, destination):
        calls["count"] += 1
        if calls["count"] == 1:
            raise PermissionError("transient handle")
        return real_replace(source, destination)

    monkeypatch.setattr("dtwin.benchmark.mrsegmentator_chaos_runner.os.replace", flaky_replace)
    _publish_directory(staging, output, attempts=2)
    assert calls["count"] == 2
    assert (output / "receipt.txt").read_text(encoding="utf-8") == "ok"


def test_verify_run_detects_tampered_mask(tmp_path):
    root = tmp_path / "run"
    case_id = "anon-case"
    mask = root / "masks" / f"{case_id}.nii.gz"
    raw = root / "raw" / case_id / "t1_in_seg.nii.gz"
    values = np.ones((5, 6, 7), dtype=np.uint8)
    _write(mask, values)
    _write(raw, values * LIVER_LABEL)
    row = {
        "case_id": case_id,
        "status": "completed",
        "mask_sha256": sha256_of(mask),
        "raw_labelmap_sha256": sha256_of(raw),
    }
    checkpoint = root / "checkpoint_cases.jsonl"
    checkpoint.write_text(json.dumps(row) + "\n", encoding="utf-8")
    context = {"schema": "argos-mrsegmentator-chaos-gpu-run-v2", "case_count": 1}
    summary = {
        "schema": "argos-mrsegmentator-chaos-gpu-run-v2",
        "completed_cases": 1,
        "checkpoint_sha256": sha256_of(checkpoint),
    }
    (root / "run_context.json").write_text(json.dumps(context), encoding="utf-8")
    (root / "run_summary.json").write_text(json.dumps(summary), encoding="utf-8")
    assert verify_run(root)["completed_cases"] == 1
    _write(mask, np.zeros((5, 6, 7), dtype=np.uint8))
    with pytest.raises(PipelineError, match="Hash"):
        verify_run(root)
