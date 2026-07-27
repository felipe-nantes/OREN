from pathlib import Path
import pytest
from dtwin.benchmark import openswisshcc_multisequence_quality as q
from dtwin.core import PipelineError

def state(manifest="m1"):
 records=[{"case_id":"anon-a","manifest_sha256":manifest,"panel_set_sha256":"set-a","panel_count":2,"unavailable_tiles":[]},{"case_id":"anon-b","manifest_sha256":"m2","panel_set_sha256":"set-b","panel_count":3,"unavailable_tiles":[{"role":"t2"}]}]
 return {"cohort":{"cohort_signature":"cohort"},"records":records}
def decisions():
 return {"anon-a":{"status":"approved_primary","reason_code":None},"anon-b":{"status":"technical_quality_exclusion","reason_code":"severe_multisequence_quality_degradation"}}

def test_blind_quality_review_signs_approved_and_excluded_without_labels(tmp_path,monkeypatch):
 monkeypatch.setattr(q,"validate_multisequence_cohort",lambda *a,**k:state())
 out=tmp_path/"quality.json";r=q.create_quality_review(panel_root=tmp_path,output_path=out,reviewer="human",decisions=decisions(),expected_case_count=2)
 assert r["approved_case_count"]==1 and r["excluded_case_count"]==1 and r["ground_truth_read"] is False
 assert q.verify_quality_review(panel_root=tmp_path,review_path=out,expected_case_count=2)["quality_review_signature"]==r["quality_review_signature"]
 assert "label" not in out.read_text(encoding="utf-8").lower()

def test_quality_decision_rejects_clinical_or_extra_fields(tmp_path,monkeypatch):
 monkeypatch.setattr(q,"validate_multisequence_cohort",lambda *a,**k:state());d=decisions();d["anon-b"]["label"]="POSITIVE"
 with pytest.raises(PipelineError,match="campos nao autorizados"):
  q.create_quality_review(panel_root=tmp_path,output_path=tmp_path/"q.json",reviewer="human",decisions=d,expected_case_count=2)

def test_panel_change_invalidates_quality_review(tmp_path,monkeypatch):
 current=[state()]
 monkeypatch.setattr(q,"validate_multisequence_cohort",lambda *a,**k:current[0]);out=tmp_path/"q.json"
 q.create_quality_review(panel_root=tmp_path,output_path=out,reviewer="human",decisions=decisions(),expected_case_count=2);current[0]=state("changed")
 with pytest.raises(PipelineError,match="mudaram"):
  q.verify_quality_review(panel_root=tmp_path,review_path=out,expected_case_count=2)
