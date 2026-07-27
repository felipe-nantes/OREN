import hashlib,json
from pathlib import Path
import pytest
from dtwin.benchmark.openswisshcc_multisequence_batch import COHORT_SCHEMA
from dtwin.benchmark.openswisshcc_multisequence_panel import SCHEMA
from dtwin.benchmark.openswisshcc_multisequence_quality import create_quality_review
from dtwin.benchmark import openswisshcc_multisequence_quality_cohort as bundle

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def source(tmp_path):
 root=tmp_path/"source";records=[]
 for case_id in ("anon-a","anon-b"):
  d=root/case_id;d.mkdir(parents=True);image=d/"p.png";image.write_bytes(case_id.encode())
  panel={"panel_number":1,"panel_total":1,"image":"p.png","bytes":image.stat().st_size,"sha256":sha(image),"trace_plane_index":1,"tiles":[]}
  m={"schema":SCHEMA,"case_id":case_id,"panel_count":1,"panels":[panel],"trace_role":"dwi_trace_run_03","t2_role":"t2_blade","coverage":{"gate_passed":True,"missing_trace_planes":[],"duplicate_trace_planes":[],"unavailable_tiles":[]},"ground_truth_read":False,"lesion_mask_used":False}
  mp=d/"multisequence_manifest.json";mp.write_text(json.dumps(m));records.append({"case_id":case_id,"panel_count":1,"trace_role":"dwi_trace_run_03","t2_role":"t2_blade","manifest_sha256":sha(mp)})
 cohort={"schema":COHORT_SCHEMA,"case_count":2,"panel_count":2,"cases":records,"cohort_signature":"source-signature","research_only":True,"clinical_use_allowed":False,"ground_truth_read":False,"lesion_mask_used":False,"inference_executed":False}
 (root/"cohort_manifest.json").write_text(json.dumps(cohort));return root
def quality(root,tmp_path):
 decisions={"anon-a":{"status":"approved_primary","reason_code":None},"anon-b":{"status":"technical_quality_exclusion","reason_code":"severe_multisequence_quality_degradation"}}
 path=tmp_path/"quality.json";create_quality_review(panel_root=root,output_path=path,reviewer="jm",decisions=decisions,expected_case_count=2);return path

def test_bundle_atomically_separates_primary_and_stress_without_changing_bytes(tmp_path):
 root=source(tmp_path);review=quality(root,tmp_path);out=tmp_path/"bundle"
 result=bundle.build_quality_bundle(source_root=root,quality_review_path=review,output_root=out,expected_source_count=2)
 assert result["primary_case_count"]==1 and result["stress_case_count"]==1
 assert (out/"primary"/"anon-a"/"p.png").read_bytes()==b"anon-a"
 assert (out/"stress"/"anon-b"/"p.png").read_bytes()==b"anon-b"
 assert not (out/"primary"/"anon-b").exists()

def test_bundle_failure_does_not_publish_partial_output(tmp_path,monkeypatch):
 root=source(tmp_path);review=quality(root,tmp_path);out=tmp_path/"bundle"
 monkeypatch.setattr(bundle,"_link_tree",lambda *a,**k:(_ for _ in ()).throw(RuntimeError("fail")))
 with pytest.raises(RuntimeError,match="fail"):bundle.build_quality_bundle(source_root=root,quality_review_path=review,output_root=out,expected_source_count=2)
 assert not out.exists()
