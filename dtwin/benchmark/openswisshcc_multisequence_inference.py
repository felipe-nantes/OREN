"""Blind, scores-only MedGemma pairwise runner for reviewed multisequence v9 panels."""
from __future__ import annotations

import hashlib
import json
import shutil
import statistics
import time
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol

from dtwin.benchmark.openswisshcc_alignment import _publish_directory, _sha256
from dtwin.benchmark.openswisshcc_multisequence_freeze import (
    PAIR_BANK,
    verify_multisequence_freeze,
)
from dtwin.benchmark.openswisshcc_multisequence_gate import verify_multisequence_review
from dtwin.core import PipelineError
from dtwin.medgemma_screening import _write_json_atomic

SCORE_SCHEMA="argos-medgemma-volumetric-pairwise-panel-scores-v1"
CASE_SCHEMA="argos-openswisshcc-multisequence-pairwise-case-v1"
RUN_SCHEMA="argos-openswisshcc-multisequence-pairwise-run-v1"

class Scorer(Protocol):
    model_id:str
    model_version:str
    def score_panel(self,panel_path:Path,prompt:str,pairs:tuple[dict[str,str],...])->dict[str,Any]:...

def _load(path):
    try: value=json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError,json.JSONDecodeError) as exc: raise PipelineError(f"JSON de inferencia v9 invalido: {path}") from exc
    if not isinstance(value,dict): raise PipelineError("JSON de inferencia v9 deve ser objeto.")
    return value
def _prompt(panel,manifest):
    unavailable=[t["role"] for t in panel.get("tiles",[]) if t.get("available_in_fov") is False]
    return ("Research-only liver MRI assessment. This 2x2 panel shows the same ordered TRACE plane using "
            "T1 venous, native T2, the final ordered DWI TRACE run, and native ADC. The cyan contour marks "
            "the liver on T1 only and is not a lesion annotation. Do not treat a vessel, benign variant, "
            "artifact, partial volume, or an OUT OF FOV tile as a focal mass. Use only visible evidence; "
            "do not emit a diagnosis, recommendation, or final case decision. "
            f"Partial plane {panel['panel_number']}/{panel['panel_total']}; TRACE index {panel['trace_plane_index']}; "
            f"unavailable modalities: {unavailable or 'none'}. Score the authorized pairs independently.")
def _verify_score(score,panel_hash):
    if score.get("schema")!=SCORE_SCHEMA or score.get("panel_sha256")!=panel_hash or score.get("final_decision") is not None or score.get("ground_truth_read") is not False: raise PipelineError("Score v9 violou schema, hash ou cegamento.")
    pairs=score.get("pairs")
    if not isinstance(pairs,list) or len(pairs)!=len(PAIR_BANK): raise PipelineError("Score v9 nao contem todos os pares.")
    for expected,observed in zip(PAIR_BANK,pairs,strict=True):
        p=observed.get("positive_probability")
        if observed.get("pair_id")!=expected["pair_id"] or not isinstance(p,(int,float)) or not 0<=float(p)<=1: raise PipelineError("Probabilidade v9 invalida.")

