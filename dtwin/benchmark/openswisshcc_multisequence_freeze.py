"""Immutable experiment freeze for reviewed OpenSwissHCC multisequence v9 panels."""
from __future__ import annotations
import hashlib, json, os, uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping
from dtwin.benchmark.openswisshcc_alignment import _sha256
from dtwin.benchmark.openswisshcc_multisequence_gate import verify_multisequence_review
from dtwin.core import PipelineError
from dtwin.medgemma_client import effective_config_sha256, load_screening_config

SCHEMA="argos-openswisshcc-multisequence-freeze-v1"
PAIR_BANK=(
 {"pair_id":"focal_lesion_evidence","question":"Which statement is better supported by this liver MRI plane?","positive":"Evidence supports a suspicious focal liver lesion.","negative":"Evidence does not support a suspicious focal liver lesion."},
 {"pair_id":"focal_mass_presence","question":"Which statement best describes this liver MRI plane?","positive":"This plane shows a focal hepatic mass.","negative":"This plane does not show a focal hepatic mass."},
)
SIGNED=("schema","experiment_version","review_signature","source_cohort_signature","case_count","panel_count","config","pair_bank","pair_bank_sha256","aggregation_rule","max_case_seconds","research_only","clinical_use_allowed","ground_truth_read","lesion_mask_used","inference_executed")

def _canonical(v:Any)->str:
    return hashlib.sha256(json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(",",":")).encode()).hexdigest()
def _signature(v): return _canonical({k:v.get(k) for k in SIGNED})
def _load(path):
    try: value=json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError,json.JSONDecodeError) as exc: raise PipelineError(f"Freeze v9 invalido: {path}") from exc
    if not isinstance(value,dict): raise PipelineError("Freeze v9 deve ser objeto.")
    return value
def _config(path:Path)->dict[str,Any]:
    path=Path(path).resolve(); cfg=load_screening_config(path); med=cfg["medgemma"]; panel=cfg.get("panel",{})
    record={"filename":path.name,"raw_sha256":_sha256(path),"effective_sha256":effective_config_sha256(cfg),"model_id":med.get("model_id"),"model_version":med.get("model_version"),"response_mode":med.get("response_mode"),"timeout_seconds":med.get("timeout_seconds"),"max_retries":med.get("max_retries"),"response_validation_max_retries":med.get("response_validation_max_retries"),"panel_strategy":panel.get("strategy"),"rag_enabled":cfg.get("rag",{}).get("enabled",False)}
    if med.get("model_id")!="google/medgemma-1.5-4b-it" or med.get("model_parameter_scale")!="4B": raise PipelineError("Freeze v9 exige exatamente MedGemma 1.5 4B.")
    if record["response_mode"]!="choice_classification" or record["panel_strategy"]!="volumetric_blocks": raise PipelineError("Freeze v9 exige choice_classification e volumetric_blocks.")
    if int(record["timeout_seconds"])>120 or int(record["max_retries"])!=0 or int(record["response_validation_max_retries"])!=0: raise PipelineError("Config v9 excede timeout ou permite retry.")
    if record["rag_enabled"] is not False: raise PipelineError("Calibracao v9 nao permite RAG.")
    return record
def create_multisequence_freeze(*,panel_root:Path,review_path:Path,config_path:Path,output_path:Path,experiment_version:str,expected_case_count:int=88,max_case_seconds:float=180.0):
    if not 0<float(max_case_seconds)<=180: raise PipelineError("max_case_seconds deve estar em (0,180].")
    review=verify_multisequence_review(panel_root=panel_root,review_path=review_path,expected_case_count=expected_case_count); version=str(experiment_version).strip()
    if not version or len(version)>120: raise PipelineError("experiment_version v9 invalida.")
    payload={"schema":SCHEMA,"experiment_version":version,"review_signature":review["review_signature"],"source_cohort_signature":review["source_cohort_signature"],"case_count":review["case_count"],"panel_count":review["panel_count"],"config":_config(config_path),"pair_bank":list(PAIR_BANK),"pair_bank_sha256":_canonical(PAIR_BANK),"aggregation_rule":"scores_only_no_decision; evaluation_after_inference","max_case_seconds":float(max_case_seconds),"research_only":True,"clinical_use_allowed":False,"ground_truth_read":False,"lesion_mask_used":False,"inference_executed":False}
    payload["experiment_signature"]=_signature(payload); payload["created_at_utc"]=datetime.now(timezone.utc).isoformat(); out=Path(output_path).resolve()
    if out.exists(): raise PipelineError("Freeze v9 ja existe e nao sera sobrescrito.")
    out.parent.mkdir(parents=True,exist_ok=True); tmp=out.with_name(f".{out.name}.{uuid.uuid4().hex}.tmp")
    try: tmp.write_text(json.dumps(payload,ensure_ascii=False,indent=2,sort_keys=True)+"\n",encoding="utf-8"); os.replace(tmp,out)
    finally: tmp.unlink(missing_ok=True)
    return payload
def verify_multisequence_freeze(*,panel_root:Path,review_path:Path,config_path:Path,freeze_path:Path,expected_case_count:int=88):
    freeze=_load(freeze_path)
    if set(freeze)!=set(SIGNED)|{"experiment_signature","created_at_utc"} or freeze.get("schema")!=SCHEMA or freeze.get("experiment_signature")!=_signature(freeze): raise PipelineError("Campos ou assinatura do freeze v9 invalidos.")
    review=verify_multisequence_review(panel_root=panel_root,review_path=review_path,expected_case_count=expected_case_count)
    if freeze["review_signature"]!=review["review_signature"] or freeze["source_cohort_signature"]!=review["source_cohort_signature"] or freeze["case_count"]!=review["case_count"] or freeze["panel_count"]!=review["panel_count"] or freeze["config"]!=_config(config_path): raise PipelineError("Freeze v9 divergiu da revisao, coorte ou config.")
    return freeze
