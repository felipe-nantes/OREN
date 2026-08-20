from __future__ import annotations

import json
from pathlib import Path

import pytest

from dtwin.benchmark.openswisshcc_candidate_volume_timing import (
    PLAN_SCHEMA,
    SCENARIOS,
    build_timing_selection_plan,
)
from dtwin.benchmark.openswisshcc_lesion_localizer import (
    CASE_SCHEMA as LOCALIZER_CASE_SCHEMA,
)
from dtwin.benchmark.openswisshcc_lesion_localizer_chunks import MERGED_RUN_SCHEMA
from dtwin.core import PipelineError


def _write(path: Path, value: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def _case(localizer_root, alignment_root, case_id, voxels, localizer_seconds, alignment_seconds):
    components = [{"component_id": index, "voxels": value, "rank_by_volume": index} for index, value in enumerate(voxels, 1)]
    total = sum(voxels)
    _write(localizer_root / case_id / "localizer_manifest.json", {
        "schema": LOCALIZER_CASE_SCHEMA,
        "case_id": case_id,
        "status": "candidate_scores_only_no_decision",
        "features": {"inside_liver_voxels": total, "components": components},
        "elapsed_seconds": localizer_seconds,
        "ground_truth_read": False,
        "ground_truth_lesion_mask_used": False,
        "final_decision": None,
        "research_only": True,
        "clinical_use_allowed": False,
    })
    _write(alignment_root / case_id / "alignment_manifest.json", {
        "schema": "argos-public-liver-mri-alignment-v1",
        "case_id": case_id,
        "reference_phase": "venous",
        "elapsed_seconds": alignment_seconds,
        "research_only": True,
        "clinical_use_allowed": False,
    })


def _cohort(tmp_path):
    localizer = tmp_path / "localizer"
    alignment = tmp_path / "alignment"
    cases = [
        ("anon-fallback-fast", [], 10, 5),
        ("anon-fallback-slow", [], 20, 5),
        ("anon-one-fast", [100], 11, 5),
        ("anon-one-slow", [100], 21, 5),
        ("anon-three-fast", [60, 20, 20], 12, 5),
        ("anon-three-slow", [60, 20, 20, 1], 22, 5),
        ("anon-five-fast", [25, 20, 15, 10, 10, 8, 7, 5], 13, 5),
        ("anon-five-slow", [25, 20, 15, 10, 10, 8, 7, 5], 23, 5),
    ]
    for args in cases:
        _case(localizer, alignment, *args)
    _write(localizer / "summary.json", {
        "schema": MERGED_RUN_SCHEMA,
        "status": "complete_scores_only_no_decision",
        "case_count": len(cases),
        "case_ids": [item[0] for item in cases],
        "ground_truth_read": False,
        "ground_truth_lesion_mask_used": False,
        "final_decision": None,
    })
    return localizer, alignment


def test_plan_selects_slowest_blind_case_for_each_frozen_scenario(tmp_path):
    localizer, alignment = _cohort(tmp_path)
    plan = build_timing_selection_plan(localizer_root=localizer, alignment_root=alignment, out_path=tmp_path / "plan.json")
    assert plan["schema"] == PLAN_SCHEMA
    assert [item["scenario"] for item in plan["selected_cases"]] == list(SCENARIOS)
    assert [item["case_id"] for item in plan["selected_cases"]] == ["anon-fallback-slow", "anon-one-slow", "anon-three-slow", "anon-five-slow"]
    assert [item["candidate_stack_count"] for item in plan["selected_cases"]] == [1, 1, 3, 5]
    assert plan["selection_used_labels"] is False
    assert plan["ground_truth_read_by_selection_process"] is False
    assert plan["development_labels_previously_visible_to_orchestrator"] is True
    assert plan["development_results_classification"] == "exploratory_only"
    assert plan["holdout_opened"] is False
    assert len(plan["plan_signature"]) == 64


def test_plan_records_missing_alignment_without_selecting_or_hiding_case(tmp_path):
    localizer, alignment = _cohort(tmp_path)
    (alignment / "anon-one-fast" / "alignment_manifest.json").unlink()
    plan = build_timing_selection_plan(localizer_root=localizer, alignment_root=alignment, out_path=tmp_path / "plan.json")
    assert plan["source_case_count"] == 8
    assert plan["alignment_available_case_count"] == 7
    assert plan["alignment_unavailable_case_count"] == 1
    assert plan["alignment_unavailable_cases"] == [{
        "case_id": "anon-one-fast",
        "scenario": "one_candidate",
        "candidate_stack_count": 1,
        "reason": "alignment_manifest_missing_after_blind_dice_gate",
        "localizer_elapsed_seconds": 11.0,
        "localizer_manifest_sha256": plan["alignment_unavailable_cases"][0]["localizer_manifest_sha256"],
    }]
    assert all(item["case_id"] != "anon-one-fast" for item in plan["selected_cases"])


def test_plan_is_reproducible_and_refuses_divergent_overwrite(tmp_path):
    localizer, alignment = _cohort(tmp_path)
    path = tmp_path / "plan.json"
    first = build_timing_selection_plan(localizer_root=localizer, alignment_root=alignment, out_path=path)
    assert build_timing_selection_plan(localizer_root=localizer, alignment_root=alignment, out_path=path) == first
    manifest = localizer / "anon-five-slow" / "localizer_manifest.json"
    value = json.loads(manifest.read_text())
    value["elapsed_seconds"] = 1
    _write(manifest, value)
    with pytest.raises(PipelineError, match="diverge"):
        build_timing_selection_plan(localizer_root=localizer, alignment_root=alignment, out_path=path)


def test_plan_aborts_when_a_required_scenario_is_absent(tmp_path):
    localizer, alignment = _cohort(tmp_path)
    summary_path = localizer / "summary.json"
    summary = json.loads(summary_path.read_text())
    summary["case_ids"] = [case for case in summary["case_ids"] if "five" not in case]
    summary["case_count"] = len(summary["case_ids"])
    _write(summary_path, summary)
    with pytest.raises(PipelineError, match="five_candidates"):
        build_timing_selection_plan(localizer_root=localizer, alignment_root=alignment, out_path=tmp_path / "plan.json")