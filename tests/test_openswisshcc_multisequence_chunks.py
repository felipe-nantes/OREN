import hashlib,json
from pathlib import Path
import pytest
from dtwin.benchmark import openswisshcc_multisequence_chunks as chunks
from dtwin.benchmark.openswisshcc_multisequence_inference import CASE_SCHEMA,RUN_SCHEMA
from dtwin.core import PipelineError
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def plan(tmp_path,monkeypatch):
 ids=["anon-a","anon-b","anon-c"];monkeypatch.setattr(chunks,"verify_multisequence_freeze",lambda **k:{"experiment_signature":"exp"});monkeypatch.setattr(chunks,"verify_multisequence_review",lambda **k:{"review_signature":"rev","cases":[{"case_id":x} for x in ids]})
 path=tmp_path/"plan.json";r=chunks.create_chunk_plan(panel_root=tmp_path,review_path=tmp_path/"r",freeze_path=tmp_path/"f",config_path=tmp_path/"c",output_path=path,expected_case_count=3,chunk_size=2);return path,r
def materialize(root,plan):
 for spec in plan["chunks"]:
  d=root/f"chunk_{spec['chunk_number']:03d}";d.mkdir(parents=True);elapsed=[]
  for case_id in spec["case_ids"]:
   c=d/case_id;c.mkdir();scores=c/"pairwise_panel_scores.json";scores.write_text("[]");m={"schema":CASE_SCHEMA,"experiment_signature":"exp","scores_sha256":sha(scores),"within_180_seconds":True,"elapsed_seconds":10.0,"panel_count":1,"model_id":"google/medgemma-1.5-4b-it","model_version":"test"};(c/"pairwise_manifest.json").write_text(json.dumps(m));elapsed.append(10)
  s={"schema":RUN_SCHEMA,"status":"complete","experiment_signature":"exp","review_signature":"rev","ground_truth_read":False,"metrics_calculated":False,"total_wall_seconds":sum(elapsed)};(d/"summary.json").write_text(json.dumps(s))
def test_signed_plan_partitions_and_merge_is_complete(tmp_path,monkeypatch):
 pp,p=plan(tmp_path,monkeypatch);root=tmp_path/"chunks";materialize(root,p);out=tmp_path/"merged";r=chunks.merge_chunk_runs(chunks_root=root,plan_path=pp,output_root=out)
 assert r["case_count"]==3 and r["failure_count"]==0 and r["all_cases_within_180_seconds"] is True
 assert sorted(x.name for x in out.iterdir() if x.is_dir())==sorted(["anon-a","anon-b","anon-c"])
def test_missing_planned_case_aborts_without_partial_merge(tmp_path,monkeypatch):
 pp,p=plan(tmp_path,monkeypatch);root=tmp_path/"chunks";materialize(root,p);missing=p["chunks"][0]["case_ids"][0];import shutil;shutil.rmtree(root/"chunk_001"/missing);out=tmp_path/"merged"
 with pytest.raises(PipelineError,match="planejados"):chunks.merge_chunk_runs(chunks_root=root,plan_path=pp,output_root=out)
 assert not out.exists()
