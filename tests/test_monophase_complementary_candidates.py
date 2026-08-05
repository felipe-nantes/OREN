from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from dtwin.core import PipelineError
from dtwin.learning.monophase_complementary_candidates import build_complementary_candidates
from dtwin.learning.protocol import sha256_file


def _fixture(tmp_path: Path) -> tuple[Path, Path]:
    sitk = pytest.importorskip("SimpleITK")
    inputs = tmp_path / "inputs"
    case = inputs / "anon-openswiss-test"
    case.mkdir(parents=True)
    z, y, x = np.mgrid[:32, :48, :48]
    volume = (
        500.0 * np.exp(-((z - 16) ** 2 / 70 + (y - 25) ** 2 / 120 + (x - 18) ** 2 / 90))
        + y * 2.0
        + x
    ).astype(np.float32)
    mask = np.zeros_like(volume, dtype=np.uint8)
    mask[10:24, 15:35, 8:30] = 1
    files = []
    for role in ("t2_haste", "dwi_trace_run_03", "dwi_adc", "t1_venous"):
        path = case / f"{role}.nii.gz"
        sitk.WriteImage(sitk.GetImageFromArray(volume), str(path))
        files.append({"role": role, "relative_path": f"anon-openswiss-test/{path.name}", "sha256": sha256_file(path)})
    mask_path = case / "liver.nii.gz"
    sitk.WriteImage(sitk.GetImageFromArray(mask), str(mask_path))
    files.append({"role": "liver_mask_venous", "relative_path": "anon-openswiss-test/liver.nii.gz", "sha256": sha256_file(mask_path)})
    manifest = tmp_path / "inputs.jsonl"
    manifest.write_text(json.dumps({
        "case_id": "anon-openswiss-test",
        "research_only": True,
        "ground_truth_read": False,
        "lesion_mask_present": False,
        "files": files,
    }) + "\n", encoding="utf-8")
    return manifest, inputs


def test_builds_three_real_sequences_with_exact_coverage(tmp_path: Path) -> None:
    manifest, inputs = _fixture(tmp_path)
    out = tmp_path / "out"
    result = build_complementary_candidates(
        input_manifest_path=manifest,
        input_files_root=inputs,
        workspace_root=tmp_path,
        output_root=out,
        dataset_id="external_holdout",
    )
    assert result["materialized_case_sequence_count"] == 3
    assert result["candidate_record_count"] == 42
    assert result["all_materialized_sequences_exact_coverage"] is True
    assert result["ground_truth_read"] is False
    assert result["lesion_masks_read"] == 0
    assert result["synthetic_sequences_created"] is False
    assert result["dataset_id"] == "external_holdout"
    records = [json.loads(line) for line in (out / "candidate_records.jsonl").read_text().splitlines()]
    assert {row["dataset_id"] for row in records} == {"external_holdout"}
    audit_images = list((out / "registration_audit").rglob("*.png"))
    assert len(audit_images) == 3


def test_rejects_modified_source_hash(tmp_path: Path) -> None:
    manifest, inputs = _fixture(tmp_path)
    row = json.loads(manifest.read_text())
    row["files"][0]["sha256"] = "0" * 64
    manifest.write_text(json.dumps(row) + "\n", encoding="utf-8")
    with pytest.raises(PipelineError, match="Hash da sequencia"):
        build_complementary_candidates(
            input_manifest_path=manifest,
            input_files_root=inputs,
            workspace_root=tmp_path,
            output_root=tmp_path / "out",
        )
