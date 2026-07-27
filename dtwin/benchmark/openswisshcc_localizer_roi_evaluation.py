"""Post-inference development evaluation for frozen v10 localizer ROI scores."""
from __future__ import annotations

import csv
import json
import math
import statistics
from pathlib import Path
from typing import Any

from dtwin.benchmark.openswisshcc_alignment import _sha256
from dtwin.benchmark.openswisshcc_localizer_roi_freeze import QUESTION_BANK, verify_roi_freeze
from dtwin.benchmark.openswisshcc_localizer_roi_gate import verify_paired_review
from dtwin.benchmark.openswisshcc_localizer_roi_inference import CASE_SCHEMA, RUN_SCHEMA, SCORE_SCHEMA
from dtwin.benchmark.openswisshcc_volumetric_evaluation import _best_threshold, _loocv, _repeated_stratified_cv
from dtwin.core import PipelineError

EVALUATION_SCHEMA = "argos-openswisshcc-localizer-roi-evaluation-v1"


def _load(path: Path) -> Any:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PipelineError(f"JSON da avaliacao ROI v10 invalido: {path}") from exc


def _top(values: list[float], count: int) -> float:
    return statistics.fmean(sorted(values, reverse=True)[: min(count, len(values))])


def _wilson(success: int, total: int, z: float = 1.959963984540054) -> list[float]:
    if total <= 0:
        return [0.0, 0.0]
    p = success / total
    denominator = 1 + z * z / total
    center = (p + z * z / (2 * total)) / denominator
    half = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / denominator
    return [max(0.0, center - half), min(1.0, center + half)]


def _validate_score(score: dict[str, Any], expected_question: dict[str, Any]) -> tuple[float, float]:
    if score.get("schema") != SCORE_SCHEMA or score.get("question_id") != expected_question["question_id"] or score.get("representation") != expected_question["representation"] or score.get("final_decision") is not None or score.get("ground_truth_read") is not False:
        raise PipelineError("Score ROI v10 invalido antes do ground truth.")
    mappings = score.get("mappings")
    if not isinstance(mappings, list) or len(mappings) != 2 or [row.get("mapping_id") for row in mappings] != ["ab", "ba"]:
        raise PipelineError("Mapeamentos ROI v10 incompletos ou fora de ordem.")
    semantic = []
    for row in mappings:
        a, b = row.get("A_probability"), row.get("B_probability")
        if not isinstance(a, (int, float)) or not isinstance(b, (int, float)) or not 0 <= float(a) <= 1 or not 0 <= float(b) <= 1 or abs(float(a) + float(b) - 1) > 1e-5 or row.get("selected_token") not in {"A", "B"}:
            raise PipelineError("Probabilidades persistidas ROI v10 invalidas.")
        positive_token = row.get("positive_token")
        if positive_token not in {"A", "B"}:
            raise PipelineError("Token positivo ROI v10 invalido.")
        semantic.append(float(a) if positive_token == "A" else float(b))
    probability = score.get("semantic_positive_probability")
    if not isinstance(probability, (int, float)) or abs(float(probability) - statistics.fmean(semantic)) > 1e-9:
        raise PipelineError("Media semantica ROI v10 divergiu dos mapeamentos.")
    return float(probability), abs(semantic[0] - semantic[1])


