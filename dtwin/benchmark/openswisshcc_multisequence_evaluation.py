"""Post-inference development evaluation for blind multisequence v9 pairwise scores."""
from __future__ import annotations
import csv,json,math,statistics
from pathlib import Path
from dtwin.benchmark.openswisshcc_alignment import _sha256
from dtwin.benchmark.openswisshcc_evaluation import _load_labels_after_inference
from dtwin.benchmark.openswisshcc_multisequence_freeze import PAIR_BANK
from dtwin.benchmark.openswisshcc_multisequence_inference import CASE_SCHEMA,RUN_SCHEMA
from dtwin.benchmark.openswisshcc_multisequence_quality import REASONS as QUALITY_REASONS,SCHEMA as QUALITY_SCHEMA,SIGNED as QUALITY_SIGNED,_signature as quality_signature
from dtwin.benchmark.openswisshcc_volumetric_evaluation import _best_threshold,_loocv,_repeated_stratified_cv
from dtwin.benchmark.openswisshcc_volumetric_fusion import _nested_repeated_cv
from dtwin.core import PipelineError

def _load(path):
    try:v=json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError,json.JSONDecodeError) as exc: raise PipelineError(f"JSON v9 invalido: {path}") from exc
    return v
def _rolling(v,w):
    return statistics.fmean(v) if len(v)<w else max(statistics.fmean(v[i:i+w]) for i in range(len(v)-w+1))
def _features(case_dir,summary):
    m=_load(case_dir/"pairwise_manifest.json"); sp=case_dir/"pairwise_panel_scores.json"
    if m.get("schema")!=CASE_SCHEMA or m.get("status")!="scores_only_no_decision" or m.get("experiment_signature")!=summary["experiment_signature"] or m.get("scores_sha256")!=_sha256(sp) or m.get("final_decision") is not None or m.get("ground_truth_read") is not False or m.get("metrics_calculated") is not False or m.get("within_180_seconds") is not True: raise PipelineError(f"Caso v9 cego invalido: {case_dir.name}.")
    rows=_load(sp)
    if not isinstance(rows,list) or len(rows)!=m.get("panel_count"): raise PipelineError(f"Scores v9 incompletos: {case_dir.name}.")
    by={p["pair_id"]:[] for p in PAIR_BANK}; means=[]
    for n,row in enumerate(rows,1):
        if row.get("panel_number")!=n: raise PipelineError(f"Ordem v9 invalida: {case_dir.name}.")
        score=row.get("score",{}); pairs=score.get("pairs")
        if not isinstance(pairs,list) or len(pairs)!=len(PAIR_BANK) or score.get("final_decision") is not None or score.get("ground_truth_read") is not False: raise PipelineError(f"Score v9 invalido: {case_dir.name}.")
        vals=[]
        for exp,obs in zip(PAIR_BANK,pairs,strict=True):
            x=obs.get("positive_probability")
            if obs.get("pair_id")!=exp["pair_id"] or not isinstance(x,(int,float)) or not 0<=float(x)<=1: raise PipelineError(f"Par v9 invalido: {case_dir.name}.")
            by[exp["pair_id"]].append(float(x)); vals.append(float(x))
        means.append(statistics.fmean(vals))
    ordered=sorted(means,reverse=True)
    f={"v9_panel_mean":statistics.fmean(means),"v9_panel_median":statistics.median(means),"v9_panel_max":max(means),"v9_panel_top2_mean":statistics.fmean(ordered[:min(2,len(ordered))]),"v9_panel_top3_mean":statistics.fmean(ordered[:min(3,len(ordered))]),"v9_panel_focality":max(means)-statistics.median(means),"v9_adjacent2_max_mean":_rolling(means,2),"v9_adjacent3_max_mean":_rolling(means,3),"v9_fraction_over_050":sum(x>=.5 for x in means)/len(means)}
    for key,vals in by.items():
        order=sorted(vals,reverse=True); f[f"v9_{key}_mean"]=statistics.fmean(vals); f[f"v9_{key}_max"]=max(vals); f[f"v9_{key}_top2_mean"]=statistics.fmean(order[:min(2,len(order))])
    return f
def _wilson(success,total,z=1.959963984540054):
    if total<=0:return [0.0,0.0]
    p=success/total; d=1+z*z/total; center=(p+z*z/(2*total))/d; half=z*math.sqrt(p*(1-p)/total+z*z/(4*total*total))/d
    return [max(0.0,center-half),min(1.0,center+half)]
