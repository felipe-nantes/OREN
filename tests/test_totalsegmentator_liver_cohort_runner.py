from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
import SimpleITK as sitk

from dtwin.benchmark.totalsegmentator_liver_cohort_runner import RUN_SCHEMA, verify_run
from dtwin.core import PipelineError, sha256_of


def _write(path: Path, array: np.ndarray):
    path.parent.mkdir(parents=True, exist_ok=True)
    sitk.WriteImage(sitk.GetImageFromArray(array), str(path), useCompression=True)


def test_verify_total_mr_run_detects_tampered_receipt(tmp_path):
    root = tmp_path / "run"
    case_id = "anon-case"
    mask = root / "masks" / f"{case_id}.nii.gz"
    receipt = root / "receipts" / f"{case_id}.json"
    _write(mask, np.ones((5, 6, 7), dtype=np.uint8))
    receipt.parent.mkdir(parents=True, exist_ok=True)
    receipt.write_text('{"engine":"TotalSegmentator"}', encoding="utf-8")
    row = {
        "case_id": case_id,
        "status": "completed",
        "mask_sha256": sha256_of(mask),
        "receipt_sha256": sha256_of(receipt),
    }
    checkpoint = root / "checkpoint_cases.jsonl"
    checkpoint.write_text(json.dumps(row) + "\n", encoding="utf-8")
    (root / "run_context.json").write_text(
        json.dumps({"schema": RUN_SCHEMA, "case_count": 1}), encoding="utf-8"
    )
    (root / "run_summary.json").write_text(
        json.dumps(
            {
                "schema": RUN_SCHEMA,
                "completed_cases": 1,
                "checkpoint_sha256": sha256_of(checkpoint),
            }
        ),
        encoding="utf-8",
    )
    assert verify_run(root)["completed_cases"] == 1
    receipt.write_text("tampered", encoding="utf-8")
    with pytest.raises(PipelineError, match="Hash"):
        verify_run(root)
