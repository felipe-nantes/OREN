import json

import pytest

from dtwin.benchmark.openswisshcc_remediation import (
    _action,
    load_review_triage,
)
from dtwin.core import PipelineError


def _payload():
    return {
        "schema": "argos-openswisshcc-technical-triage-v1",
        "reviewer_source": "human-reviewer-provided-in-chat",
        "case_count": 2,
        "cases": [
            {"case_id": "anon-openswiss-a", "codes": ["M"], "note": ""},
            {"case_id": "anon-openswiss-b", "codes": ["C", "M"], "note": ""},
        ],
        "research_only": True,
        "clinical_use_allowed": False,
        "ground_truth_read": False,
        "inference_executed": False,
    }


def test_triage_accepts_only_technical_codes(tmp_path):
    path = tmp_path / "triage.json"
    path.write_text(json.dumps(_payload()), encoding="utf-8")
    result = load_review_triage(path)
    assert result["case_count"] == 2
    assert _action({"M"}) == "venous_review_fallback"
    assert _action({"C"}) == "venous_review_fallback"
    assert _action({"I"}) == "restored_source_candidate_retained"
    assert _action(set()) == "unchanged"


@pytest.mark.parametrize("code", ["Q", "POSITIVE", "NEGATIVE", "D"])
def test_triage_rejects_unknown_or_diagnostic_codes(tmp_path, code):
    payload = _payload()
    payload["cases"][0]["codes"] = [code]
    path = tmp_path / "triage.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(PipelineError, match="Códigos técnicos"):
        load_review_triage(path)


def test_triage_rejects_duplicate_case(tmp_path):
    payload = _payload()
    payload["cases"][1]["case_id"] = payload["cases"][0]["case_id"]
    path = tmp_path / "triage.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(PipelineError, match="duplicado"):
        load_review_triage(path)


def test_triage_rejects_ground_truth_flag(tmp_path):
    payload = _payload()
    payload["ground_truth_read"] = True
    path = tmp_path / "triage.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(PipelineError, match="salvaguardas"):
        load_review_triage(path)