def _derive_class_counts(labels_path):
    """Read counts only after blind artifacts pass; the protected loader validates next."""
    try:rows=[json.loads(line) for line in Path(labels_path).read_text(encoding="utf-8").splitlines() if line.strip()]
    except (OSError,json.JSONDecodeError) as exc:raise PipelineError(f"Ground truth protegido invalido: {exc}") from exc
    return sum(row.get("label")=="POSITIVE" for row in rows),sum(row.get("label")=="NEGATIVE" for row in rows)
def _load_quality_review(path,inferred_ids):
    review=_load(path)
    if set(review)!=set(QUALITY_SIGNED)|{"quality_review_signature"} or review.get("schema")!=QUALITY_SCHEMA or review.get("quality_review_signature")!=quality_signature(review):raise PipelineError("Revisao tecnica assinada invalida.")
    if review.get("review_status")!="blind_technical_quality_complete" or review.get("ground_truth_read") is not False or review.get("inference_executed") is not False or review.get("lesion_mask_used") is not False:raise PipelineError("Revisao tecnica perdeu o cegamento.")
    rows=review.get("decisions")
    if not isinstance(rows,list) or len(rows)!=review.get("source_case_count"):raise PipelineError("Decisoes da revisao tecnica incompletas.")
    ids=[];approved=[];excluded=[]
    for row in rows:
        if set(row)!={"case_id","status","reason_code","manifest_sha256","panel_set_sha256","panel_count","unavailable_tile_count"}:raise PipelineError("Decisao tecnica contem campos inesperados.")
        case_id=row.get("case_id");status=row.get("status");reason=row.get("reason_code")
        if not isinstance(case_id,str) or not case_id.startswith("anon-") or case_id in ids:raise PipelineError("Case ID tecnico invalido ou duplicado.")
        if status=="approved_primary" and reason is None:approved.append(case_id)
        elif status=="technical_quality_exclusion" and reason in QUALITY_REASONS:excluded.append({"case_id":case_id,"reason_code":reason})
        else:raise PipelineError("Status ou motivo tecnico invalido.")
        ids.append(case_id)
    if sorted(approved)!=sorted(inferred_ids) or review.get("approved_case_count")!=len(approved) or review.get("excluded_case_count")!=len(excluded):raise PipelineError("Revisao tecnica nao corresponde exatamente a coorte inferida.")
    return review,ids,excluded
def _load_labels_with_quality_exclusion(labels_path,all_quality_ids,inferred_ids):
    try:rows=[json.loads(line) for line in Path(labels_path).read_text(encoding="utf-8").splitlines() if line.strip()]
    except (OSError,json.JSONDecodeError) as exc:raise PipelineError(f"Ground truth protegido invalido: {exc}") from exc
    required={"schema","case_id","public_subject_id","label","target_condition","label_basis","review_status"};by={}
    for row in rows:
        if set(row)!=required or row.get("schema")!="argos-openswisshcc-ground-truth-v1" or row.get("label") not in {"POSITIVE","NEGATIVE"} or row.get("target_condition")!="hcc_presence":raise PipelineError("Registro protegido possui campos ou valores incompatíveis.")
        case_id=str(row.get("case_id",""))
        if not case_id.startswith("anon-") or case_id in by:raise PipelineError("Ground truth contem case_id invalido ou duplicado.")
        by[case_id]=row
    if sorted(by)!=sorted(all_quality_ids):raise PipelineError("Ground truth nao cobre exatamente a coorte revisada, incluindo exclusoes tecnicas.")
    return {case_id:by[case_id] for case_id in inferred_ids},_sha256(Path(labels_path).resolve())
