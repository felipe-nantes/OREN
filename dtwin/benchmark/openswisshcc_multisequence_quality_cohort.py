"""Atomic primary/stress cohort bundle derived from blind v9 quality decisions."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import uuid
from pathlib import Path
from typing import Any

from dtwin.benchmark.openswisshcc_alignment import _publish_directory
from dtwin.benchmark.openswisshcc_multisequence_batch import COHORT_SCHEMA
from dtwin.benchmark.openswisshcc_multisequence_gate import (
 validate_multisequence_cohort,
)
from dtwin.benchmark.openswisshcc_multisequence_quality import verify_quality_review
from dtwin.core import PipelineError

BUNDLE_SCHEMA="argos-openswisshcc-multisequence-quality-bundle-v1"
def _canonical(v:Any)->str:return hashlib.sha256(json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(",",":")).encode()).hexdigest()
def _load(p):return json.loads(Path(p).read_text(encoding="utf-8"))
def _link_tree(source:Path,destination:Path)->dict[str,int]:
 destination.mkdir(parents=True);hard=copy=0
 for item in source.iterdir():
  if not item.is_file():raise PipelineError("Caso v9 contem entrada nao autorizada.")
  target=destination/item.name
  try:os.link(item,target);hard+=1
  except OSError:shutil.copy2(item,target);copy+=1
 return {"hardlinks":hard,"copies":copy}
def _submanifest(source:dict,records:list[dict],quality:dict,subset:str)->dict:
 return {"schema":COHORT_SCHEMA,"case_count":len(records),"panel_count":sum(int(r["panel_count"]) for r in records),"max_panels_per_case":max(int(r["panel_count"]) for r in records),"cases":records,"cohort_signature":_canonical(records),"subset":subset,"source_cohort_signature":source["cohort_signature"],"quality_review_signature":quality["quality_review_signature"],"research_only":True,"clinical_use_allowed":False,"ground_truth_read":False,"lesion_mask_used":False,"inference_executed":False,"requires_human_review":True}
def build_quality_bundle(*,source_root:Path,quality_review_path:Path,output_root:Path,expected_source_count:int=88):
 source_root=Path(source_root).resolve();output_root=Path(output_root).resolve()
 if output_root.exists():raise PipelineError("Bundle de qualidade v9 ja existe.")
 quality=verify_quality_review(panel_root=source_root,review_path=quality_review_path,expected_case_count=expected_source_count)
 source=_load(source_root/"cohort_manifest.json");by_id={r["case_id"]:r for r in source["cases"]}
 approved=[r["case_id"] for r in quality["decisions"] if r["status"]=="approved_primary"];excluded=[r["case_id"] for r in quality["decisions"] if r["status"]=="technical_quality_exclusion"]
 if len(approved)!=quality["approved_case_count"] or len(excluded)!=quality["excluded_case_count"] or not excluded:raise PipelineError("Particao tecnica v9 inconsistente.")
 output_root.parent.mkdir(parents=True,exist_ok=True);staging=output_root.parent/f"._v9quality_{uuid.uuid4().hex[:8]}";staging.mkdir()
 try:
  modes={"hardlinks":0,"copies":0}
  for subset,ids in (("primary",approved),("stress",excluded)):
   root=staging/subset;root.mkdir()
   for case_id in ids:
    counts=_link_tree(source_root/case_id,root/case_id)
    for key in modes:modes[key]+=counts[key]
   records=[by_id[i] for i in ids];manifest=_submanifest(source,records,quality,subset)
   (root/"cohort_manifest.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2,sort_keys=True)+"\n",encoding="utf-8")
  primary=validate_multisequence_cohort(staging/"primary",len(approved))["cohort"];stress=validate_multisequence_cohort(staging/"stress",len(excluded))["cohort"]
  bundle={"schema":BUNDLE_SCHEMA,"source_cohort_signature":source["cohort_signature"],"quality_review_signature":quality["quality_review_signature"],"primary_case_count":len(approved),"stress_case_count":len(excluded),"primary_cohort_signature":primary["cohort_signature"],"stress_cohort_signature":stress["cohort_signature"],"file_materialization":modes,"research_only":True,"clinical_use_allowed":False,"ground_truth_read":False,"lesion_mask_used":False,"inference_executed":False}
  bundle["bundle_signature"]=_canonical(bundle);(staging/"bundle_manifest.json").write_text(json.dumps(bundle,ensure_ascii=False,indent=2,sort_keys=True)+"\n",encoding="utf-8")
  _publish_directory(staging,output_root);return bundle
 except Exception:
  shutil.rmtree(staging,ignore_errors=True);raise
