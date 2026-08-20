"""Blind technical-quality decisions for the OpenSwissHCC multisequence v9 cohort."""
from __future__ import annotations

import hashlib
import json
import os
import uuid
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dtwin.benchmark.openswisshcc_multisequence_gate import (
 validate_multisequence_cohort,
)
from dtwin.core import PipelineError

SCHEMA="argos-openswisshcc-multisequence-quality-review-v1"
STATUSES={"approved_primary","technical_quality_exclusion"}
REASONS={"severe_multisequence_quality_degradation","severe_motion_artifact","insufficient_liver_visibility","corrupted_images","visible_phi"}
SIGNED=("schema","review_status","reviewer","reviewed_at_utc","source_cohort_signature","source_case_count","approved_case_count","excluded_case_count","decisions","research_only","clinical_use_allowed","ground_truth_read","lesion_mask_used","inference_executed")

def _canonical(v:Any)->str:return hashlib.sha256(json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(",",":")).encode()).hexdigest()
def _signature(v):return _canonical({k:v.get(k) for k in SIGNED})
def _load(p):
 try:v=json.loads(Path(p).read_text(encoding="utf-8"))
 except (OSError,json.JSONDecodeError) as exc:raise PipelineError(f"Revisao de qualidade v9 invalida: {p}") from exc
 if not isinstance(v,dict):raise PipelineError("Revisao de qualidade v9 deve ser objeto.")
 return v
def _records(panel_root,expected_case_count):
 validated=validate_multisequence_cohort(panel_root,expected_case_count)
 return validated,{r["case_id"]:r for r in validated["records"]}
def create_quality_review(*,panel_root:Path,output_path:Path,reviewer:str,decisions:Mapping[str,Mapping[str,Any]],expected_case_count:int=88):
 reviewer=str(reviewer).strip()
 if not reviewer or len(reviewer)>120:raise PipelineError("Revisor de qualidade obrigatorio.")
 validated,current=_records(panel_root,expected_case_count)
 if set(decisions)!=set(current):raise PipelineError("Decisoes de qualidade nao cobrem exatamente a coorte.")
 rows=[]
 for case_id in sorted(current):
  decision=decisions[case_id]
  if set(decision)!={"status","reason_code"}:raise PipelineError("Decisao tecnica contem campos nao autorizados.")
  status=decision["status"];reason=decision["reason_code"]
  if status not in STATUSES:raise PipelineError("Status tecnico invalido.")
  if status=="approved_primary" and reason is not None:raise PipelineError("Caso aprovado nao pode ter motivo de exclusao.")
  if status=="technical_quality_exclusion" and reason not in REASONS:raise PipelineError("Exclusao tecnica exige reason_code autorizado.")
  source=current[case_id]
  rows.append({"case_id":case_id,"status":status,"reason_code":reason,"manifest_sha256":source["manifest_sha256"],"panel_set_sha256":source["panel_set_sha256"],"panel_count":source["panel_count"],"unavailable_tile_count":len(source["unavailable_tiles"])})
 approved=sum(r["status"]=="approved_primary" for r in rows);excluded=len(rows)-approved
 if approved<1:raise PipelineError("Revisao tecnica excluiu toda a coorte.")
 payload={"schema":SCHEMA,"review_status":"blind_technical_quality_complete","reviewer":reviewer,"reviewed_at_utc":datetime.now(timezone.utc).isoformat(),"source_cohort_signature":validated["cohort"]["cohort_signature"],"source_case_count":len(rows),"approved_case_count":approved,"excluded_case_count":excluded,"decisions":rows,"research_only":True,"clinical_use_allowed":False,"ground_truth_read":False,"lesion_mask_used":False,"inference_executed":False}
 payload["quality_review_signature"]=_signature(payload);out=Path(output_path).resolve()
 if out.exists():raise PipelineError("Revisao de qualidade ja existe.")
 out.parent.mkdir(parents=True,exist_ok=True);tmp=out.with_name(f".{out.name}.{uuid.uuid4().hex}.tmp")
 try:tmp.write_text(json.dumps(payload,ensure_ascii=False,indent=2,sort_keys=True)+"\n",encoding="utf-8");os.replace(tmp,out)
 finally:tmp.unlink(missing_ok=True)
 return payload
def verify_quality_review(*,panel_root:Path,review_path:Path,expected_case_count:int=88):
 review=_load(review_path)
 if set(review)!=set(SIGNED)|{"quality_review_signature"} or review.get("schema")!=SCHEMA or review.get("review_status")!="blind_technical_quality_complete" or review.get("quality_review_signature")!=_signature(review):raise PipelineError("Campos ou assinatura da revisao tecnica invalidos.")
 if review.get("ground_truth_read") is not False or review.get("lesion_mask_used") is not False or review.get("inference_executed") is not False:raise PipelineError("Revisao tecnica violou cegamento.")
 validated,current=_records(panel_root,expected_case_count);rows=review.get("decisions")
 if not isinstance(rows,list) or len(rows)!=expected_case_count:raise PipelineError("Decisoes tecnicas incompletas.")
 expected=[]
 for row in rows:
  case_id=row.get("case_id");source=current.get(case_id)
  if source is None:raise PipelineError("Caso tecnico desconhecido.")
  expected.append({"case_id":case_id,"status":row.get("status"),"reason_code":row.get("reason_code"),"manifest_sha256":source["manifest_sha256"],"panel_set_sha256":source["panel_set_sha256"],"panel_count":source["panel_count"],"unavailable_tile_count":len(source["unavailable_tiles"])})
 if rows!=expected or review["source_cohort_signature"]!=validated["cohort"]["cohort_signature"]:raise PipelineError("Coorte ou paineis mudaram apos revisao tecnica.")
 if review["approved_case_count"]!=sum(r["status"]=="approved_primary" for r in rows) or review["excluded_case_count"]!=sum(r["status"]=="technical_quality_exclusion" for r in rows):raise PipelineError("Contagens da revisao tecnica divergem.")
 return review