def run_multisequence_scores(*,panel_root:Path,review_path:Path,freeze_path:Path,config_path:Path,output_root:Path,scorer:Scorer,expected_case_count:int=88,case_ids:list[str]|None=None,progress:Callable[[dict[str,Any]],None]|None=None):
    freeze=verify_multisequence_freeze(panel_root=panel_root,review_path=review_path,config_path=config_path,freeze_path=freeze_path,expected_case_count=expected_case_count)
    review=verify_multisequence_review(panel_root=panel_root,review_path=review_path,expected_case_count=expected_case_count)
    available=[r["case_id"] for r in review["cases"]]; selected=available if case_ids is None else list(case_ids)
    if not selected or len(selected)!=len(set(selected)) or any(c not in available for c in selected): raise PipelineError("Selecao de casos v9 invalida.")
    root=Path(panel_root).resolve(); out=Path(output_root).resolve()
    if out.exists(): raise PipelineError("Destino de inferencia v9 ja existe; nao sera sobrescrito.")
    out.parent.mkdir(parents=True,exist_ok=True); staging_run=out.parent/f"._v9run_{uuid.uuid4().hex[:8]}"; staging_run.mkdir()
    run_started=time.monotonic(); manifests=[]
    try:
        for sequence,case_id in enumerate(selected,1):
            case_started=time.monotonic(); case_dir=(root/case_id).resolve(); manifest=_load(case_dir/"multisequence_manifest.json")
            panels=manifest.get("panels",[]); staging=staging_run/case_id; staging.mkdir(); results=[]
            for panel in panels:
                if time.monotonic()-case_started>=float(freeze["max_case_seconds"]): raise PipelineError(f"Tempo v9 excedeu {freeze['max_case_seconds']}s em {case_id}.")
                path=(case_dir/str(panel.get("image",""))).resolve()
                if not path.is_relative_to(case_dir) or not path.is_file() or _sha256(path)!=panel.get("sha256"): raise PipelineError("Painel v9 mudou antes da inferencia.")
                started=time.monotonic(); prompt=_prompt(panel,manifest); score=scorer.score_panel(path,prompt,PAIR_BANK); _verify_score(score,panel["sha256"])
                elapsed=time.monotonic()-case_started
                if elapsed>float(freeze["max_case_seconds"]): raise PipelineError(f"Tempo v9 excedeu {freeze['max_case_seconds']}s em {case_id}.")
                results.append({"panel_number":panel["panel_number"],"panel_total":panel["panel_total"],"trace_plane_index":panel["trace_plane_index"],"sha256":panel["sha256"],"prompt_sha256":hashlib.sha256(prompt.encode()).hexdigest(),"elapsed_seconds":round(time.monotonic()-started,4),"score":score})
                _write_json_atomic(staging/"pairwise_panel_scores.json",results)
            scores=staging/"pairwise_panel_scores.json"; elapsed=time.monotonic()-case_started
            case_manifest={"schema":CASE_SCHEMA,"case_id":case_id,"status":"scores_only_no_decision","panel_count":len(results),"scores_sha256":_sha256(scores),"experiment_signature":freeze["experiment_signature"],"review_signature":review["review_signature"],"model_id":scorer.model_id,"model_version":scorer.model_version,"elapsed_seconds":round(elapsed,4),"within_180_seconds":elapsed<=float(freeze["max_case_seconds"]),"final_decision":None,"ground_truth_read":False,"metrics_calculated":False,"research_only":True,"clinical_use_allowed":False,"requires_human_review":True}
            _write_json_atomic(staging/"pairwise_manifest.json",case_manifest); manifests.append(case_manifest)
            if progress: progress({"sequence":sequence,"case_count":len(selected),"case_id":case_id,"elapsed_seconds":case_manifest["elapsed_seconds"]})
        elapsed=[m["elapsed_seconds"] for m in manifests]
        summary={"schema":RUN_SCHEMA,"status":"complete","case_count":len(manifests),"panel_count":sum(m["panel_count"] for m in manifests),"experiment_signature":freeze["experiment_signature"],"review_signature":review["review_signature"],"model_id":scorer.model_id,"model_version":scorer.model_version,"mean_case_seconds":statistics.fmean(elapsed),"max_case_seconds":max(elapsed),"all_cases_within_180_seconds":all(m["within_180_seconds"] for m in manifests),"total_wall_seconds":round(time.monotonic()-run_started,4),"final_decision":None,"ground_truth_read":False,"metrics_calculated":False,"research_only":True,"clinical_use_allowed":False}
        _write_json_atomic(staging_run/"summary.json",summary); _publish_directory(staging_run,out); return summary
    except Exception:
        shutil.rmtree(staging_run,ignore_errors=True); raise
