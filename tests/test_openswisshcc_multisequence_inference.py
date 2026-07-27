import hashlib,json,time
from pathlib import Path
import pytest
from dtwin.benchmark import openswisshcc_multisequence_inference as inf
from dtwin.core import PipelineError

def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def case_root(tmp_path):
 root=tmp_path/'cohort'; case=root/'anon-a'; case.mkdir(parents=True); image=case/'p.png'; image.write_bytes(b'panel'); digest=sha(image)
 tiles=[{"role":"t1_venous","available_in_fov":True},{"role":"t2_blade","available_in_fov":False}]
 manifest={"case_id":"anon-a","panels":[{"panel_number":1,"panel_total":1,"image":"p.png","sha256":digest,"bytes":5,"trace_plane_index":4,"tiles":tiles}]}
 (case/'multisequence_manifest.json').write_text(json.dumps(manifest)); return root,digest
class Fake:
 model_id="google/medgemma-1.5-4b-it"; model_version="test"
 def __init__(self,delay=0): self.delay=delay; self.prompts=[]
 def score_panel(self,path,prompt,pairs):
  time.sleep(self.delay); self.prompts.append(prompt)
  return {"schema":inf.SCORE_SCHEMA,"panel_sha256":sha(path),"pairs":[{"pair_id":p["pair_id"],"positive_probability":0.4} for p in pairs],"final_decision":None,"ground_truth_read":False}
def gates(monkeypatch,seconds=180):
 monkeypatch.setattr(inf,"verify_multisequence_freeze",lambda **k:{"experiment_signature":"exp","max_case_seconds":seconds})
 monkeypatch.setattr(inf,"verify_multisequence_review",lambda **k:{"review_signature":"rev","cases":[{"case_id":"anon-a"}]})

def test_scores_only_runner_is_blind_atomic_and_records_missing_modality(tmp_path,monkeypatch):
 root,digest=case_root(tmp_path); gates(monkeypatch); scorer=Fake(); out=tmp_path/'run'
 result=inf.run_multisequence_scores(panel_root=root,review_path=tmp_path/'r',freeze_path=tmp_path/'f',config_path=tmp_path/'c',output_root=out,scorer=scorer,expected_case_count=1)
 assert result["status"]=="complete" and result["final_decision"] is None and result["ground_truth_read"] is False
 assert "unavailable modalities: ['t2_blade']" in scorer.prompts[0]
 case=json.loads((out/'anon-a'/'pairwise_manifest.json').read_text()); assert case["metrics_calculated"] is False and case["within_180_seconds"] is True

def test_timeout_aborts_without_publishing_partial_run(tmp_path,monkeypatch):
 root,_=case_root(tmp_path); gates(monkeypatch,0.001); out=tmp_path/'run'
 with pytest.raises(PipelineError,match='Tempo v9 excedeu'):
  inf.run_multisequence_scores(panel_root=root,review_path=tmp_path/'r',freeze_path=tmp_path/'f',config_path=tmp_path/'c',output_root=out,scorer=Fake(0.01),expected_case_count=1)
 assert not out.exists()

def test_invalid_review_blocks_before_scoring(tmp_path,monkeypatch):
 root,_=case_root(tmp_path); scorer=Fake()
 monkeypatch.setattr(inf,"verify_multisequence_freeze",lambda **k:(_ for _ in ()).throw(PipelineError("review missing")))
 with pytest.raises(PipelineError,match='review missing'):
  inf.run_multisequence_scores(panel_root=root,review_path=tmp_path/'r',freeze_path=tmp_path/'f',config_path=tmp_path/'c',output_root=tmp_path/'out',scorer=scorer,expected_case_count=1)
 assert scorer.prompts==[]
