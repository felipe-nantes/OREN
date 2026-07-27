from __future__ import annotations

import copy

import pytest

from dtwin.benchmark.openswisshcc_candidate_volume_timing import SCENARIOS
from dtwin.benchmark.openswisshcc_candidate_volume_timing_run import (
    _validate_plan_bundle_binding,
    projected_pipeline_seconds,
)
from dtwin.core import PipelineError


def _context():
    counts = [1, 1, 3, 5]
    selected = [
        {
            "scenario": scenario,
            "case_id": f"anon-{index:016d}",
            "candidate_stack_count": count,
            "fallback_no_candidate": scenario == "fallback",
            "alignment_available": True,
            "alignment_unavailable_reason": None,
        }
        for index, (scenario, count) in enumerate(zip(SCENARIOS, counts, strict=True), 1)
    ]
    plan = {"plan_signature": "a" * 64, "selected_cases": selected}
    bundle = {
        "case_ids": [item["case_id"] for item in selected],
        "cases": [{"candidate_stack_count": count} for count in counts],
        "cohort": {
            "source_timing_plan_sha256": "b" * 64,
            "source_timing_plan_signature": plan["plan_signature"],
            "protocol": {"case_time_gate_seconds": 180.0},
            "timing_execution_started": False,
        },
    }
    return bundle, plan


def test_projected_pipeline_adds_historical_preprocessing_and_fresh_reader():
    assert projected_pipeline_seconds(55.0, 124.9) == pytest.approx(179.9)
    assert projected_pipeline_seconds(55.0, 125.1) > 180.0
    with pytest.raises(PipelineError):
        projected_pipeline_seconds(-1, 20)


def test_plan_bundle_binding_requires_exact_cases_counts_and_time_gate(tmp_path, monkeypatch):
    bundle, plan = _context()
    path = tmp_path / "plan.json"
    path.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(
        "dtwin.benchmark.openswisshcc_candidate_volume_timing_run._sha256",
        lambda _: "b" * 64,
    )
    selected = _validate_plan_bundle_binding(bundle, path, plan)
    assert [item["candidate_stack_count"] for item in selected] == [1, 1, 3, 5]

    changed = copy.deepcopy(bundle)
    changed["cases"][3]["candidate_stack_count"] = 4
    with pytest.raises(PipelineError, match="plano assinado"):
        _validate_plan_bundle_binding(changed, path, plan)


@pytest.mark.parametrize("field,value", [("timing_execution_started", True), ("source_timing_plan_signature", "c" * 64)])
def test_plan_bundle_binding_rejects_reuse_or_signature_change(tmp_path, monkeypatch, field, value):
    bundle, plan = _context()
    path = tmp_path / "plan.json"
    path.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(
        "dtwin.benchmark.openswisshcc_candidate_volume_timing_run._sha256",
        lambda _: "b" * 64,
    )
    bundle["cohort"][field] = value
    with pytest.raises(PipelineError):
        _validate_plan_bundle_binding(bundle, path, plan)
