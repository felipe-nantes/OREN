"""Exploratory post-inference evaluation for high-resolution axial slice scores."""
from __future__ import annotations

import json
import statistics
from pathlib import Path
from typing import Any

from dtwin.benchmark.openswisshcc_alignment import _load_json, _sha256
from dtwin.benchmark.openswisshcc_slice_pairwise import CASE_SCHEMA, RUN_SCHEMA
from dtwin.benchmark.openswisshcc_volumetric_evaluation import (
    _best_threshold,
    _loocv,
    _repeated_stratified_cv,
)
from dtwin.core import PipelineError


def _rolling(values: list[float], width: int) -> float:
    if len(values) < width:
        return statistics.fmean(values)
    return max(statistics.fmean(values[i:i + width]) for i in range(len(values) - width + 1))


def _verify_case(case_dir: Path, summary: dict[str, Any]) -> dict[str, float]:
    manifest = _load_json(case_dir / "slice_manifest.json")
    scores_path = case_dir / "slice_scores.json"
    if (
        manifest.get("schema") != CASE_SCHEMA
        or manifest.get("status") != "scores_only_no_decision"
        or manifest.get("experiment_signature") != summary["experiment_signature"]
        or manifest.get("scores_sha256") != _sha256(scores_path)
        or manifest.get("final_decision") is not None
        or manifest.get("ground_truth_read") is not False
        or manifest.get("metrics_calculated") is not False
    ):
        raise PipelineError(f"Caso axial invalido: {case_dir.name}.")
    rows = json.loads(scores_path.read_text(encoding="utf-8"))
    if not isinstance(rows, list) or len(rows) != manifest.get("slice_count"):
        raise PipelineError(f"Scores axiais incompletos: {case_dir.name}.")
    indices = [row.get("axial_index") for row in rows]
    if any(not isinstance(value, int) for value in indices) or len(indices) != len(set(indices)):
        raise PipelineError(f"Indices axiais invalidos: {case_dir.name}.")
    values = []
    for row in rows:
        score = row.get("score")
        value = score.get("positive_probability") if isinstance(score, dict) else None
        if (
            not isinstance(value, (int, float)) or not 0 <= float(value) <= 1
            or score.get("final_decision") is not None
            or score.get("ground_truth_read") is not False
        ):
            raise PipelineError(f"Probabilidade axial invalida: {case_dir.name}.")
        values.append(float(value))
    ordered = sorted(values, reverse=True)
    return {
        "slice_mean": statistics.fmean(values),
        "slice_median": statistics.median(values),
        "slice_max": max(values),
        "slice_top2_mean": statistics.fmean(ordered[:2]),
        "slice_top5_mean": statistics.fmean(ordered[:5]),
        "slice_top10_mean": statistics.fmean(ordered[:10]),
        "slice_focality": max(values) - statistics.median(values),
        "slice_adjacent2_max_mean": _rolling(values, 2),
        "slice_adjacent3_max_mean": _rolling(values, 3),
        "slice_adjacent5_max_mean": _rolling(values, 5),
        "slice_fraction_over_030": sum(value >= 0.30 for value in values) / len(values),
        "slice_fraction_over_040": sum(value >= 0.40 for value in values) / len(values),
        "slice_fraction_over_050": sum(value >= 0.50 for value in values) / len(values),
    }


def _strict_labels(path: Path) -> tuple[dict[str, dict[str, Any]], str]:
    rows = [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line]
    required = {"schema", "case_id", "public_subject_id", "label", "target_condition", "label_basis", "review_status"}
    if (
        len(rows) != 88
        or any(set(row) != required for row in rows)
        or any(row.get("schema") != "argos-openswisshcc-ground-truth-v1" for row in rows)
        or any(row.get("label") not in {"POSITIVE", "NEGATIVE"} for row in rows)
        or any(row.get("target_condition") != "hcc_presence" for row in rows)
        or sum(row["label"] == "POSITIVE" for row in rows) != 39
        or sum(row["label"] == "NEGATIVE" for row in rows) != 49
    ):
        raise PipelineError("Ground truth protegido completo e invalido.")
    by_id = {str(row["case_id"]): row for row in rows}
    if len(by_id) != 88:
        raise PipelineError("Ground truth protegido contem duplicatas.")
    return by_id, _sha256(Path(path))


def evaluate_slice_pairwise(*, scores_root: Path, labels_path: Path, output_path: Path) -> dict[str, Any]:
    scores_root = Path(scores_root).resolve()
    summary_path = scores_root / "summary.json"
    summary = _load_json(summary_path)
    if (
        summary.get("schema") != RUN_SCHEMA or summary.get("status") != "complete"
        or summary.get("success_count") != summary.get("case_count")
        or summary.get("failure_count") != 0 or summary.get("final_decision") is not None
        or summary.get("ground_truth_read") is not False or summary.get("metrics_calculated") is not False
    ):
        raise PipelineError("Lote axial nao esta completo e cego.")
    case_ids = list(summary.get("case_ids") or [])
    if len(case_ids) != summary["case_count"] or len(case_ids) != len(set(case_ids)):
        raise PipelineError("Lista de casos axiais invalida.")
    features = {case_id: _verify_case(scores_root / case_id, summary) for case_id in case_ids}
    # Ground truth is opened only after every blind artifact above has passed.
    all_labels, labels_hash = _strict_labels(labels_path)
    if any(case_id not in all_labels for case_id in case_ids):
        raise PipelineError("Piloto axial contem case_id sem rotulo protegido.")
    truth = [all_labels[case_id]["label"] == "POSITIVE" for case_id in case_ids]
    positives, negatives = sum(truth), len(truth) - sum(truth)
    if positives < 2 or negatives < 2:
        raise PipelineError("Piloto axial nao possui ambas as classes em quantidade avaliavel.")
    analyses = []
    for name in sorted(next(iter(features.values()))):
        values = [features[case_id][name] for case_id in case_ids]
        threshold, apparent = _best_threshold(values, truth)
        analyses.append({
            "feature": name, "apparent_threshold": threshold, "apparent": apparent,
            "loocv": _loocv(values, truth),
            "repeated_5fold": _repeated_stratified_cv(values, truth),
        })
    analyses.sort(key=lambda item: (item["loocv"]["minimum_gate_metric"], item["loocv"]["balanced_accuracy"]), reverse=True)
    result = {
        "schema": "argos-openswisshcc-axial-slice-pairwise-evaluation-v1",
        "status": "exploratory_pilot_not_qualification",
        "case_count": len(case_ids), "positive_count": positives, "negative_count": negatives,
        "protected_ground_truth_sha256": labels_hash,
        "scores_summary_sha256": _sha256(summary_path),
        "observed_mean_case_seconds": summary["mean_case_seconds"],
        "observed_max_case_seconds": summary["max_case_seconds"],
        "time_gate_180_seconds_passed": summary["time_gate_180_seconds_passed"],
        "analyses": analyses, "holdout_opened": False, "qualified": False,
        "research_only": True, "clinical_use_allowed": False, "requires_human_review": True,
    }
    output_path = Path(output_path).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result
