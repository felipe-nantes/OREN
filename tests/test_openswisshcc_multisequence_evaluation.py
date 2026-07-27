import hashlib,json
import pytest
from dtwin.benchmark import openswisshcc_multisequence_evaluation as ev
from dtwin.benchmark.openswisshcc_multisequence_freeze import PAIR_BANK
from dtwin.benchmark.openswisshcc_multisequence_inference import CASE_SCHEMA,RUN_SCHEMA
from dtwin.benchmark.openswisshcc_multisequence_quality import SCHEMA as QUALITY_SCHEMA,_signature as quality_signature
from dtwin.core import PipelineError

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def run(tmp_path):
 root=tmp_path/'run';root.mkdir();ids=['anon-a','anon-b','anon-c','anon-d']
 for n,c in enumerate(ids):
  d=root/c;d.mkdir();pairs=[{"pair_id":p["pair_id"],"positive_probability":.8 if n<2 else .2} for p in PAIR_BANK]
  rows=[{"panel_number":1,"score":{"pairs":pairs,"final_decision":None,"ground_truth_read":False}}]
  sp=d/'pairwise_panel_scores.json';sp.write_text(json.dumps(rows));m={"schema":CASE_SCHEMA,"status":"scores_only_no_decision","experiment_signature":"exp","scores_sha256":sha(sp),"panel_count":1,"final_decision":None,"ground_truth_read":False,"metrics_calculated":False,"within_180_seconds":True};(d/'pairwise_manifest.json').write_text(json.dumps(m))
 summary={"schema":RUN_SCHEMA,"status":"complete","case_count":4,"experiment_signature":"exp","mean_case_seconds":10,"max_case_seconds":20,"all_cases_within_180_seconds":True,"final_decision":None,"ground_truth_read":False,"metrics_calculated":False};(root/'summary.json').write_text(json.dumps(summary))
 labels=tmp_path/'labels.jsonl';records=[]
 for n,c in enumerate(ids):records.append({"schema":"argos-openswisshcc-ground-truth-v1","case_id":c,"public_subject_id":f"sub-{n}","label":"POSITIVE" if n<2 else "NEGATIVE","target_condition":"hcc_presence","label_basis":"test","review_status":"reviewed"})
 labels.write_text('\n'.join(json.dumps(x) for x in records));return root,labels
def metrics():return {"tp":2,"tn":2,"fp":0,"fn":0,"sensitivity":1.0,"specificity":1.0,"balanced_accuracy":1.0,"minimum_gate_metric":1.0,"passed_75_75":True}
def patch_metrics(monkeypatch):
 monkeypatch.setattr(ev,"_best_threshold",lambda v,t:(.5,metrics()));monkeypatch.setattr(ev,"_loocv",lambda v,t:metrics());monkeypatch.setattr(ev,"_repeated_stratified_cv",lambda v,t:{"runs_passing_75_75":50});monkeypatch.setattr(ev,"_nested_repeated_cv",lambda m,t:{"runs_passing_75_75":50})

def test_evaluation_opens_labels_only_after_blind_artifacts_and_reports_ci(tmp_path,monkeypatch):
 root,labels=run(tmp_path);patch_metrics(monkeypatch);r=ev.evaluate_multisequence_scores(scores_root=root,labels_path=labels,output_dir=tmp_path/'eval',expected_positive=2,expected_negative=2)
 assert r["qualified"] is True and r["time_gate_180_seconds_passed"] is True and len(r["primary_loocv_confidence_intervals"]["sensitivity_95"])==2
def test_corrupt_blind_artifact_fails_before_missing_labels_are_opened(tmp_path):
 root,_=run(tmp_path);(root/'anon-a'/'pairwise_panel_scores.json').write_text('[]')
 with pytest.raises(PipelineError,match='Caso v9 cego invalido'):ev.evaluate_multisequence_scores(scores_root=root,labels_path=tmp_path/'missing.jsonl',output_dir=tmp_path/'eval',expected_positive=2,expected_negative=2)
def test_evaluation_derives_class_counts_after_blind_validation(tmp_path,monkeypatch):
 root,labels=run(tmp_path);patch_metrics(monkeypatch);r=ev.evaluate_multisequence_scores(scores_root=root,labels_path=labels,output_dir=tmp_path/'eval',expected_total=4)
 assert r["positive_count"]==2 and r["negative_count"]==2
def test_signed_quality_exclusion_allows_full_ground_truth_audit(tmp_path,monkeypatch):
 root,labels=run(tmp_path);extra={"schema":"argos-openswisshcc-ground-truth-v1","case_id":"anon-x","public_subject_id":"sub-x","label":"NEGATIVE","target_condition":"hcc_presence","label_basis":"test","review_status":"reviewed"};labels.write_text(labels.read_text()+'\n'+json.dumps(extra))
 decisions=[]
 for case_id in ['anon-a','anon-b','anon-c','anon-d']:
  decisions.append({"case_id":case_id,"status":"approved_primary","reason_code":None,"manifest_sha256":"a"*64,"panel_set_sha256":"b"*64,"panel_count":1,"unavailable_tile_count":0})
 decisions.append({"case_id":"anon-x","status":"technical_quality_exclusion","reason_code":"severe_multisequence_quality_degradation","manifest_sha256":"c"*64,"panel_set_sha256":"d"*64,"panel_count":1,"unavailable_tile_count":0})
 review={"schema":QUALITY_SCHEMA,"review_status":"blind_technical_quality_complete","reviewer":"jm","reviewed_at_utc":"2026-07-15T00:00:00+00:00","source_cohort_signature":"e"*64,"source_case_count":5,"approved_case_count":4,"excluded_case_count":1,"decisions":decisions,"research_only":True,"clinical_use_allowed":False,"ground_truth_read":False,"lesion_mask_used":False,"inference_executed":False};review["quality_review_signature"]=quality_signature(review);q=tmp_path/'quality.json';q.write_text(json.dumps(review));patch_metrics(monkeypatch)
 r=ev.evaluate_multisequence_scores(scores_root=root,labels_path=labels,output_dir=tmp_path/'eval',expected_total=4,quality_review_path=q)
 assert r["positive_count"]==2 and r["negative_count"]==2 and r["technical_quality_exclusion_audit"]["excluded_cases"]==[{"case_id":"anon-x","reason_code":"severe_multisequence_quality_degradation"}]
