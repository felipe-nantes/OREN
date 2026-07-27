import hashlib
import json
from pathlib import Path

import pytest

from dtwin.benchmark import openswisshcc_lesion_localizer_chunks as chunks
from dtwin.benchmark.openswisshcc_lesion_localizer import CASE_SCHEMA, RUN_SCHEMA, TASK
from dtwin.core import PipelineError


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _plan(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    plan = {
        "plan_signature": "signed-plan",
        "chunks": [
            {"chunk_number": 1, "case_ids": ["anon-a", "anon-b"]},
            {"chunk_number": 2, "case_ids": ["anon-c"]},
        ],
    }
    monkeypatch.setattr(chunks, "load_verified_selection_plan", lambda *a, **k: plan)
    path = tmp_path / "plan.json"
    path.write_text("{}", encoding="utf-8")
    return path, plan


def _materialize(root: Path, plan: dict):
    for spec in plan["chunks"]:
        chunk = root / f"chunk_{spec['chunk_number']:03d}"
        chunk.mkdir(parents=True)
        manifests = []
        for sequence, case_id in enumerate(spec["case_ids"], 1):
            case = chunk / case_id
            raw_dir = case / "raw_model_output"
            raw_dir.mkdir(parents=True)
            raw = raw_dir / "liver_lesions.nii.gz"
            filtered = case / "liver_lesion_candidates_in_liver.nii.gz"
            raw.write_bytes(f"raw-{case_id}".encode())
            filtered.write_bytes(f"filtered-{case_id}".encode())
            manifest = {
                "schema": CASE_SCHEMA,
                "case_id": case_id,
                "status": "candidate_scores_only_no_decision",
                "sequence": sequence,
                "task": TASK,
                "model_version": "test-model",
                "raw_candidate_mask_sha256": _sha(raw),
                "filtered_candidate_mask_sha256": _sha(filtered),
                "features": {"candidate_present": True, "total_candidate_volume_mm3": 10.0},
                "elapsed_seconds": 1.0,
                "within_90_seconds": True,
                "ground_truth_lesion_mask_used": False,
                "ground_truth_read": False,
                "metrics_calculated": False,
                "final_decision": None,
                "research_only": True,
                "clinical_use_allowed": False,
                "requires_human_review": True,
            }
            (case / "localizer_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
            manifests.append(manifest)
        summary = {
            "schema": RUN_SCHEMA,
            "status": "complete_scores_only_no_decision",
            "case_count": len(spec["case_ids"]),
            "case_ids": spec["case_ids"],
            "selection_signature": "signed-plan",
            "task": TASK,
            "model_version": "test-model",
            "input_manifest_sha256": "input-hash",
            "all_cases_within_90_seconds": True,
            "total_wall_seconds": float(len(manifests)),
            "ground_truth_lesion_mask_used": False,
            "ground_truth_read": False,
            "metrics_calculated": False,
            "final_decision": None,
            "research_only": True,
            "clinical_use_allowed": False,
        }
        (chunk / "summary.json").write_text(json.dumps(summary), encoding="utf-8")


def test_merge_is_complete_atomic_and_preserves_nested_masks(tmp_path, monkeypatch):
    plan_path, plan = _plan(tmp_path, monkeypatch)
    root = tmp_path / "chunks"
    _materialize(root, plan)
    out = tmp_path / "merged"
    result = chunks.merge_localizer_chunks(
        chunks_root=root, selection_plan_path=plan_path, output_root=out, expected_case_count=3
    )
    assert result["case_count"] == 3
    assert result["ground_truth_read"] is False
    assert result["metrics_calculated"] is False
    assert (out / "anon-a" / "raw_model_output" / "liver_lesions.nii.gz").is_file()


def test_missing_case_aborts_without_partial_publication(tmp_path, monkeypatch):
    plan_path, plan = _plan(tmp_path, monkeypatch)
    root = tmp_path / "chunks"
    _materialize(root, plan)
    import shutil

    shutil.rmtree(root / "chunk_001" / "anon-a")
    out = tmp_path / "merged"
    with pytest.raises(PipelineError, match="planejados"):
        chunks.merge_localizer_chunks(
            chunks_root=root, selection_plan_path=plan_path, output_root=out, expected_case_count=3
        )
    assert not out.exists()


def test_tampered_mask_aborts(tmp_path, monkeypatch):
    plan_path, plan = _plan(tmp_path, monkeypatch)
    root = tmp_path / "chunks"
    _materialize(root, plan)
    (root / "chunk_002" / "anon-c" / "liver_lesion_candidates_in_liver.nii.gz").write_bytes(b"tampered")
    out = tmp_path / "merged"
    with pytest.raises(PipelineError, match="adulterada"):
        chunks.merge_localizer_chunks(
            chunks_root=root, selection_plan_path=plan_path, output_root=out, expected_case_count=3
        )
    assert not out.exists()


def test_planned_chunk_rejects_invalid_number():
    plan = {"chunks": [{"chunk_number": 1, "case_ids": ["anon-a"]}]}
    assert chunks.planned_chunk(plan, 1) == ["anon-a"]
    with pytest.raises(PipelineError, match="Numero"):
        chunks.planned_chunk(plan, 2)