def _case_features(case_dir: Path, summary: dict[str, Any], localizer_run: Path, question_by_id: dict[str, dict[str, Any]]) -> dict[str, float]:
    manifest = _load(case_dir / "mirrored_ab_manifest.json")
    scores_path = case_dir / "mirrored_ab_scores.json"
    if manifest.get("schema") != CASE_SCHEMA or manifest.get("case_id") != case_dir.name or manifest.get("status") != "scores_only_no_decision" or manifest.get("experiment_signature") != summary["experiment_signature"] or manifest.get("review_signature") != summary["review_signature"] or manifest.get("scores_sha256") != _sha256(scores_path) or manifest.get("final_decision") is not None or manifest.get("ground_truth_read") is not False or manifest.get("metrics_calculated") is not False or manifest.get("within_scoring_budget") is not True:
        raise PipelineError(f"Caso ROI v10 cego invalido: {case_dir.name}.")
    rows = _load(scores_path)
    if not isinstance(rows, list) or len(rows) != manifest.get("panel_pairs"):
        raise PipelineError("Scores ROI v10 nao cobrem os paineis do caso.")
    by_question = {question["question_id"]: [] for question in QUESTION_BANK}
    panel_vectors = []
    mapping_biases = []
    for number, row in enumerate(rows, 1):
        if row.get("panel_number") != number or row.get("panel_total") != len(rows):
            raise PipelineError("Ordem de paineis ROI v10 invalida.")
        questions = row.get("questions")
        if not isinstance(questions, list) or len(questions) != len(QUESTION_BANK):
            raise PipelineError("Perguntas ROI v10 incompletas.")
        observed = {}
        for item in questions:
            score = item.get("score", {})
            question_id = score.get("question_id")
            expected = question_by_id.get(question_id)
            if expected is None or question_id in observed:
                raise PipelineError("Pergunta ROI v10 desconhecida ou duplicada.")
            probability, bias = _validate_score(score, expected)
            observed[question_id] = probability
            by_question[question_id].append(probability)
            mapping_biases.append(bias)
        if set(observed) != set(question_by_id):
            raise PipelineError("Painel ROI v10 nao contem o banco de perguntas completo.")
        panel_vectors.append(observed)
    localizer_path = Path(localizer_run).resolve() / case_dir.name / "localizer_manifest.json"
    localizer = _load(localizer_path)
    if _sha256(localizer_path) != manifest.get("localizer_manifest_sha256") or localizer.get("ground_truth_read") is not False or localizer.get("ground_truth_lesion_mask_used") is not False or localizer.get("final_decision") is not None:
        raise PipelineError("Localizador ROI v10 mudou ou perdeu o cegamento.")
    local_features = localizer.get("features", {})
    candidate_present = 1.0 if local_features.get("candidate_present") is True else 0.0
    features: dict[str, float] = {
        "candidate_present": candidate_present,
        "candidate_component_count": float(local_features.get("component_count", 0)),
        "candidate_total_volume_log1p": math.log1p(float(local_features.get("total_candidate_volume_mm3", 0))),
        "candidate_largest_volume_log1p": math.log1p(float(local_features.get("largest_component_volume_mm3", 0))),
        "mapping_bias_mean": statistics.fmean(mapping_biases),
        "mapping_bias_max": max(mapping_biases),
    }
    for question_id, values in by_question.items():
        features[f"{question_id}_mean"] = statistics.fmean(values)
        features[f"{question_id}_max"] = max(values)
        features[f"{question_id}_top2_mean"] = _top(values, 2)
        features[f"{question_id}_max_x_candidate"] = max(values) * candidate_present
    panel_all = []
    panel_mass = []
    panel_support = []
    panel_conservative = []
    for vector in panel_vectors:
        mass = statistics.fmean([vector["morphology_mass_vs_mimic"], vector["dynamic_mass_vs_vessel"]])
        support = statistics.fmean([vector["morphology_cross_sequence"], vector["dynamic_enhancement_support"]])
        all_mean = statistics.fmean(vector.values())
        panel_all.append(all_mean)
        panel_mass.append(mass)
        panel_support.append(support)
        panel_conservative.append(min(mass, support))
    for name, values in {"panel_all": panel_all, "panel_mass": panel_mass, "panel_support": panel_support, "panel_conservative": panel_conservative}.items():
        features[f"{name}_mean"] = statistics.fmean(values)
        features[f"{name}_max"] = max(values)
        features[f"{name}_top2_mean"] = _top(values, 2)
        features[f"{name}_max_x_candidate"] = max(values) * candidate_present
    return features


def _validate_blind_run(*, scores_root: Path, freeze: dict[str, Any], review: dict[str, Any], localizer_run: Path, expected_case_count: int) -> tuple[dict[str, Any], dict[str, dict[str, float]]]:
    root = Path(scores_root).resolve()
    summary = _load(root / "summary.json")
    if summary.get("schema") != RUN_SCHEMA or summary.get("status") != "complete_scores_only_no_decision" or summary.get("case_count") != expected_case_count or summary.get("experiment_signature") != freeze["experiment_signature"] or summary.get("review_signature") != review["review_signature"] or summary.get("final_decision") is not None or summary.get("ground_truth_read") is not False or summary.get("metrics_calculated") is not False or summary.get("all_cases_within_scoring_budget") is not True or summary.get("end_to_end_time_gate_evaluable") is not False:
        raise PipelineError("Lote ROI v10 nao esta completo, cego ou dentro do budget de scoring.")
    directories = sorted(path for path in root.iterdir() if path.is_dir() and not path.name.startswith("."))
    expected_ids = sorted(case["case_id"] for case in review["cases"])
    if [path.name for path in directories] != expected_ids:
        raise PipelineError("Diretorios ROI v10 nao cobrem exatamente a coorte revisada.")
    question_by_id = {question["question_id"]: question for question in freeze["question_bank"]}
    if question_by_id != {question["question_id"]: question for question in QUESTION_BANK}:
        raise PipelineError("Banco de perguntas ROI v10 mudou antes da avaliacao.")
    features = {path.name: _case_features(path, summary, Path(localizer_run), question_by_id) for path in directories}
    return summary, features


