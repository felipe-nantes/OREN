"""Signed blind chunk plan and atomic merger for long multisequence v9 inference."""
from __future__ import annotations
import hashlib,json,os,shutil,statistics,uuid
from pathlib import Path
from typing import Any
from dtwin.benchmark.openswisshcc_alignment import _publish_directory,_sha256
from dtwin.benchmark.openswisshcc_multisequence_freeze import verify_multisequence_freeze
from dtwin.benchmark.openswisshcc_multisequence_gate import verify_multisequence_review
from dtwin.benchmark.openswisshcc_multisequence_inference import CASE_SCHEMA,RUN_SCHEMA
from dtwin.core import PipelineError

PLAN_SCHEMA="argos-openswisshcc-multisequence-chunk-plan-v1"
def _canonical(v:Any)->str:return hashlib.sha256(json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(",",":")).encode()).hexdigest()
def _load(p):
 try:v=json.loads(Path(p).read_text(encoding="utf-8"))
 except (OSError,json.JSONDecodeError) as exc:raise PipelineError(f"JSON de chunk v9 invalido: {p}") from exc
 if not isinstance(v,dict):raise PipelineError("JSON de chunk v9 deve ser objeto.")
 return v
def create_chunk_plan(*,panel_root:Path,review_path:Path,freeze_path:Path,config_path:Path,output_path:Path,expected_case_count:int=87,chunk_size:int=8):
 if not 1<=int(chunk_size)<=20:raise PipelineError("chunk_size deve estar em [1,20].")
 freeze=verify_multisequence_freeze(panel_root=panel_root,review_path=review_path,config_path=config_path,freeze_path=freeze_path,expected_case_count=expected_case_count)
 review=verify_multisequence_review(panel_root=panel_root,review_path=review_path,expected_case_count=expected_case_count)
 ids=[r["case_id"] for r in review["cases"]];ordered=sorted(ids,key=lambda x:hashlib.sha256(x.encode()).hexdigest())
 chunks=[{"chunk_number":n+1,"case_ids":ordered[i:i+chunk_size]} for n,i in enumerate(range(0,len(ordered),chunk_size))]
 payload={"schema":PLAN_SCHEMA,"experiment_signature":freeze["experiment_signature"],"review_signature":review["review_signature"],"case_count":len(ordered),"chunk_size":int(chunk_size),"chunk_count":len(chunks),"ordering":"sha256_case_id_ascending","chunks":chunks,"ground_truth_read":False,"inference_executed":False}
 payload["plan_signature"]=_canonical(payload);out=Path(output_path).resolve()
 if out.exists():raise PipelineError("Plano de chunks v9 ja existe.")
 out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(payload,indent=2,sort_keys=True)+"\n",encoding="utf-8");return payload
def verify_chunk_plan(*,plan_path:Path,experiment_signature:str,review_signature:str,expected_case_count:int):
 plan=_load(plan_path);signed={k:v for k,v in plan.items() if k!="plan_signature"}
 if plan.get("schema")!=PLAN_SCHEMA or plan.get("plan_signature")!=_canonical(signed) or plan.get("experiment_signature")!=experiment_signature or plan.get("review_signature")!=review_signature or plan.get("case_count")!=expected_case_count or plan.get("ground_truth_read") is not False or plan.get("inference_executed") is not False:raise PipelineError("Plano de chunks v9 invalido.")
 flat=[c for chunk in plan.get("chunks",[]) for c in chunk.get("case_ids",[])]
 if len(flat)!=expected_case_count or len(flat)!=len(set(flat)) or len(plan["chunks"])!=plan.get("chunk_count"):raise PipelineError("Particao de chunks v9 invalida.")
 return plan
def _link_case(source:Path,destination:Path):
 destination.mkdir()
 for item in source.iterdir():
  if not item.is_file():raise PipelineError("Chunk contem entrada de caso invalida.")
  try:os.link(item,destination/item.name)
  except OSError:shutil.copy2(item,destination/item.name)
def merge_chunk_runs(*,chunks_root:Path,plan_path:Path,output_root:Path):
 chunks_root=Path(chunks_root).resolve();out=Path(output_root).resolve()
 if out.exists():raise PipelineError("Run v9 consolidado ja existe.")
 raw=_load(plan_path);plan=verify_chunk_plan(plan_path=plan_path,experiment_signature=raw["experiment_signature"],review_signature=raw["review_signature"],expected_case_count=raw["case_count"])
 out.parent.mkdir(parents=True,exist_ok=True);staging=out.parent/f"._v9merge_{uuid.uuid4().hex[:8]}";staging.mkdir();manifests=[];wall=0.0
 try:
  seen=set()
  for chunk in plan["chunks"]:
   root=chunks_root/f"chunk_{chunk['chunk_number']:03d}";summary=_load(root/"summary.json")
   if summary.get("schema")!=RUN_SCHEMA or summary.get("status")!="complete" or summary.get("experiment_signature")!=plan["experiment_signature"] or summary.get("review_signature")!=plan["review_signature"] or summary.get("ground_truth_read") is not False or summary.get("metrics_calculated") is not False:raise PipelineError("Resumo de chunk v9 invalido.")
   visible=sorted(p.name for p in root.iterdir() if p.is_dir() and not p.name.startswith("."))
   if sorted(chunk["case_ids"])!=visible:raise PipelineError("Chunk v9 nao contem os casos planejados.")
   for case_id in chunk["case_ids"]:
    if case_id in seen:
     raise PipelineError("Caso duplicado entre chunks.")
    seen.add(case_id)
    source=root/case_id;m=_load(source/"pairwise_manifest.json")
    if m.get("schema")!=CASE_SCHEMA or m.get("experiment_signature")!=plan["experiment_signature"] or m.get("scores_sha256")!=_sha256(source/"pairwise_panel_scores.json") or m.get("within_180_seconds") is not True:raise PipelineError("Caso de chunk v9 invalido.")
    _link_case(source,staging/case_id);manifests.append(m)
   wall+=float(summary.get("total_wall_seconds",0))
  if seen!=set(c for x in plan["chunks"] for c in x["case_ids"]):raise PipelineError("Merge v9 incompleto.")
  elapsed=[float(m["elapsed_seconds"]) for m in manifests]
  summary={"schema":RUN_SCHEMA,"status":"complete","case_count":len(manifests),"panel_count":sum(int(m["panel_count"]) for m in manifests),"success_count":len(manifests),"failure_count":0,"case_ids":sorted(seen),"experiment_signature":plan["experiment_signature"],"review_signature":plan["review_signature"],"plan_signature":plan["plan_signature"],"model_id":manifests[0]["model_id"],"model_version":manifests[0]["model_version"],"mean_case_seconds":statistics.fmean(elapsed),"max_case_seconds":max(elapsed),"all_cases_within_180_seconds":all(m["within_180_seconds"] for m in manifests),"total_wall_seconds":wall,"final_decision":None,"ground_truth_read":False,"metrics_calculated":False,"research_only":True,"clinical_use_allowed":False}
  (staging/"summary.json").write_text(json.dumps(summary,indent=2,sort_keys=True)+"\n",encoding="utf-8");_publish_directory(staging,out);return summary
 except Exception:shutil.rmtree(staging,ignore_errors=True);raise