def evaluate_multisequence_scores(*,scores_root:Path,labels_path:Path,output_dir:Path,expected_total:int|None=None,expected_positive:int|None=None,expected_negative:int|None=None,quality_review_path:Path|None=None):
    root=Path(scores_root).resolve();out=Path(output_dir).resolve()
    if out.exists():raise PipelineError("Avaliacao v9 ja existe.")
    if (expected_positive is None)!=(expected_negative is None):raise PipelineError("As contagens de classe devem ser fornecidas juntas ou omitidas.")
    if expected_total is None:
        if expected_positive is None:raise PipelineError("expected_total e obrigatorio quando as contagens de classe sao omitidas.")
        expected_total=expected_positive+expected_negative
    if expected_positive is not None and expected_positive+expected_negative!=expected_total:raise PipelineError("As contagens de classe nao totalizam a coorte esperada.")
    summary=_load(root/"summary.json")
    if summary.get("schema")!=RUN_SCHEMA or summary.get("status")!="complete" or summary.get("case_count")!=expected_total or summary.get("final_decision") is not None or summary.get("ground_truth_read") is not False or summary.get("metrics_calculated") is not False or summary.get("all_cases_within_180_seconds") is not True or float(summary.get("max_case_seconds",181))>180:raise PipelineError("Lote v9 nao esta completo, cego e dentro de 180s.")
    dirs=sorted(p for p in root.iterdir() if p.is_dir() and not p.name.startswith("."))
    if len(dirs)!=summary["case_count"]:raise PipelineError("Diretorios v9 nao cobrem a coorte.")
    features={d.name:_features(d,summary) for d in dirs};ids=sorted(features);quality_audit=None
    if quality_review_path is not None:
        review,all_quality_ids,excluded=_load_quality_review(quality_review_path,ids)
        labels,labels_hash=_load_labels_with_quality_exclusion(labels_path,all_quality_ids,ids)
        actual_positive=sum(labels[i]["label"]=="POSITIVE" for i in ids);actual_negative=len(ids)-actual_positive
        if expected_positive is not None and (actual_positive,actual_negative)!=(expected_positive,expected_negative):raise PipelineError("Contagens protegidas da coorte primaria divergem.")
        expected_positive,expected_negative=actual_positive,actual_negative
        quality_audit={"quality_review_signature":review["quality_review_signature"],"quality_review_sha256":_sha256(Path(quality_review_path).resolve()),"quality_reviewer":review["reviewer"],"excluded_cases":excluded}
    else:
        if expected_positive is None:expected_positive,expected_negative=_derive_class_counts(labels_path)
        labels,labels_hash=_load_labels_after_inference(labels_path,expected_ids=ids,expected_positive=expected_positive,expected_negative=expected_negative)
    truth=[labels[i]["label"]=="POSITIVE" for i in ids];matrix={name:[features[i][name] for i in ids] for name in sorted(next(iter(features.values())))}
    analyses=[]
    for name,values in matrix.items():
        threshold,apparent=_best_threshold(values,truth);analyses.append({"feature":name,"apparent_threshold":threshold,"apparent":apparent,"loocv":_loocv(values,truth),"repeated_5fold":_repeated_stratified_cv(values,truth)})
    analyses.sort(key=lambda x:(x["loocv"]["minimum_gate_metric"],x["loocv"]["balanced_accuracy"]),reverse=True);nested=_nested_repeated_cv(matrix,truth);primary=analyses[0]["loocv"]
    ci={"sensitivity_95":_wilson(primary["tp"],primary["tp"]+primary["fn"]),"specificity_95":_wilson(primary["tn"],primary["tn"]+primary["fp"])}
    qualified=bool(primary["passed_75_75"] and analyses[0]["repeated_5fold"]["runs_passing_75_75"]==50 and nested["runs_passing_75_75"]==50)
    result={"schema":"argos-openswisshcc-multisequence-pairwise-evaluation-v1","status":"qualified_development_candidate" if qualified else "development_only_not_qualified","case_count":len(ids),"positive_count":expected_positive,"negative_count":expected_negative,"protected_ground_truth_sha256":labels_hash,"scores_summary_sha256":_sha256(root/"summary.json"),"observed_mean_case_seconds":summary["mean_case_seconds"],"observed_max_case_seconds":summary["max_case_seconds"],"time_gate_180_seconds_passed":True,"primary_feature":analyses[0]["feature"],"primary_loocv_confidence_intervals":ci,"analyses":analyses,"nested_repeated_stratified_5fold":nested,"holdout_opened":False,"qualified":qualified,"research_only":True,"clinical_use_allowed":False,"requires_human_review":True}
    if quality_audit is not None:result["technical_quality_exclusion_audit"]=quality_audit
    out.mkdir(parents=True);(out/"evaluation.json").write_text(json.dumps(result,ensure_ascii=False,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    with (out/"case_features.csv").open("w",encoding="utf-8",newline="") as h:
        fields=["case_id","label",*sorted(next(iter(features.values())))];w=csv.DictWriter(h,fieldnames=fields);w.writeheader()
        for i in ids:w.writerow({"case_id":i,"label":labels[i]["label"],**features[i]})
    return result