def _load_selected_labels(path: Path, expected_ids: list[str], expected_positive: int, expected_negative: int) -> tuple[dict[str, dict[str, Any]], str]:
    path = Path(path).resolve()
    try:
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    except (OSError, json.JSONDecodeError) as exc:
        raise PipelineError("Ground truth protegido ROI v10 invalido.") from exc
    required = {"schema", "case_id", "public_subject_id", "label", "target_condition", "label_basis", "review_status"}
    by_id = {}
    for row in rows:
        if set(row) != required or row.get("schema") != "argos-openswisshcc-ground-truth-v1" or row.get("label") not in {"POSITIVE", "NEGATIVE"} or row.get("target_condition") != "hcc_presence":
            raise PipelineError("Registro protegido ROI v10 incompativel.")
        case_id = str(row.get("case_id", ""))
        if not case_id.startswith("anon-") or case_id in by_id:
            raise PipelineError("Ground truth ROI v10 possui ID invalido ou duplicado.")
        by_id[case_id] = row
    if any(case_id not in by_id for case_id in expected_ids):
        raise PipelineError("Ground truth nao cobre o piloto ROI v10.")
    selected = {case_id: by_id[case_id] for case_id in expected_ids}
    positive = sum(row["label"] == "POSITIVE" for row in selected.values())
    negative = len(selected) - positive
    if (positive, negative) != (expected_positive, expected_negative):
        raise PipelineError("Contagens protegidas do piloto ROI v10 divergiram.")
    return selected, _sha256(path)


def evaluate_roi_pilot(*, morphology_root: Path, enhancement_root: Path, review_path: Path, freeze_path: Path, config_path: Path, localizer_run: Path, scores_root: Path, labels_path: Path, output_dir: Path, expected_case_count: int = 10, expected_positive: int = 4, expected_negative: int = 6) -> dict[str, Any]:
    output = Path(output_dir).resolve()
    if output.exists():
        raise PipelineError("Avaliacao ROI v10 ja existe.")
    freeze = verify_roi_freeze(morphology_root=morphology_root, enhancement_root=enhancement_root, review_path=review_path, config_path=config_path, freeze_path=freeze_path, expected_case_count=expected_case_count)
    review = verify_paired_review(morphology_root=morphology_root, enhancement_root=enhancement_root, review_path=review_path, expected_case_count=expected_case_count)
    summary, features = _validate_blind_run(scores_root=scores_root, freeze=freeze, review=review, localizer_run=localizer_run, expected_case_count=expected_case_count)
    case_ids = sorted(features)
    labels, labels_hash = _load_selected_labels(labels_path, case_ids, expected_positive, expected_negative)
    truth = [labels[case_id]["label"] == "POSITIVE" for case_id in case_ids]
    analyses = []
    for feature in sorted(next(iter(features.values()))):
        values = [features[case_id][feature] for case_id in case_ids]
        threshold, apparent = _best_threshold(values, truth)
        loocv = _loocv(values, truth)
        repeated = _repeated_stratified_cv(values, truth, repeats=50, folds=5)
        analyses.append({"feature": feature, "direction": "higher_is_positive", "apparent_threshold": threshold, "apparent": apparent, "loocv": loocv, "repeated_stratified_5fold": repeated})
    analyses.sort(key=lambda row: (row["loocv"]["minimum_gate_metric"], row["loocv"]["balanced_accuracy"], row["repeated_stratified_5fold"]["runs_passing_75_75"]), reverse=True)
    primary = analyses[0]
    loocv = primary["loocv"]
    result = {
        "schema": EVALUATION_SCHEMA,
        "status": "pilot_exploration_not_qualified",
        "case_count": expected_case_count,
        "positive_count": expected_positive,
        "negative_count": expected_negative,
        "protected_ground_truth_sha256": labels_hash,
        "scores_summary_sha256": _sha256(Path(scores_root).resolve() / "summary.json"),
        "experiment_signature": freeze["experiment_signature"],
        "review_signature": review["review_signature"],
        "primary_feature": primary["feature"],
        "primary_loocv_confidence_intervals": {"sensitivity_95": _wilson(loocv["tp"], loocv["tp"] + loocv["fn"]), "specificity_95": _wilson(loocv["tn"], loocv["tn"] + loocv["fp"])},
        "analyses": analyses,
        "observed_mean_localizer_plus_scoring_seconds": summary["mean_observed_localizer_plus_scoring_seconds"],
        "observed_max_localizer_plus_scoring_seconds": summary["max_observed_localizer_plus_scoring_seconds"],
        "observed_partial_time_within_180_seconds": summary["all_cases_within_observed_180_seconds"],
        "end_to_end_time_gate_evaluable": False,
        "unmeasured_stages": summary["unmeasured_stages"],
        "thresholds_selected_using_development_labels": True,
        "pilot_too_small_for_qualification": True,
        "holdout_opened": False,
        "qualified": False,
        "research_only": True,
        "clinical_use_allowed": False,
        "requires_human_review": True,
    }
    output.mkdir(parents=True)
    (output / "evaluation.json").write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    with (output / "case_features.csv").open("w", encoding="utf-8", newline="") as handle:
        fields = ["case_id", "label", *sorted(next(iter(features.values())))]
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for case_id in case_ids:
            writer.writerow({"case_id": case_id, "label": labels[case_id]["label"], **features[case_id]})
    return result
