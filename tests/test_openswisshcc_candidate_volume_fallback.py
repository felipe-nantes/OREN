from __future__ import annotations

import json

import pytest

from dtwin.benchmark.openswisshcc_candidate_volume_fallback import FALLBACK_REASON, _validate_timing_plan
from dtwin.benchmark.openswisshcc_candidate_volume_timing import PLAN_SCHEMA
from dtwin.benchmark.openswisshcc_highdimensional_inference import _canonical_hash
from dtwin.core import PipelineError


def _plan(path):
    base = {
        "schema": PLAN_SCHEMA,
        "status": "frozen_blind_before_v16_scores",
        "selection_used_labels": False,
        "ground_truth_read": False,
        "ground_truth_read_by_selection_process": False,
        "development_labels_previously_visible_to_orchestrator": True,
        "development_results_classification": "exploratory_only",
        "alignment_unavailable_case_count": 1,
        "alignment_unavailable_cases": [{"case_id": "anon-openswiss-0123456789abcdef", "reason": FALLBACK_REASON}],
        "holdout_opened": False,
        "research_only": True,
        "clinical_use_allowed": False,
    }
    value = {**base, "plan_signature": _canonical_hash(base)}
    path.write_text(json.dumps(value), encoding="utf-8")
    return value


def test_fallback_requires_signed_plan_and_preserves_exploratory_disclosure(tmp_path):
    path = tmp_path / "plan.json"
    value = _plan(path)
    loaded = _validate_timing_plan(path)
    assert loaded == value
    assert loaded["ground_truth_read_by_selection_process"] is False
    assert loaded["development_labels_previously_visible_to_orchestrator"] is True
    assert loaded["holdout_opened"] is False


def test_fallback_rejects_tampered_signature_or_unapproved_reason(tmp_path):
    path = tmp_path / "plan.json"
    value = _plan(path)
    value["alignment_unavailable_cases"][0]["reason"] = "manual_override"
    path.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(PipelineError, match="Assinatura"):
        _validate_timing_plan(path)

    value["plan_signature"] = _canonical_hash({key: item for key, item in value.items() if key != "plan_signature"})
    path.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(PipelineError, match="razoes"):
        _validate_timing_plan(path)
