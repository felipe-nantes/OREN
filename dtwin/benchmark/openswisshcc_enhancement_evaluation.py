"""Exploratory development-only evaluation of blind v22 enhancement features."""
from __future__ import annotations

import json
import math
import shutil
import uuid
from pathlib import Path
from typing import Any

from dtwin.benchmark.openswisshcc_alignment import _publish_directory, _sha256
from dtwin.benchmark.openswisshcc_enhancement_maps import (
    CASE_SCHEMA,
    COHORT_SCHEMA,
)
from dtwin.core import PipelineError
from dtwin.medgemma_screening import _write_json_atomic

EVALUATION_SCHEMA = "argos-openswisshcc-enhancement-feature-evaluation-v22"
LABEL_SCHEMA = "argos-openswisshcc-ground-truth-v1"


def _load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PipelineError(f"JSON da avaliacao v22 invalido: {path}") from exc
    if not isinstance(value, dict):
        raise PipelineError("JSON da avaliacao v22 deve ser objeto.")
    return value


def _jsonl(path: Path) -> list[dict[str, Any]]:
    try:
        rows = [
            json.loads(line)
            for line in Path(path).read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    except (OSError, json.JSONDecodeError) as exc:
        raise PipelineError(f"JSONL da avaliacao v22 invalido: {path}") from exc
    if not rows or any(not isinstance(row, dict) for row in rows):
        raise PipelineError("JSONL da avaliacao v22 vazio ou invalido.")
    return rows


def _auc(positive: list[float], negative: list[float]) -> float:
    if not positive or not negative:
        raise PipelineError("AUC v22 exige as duas classes.")
    favorable = 0.0
    for left in positive:
        for right in negative:
            favorable += 1.0 if left > right else 0.5 if left == right else 0.0
    return favorable / (len(positive) * len(negative))


def _frontier(
    values: list[tuple[bool, float]], *, direction: int
) -> tuple[bool, dict[str, float]]:
    directed = [(truth, value * direction) for truth, value in values]
    thresholds = [-math.inf, *sorted({value for _, value in directed}), math.inf]
    best: tuple[float, float, float, float, float] | None = None
    meets = False
    for threshold in thresholds:
        tp = tn = fp = fn = 0
        for truth, value in directed:
            predicted = value >= threshold
            tp += truth and predicted
            fn += truth and not predicted
            tn += (not truth) and not predicted
            fp += (not truth) and predicted
        sensitivity = tp / (tp + fn)
        specificity = tn / (tn + fp)
        meets = meets or (sensitivity >= 0.75 and specificity >= 0.75)
        candidate = (
            min(sensitivity, specificity),
            (sensitivity + specificity) / 2.0,
            sensitivity,
            specificity,
            threshold,
        )
        if best is None or candidate > best:
            best = candidate
    assert best is not None
    return meets, {
        "best_minimum_sensitivity_specificity": best[0],
        "balanced_accuracy_at_best_minimum": best[1],
        "sensitivity_at_best_minimum": best[2],
        "specificity_at_best_minimum": best[3],
        "directed_threshold": best[4],
    }


def evaluate_enhancement_features_development(
    *, feature_root: Path, labels_path: Path, output_dir: Path
) -> dict[str, Any]:
    """Evaluate already-generated features; never use this result as holdout evidence."""

    feature_root = Path(feature_root).resolve()
    summary = _load(feature_root / "summary.json")
    rows = _jsonl(feature_root / "features.jsonl")
    if (
        summary.get("schema") != COHORT_SCHEMA
        or summary.get("status") != "complete_blind_features_with_declared_fallbacks"
        or summary.get("case_count") != 87
        or summary.get("case_ids") != [row.get("case_id") for row in rows]
        or summary.get("features_sha256") != _sha256(feature_root / "features.jsonl")
        or summary.get("labels_read") is not False
        or summary.get("ground_truth_lesion_masks_read") != 0
        or len(rows) != 87
    ):
        raise PipelineError("Bundle de features v22 invalido ou adulterado.")
    available = []
    for row in rows:
        if row.get("schema") != CASE_SCHEMA:
            raise PipelineError("Registro de feature v22 com schema invalido.")
        if row.get("status") == "complete_blind_features":
            if not isinstance(row.get("features"), dict):
                raise PipelineError("Registro v22 disponivel sem features.")
            available.append(row)
        elif row.get("status") != "unavailable_unregistered_fallback":
            raise PipelineError("Status individual v22 invalido.")
    if len(available) != summary.get("available_case_count"):
        raise PipelineError("Contagem disponivel v22 divergiu.")

    labels_rows = _jsonl(labels_path)
    labels: dict[str, bool] = {}
    for row in labels_rows:
        case_id = str(row.get("case_id", ""))
        if (
            row.get("schema") != LABEL_SCHEMA
            or row.get("label") not in {"POSITIVE", "NEGATIVE"}
            or case_id in labels
        ):
            raise PipelineError("Label de desenvolvimento v22 invalido.")
        labels[case_id] = row["label"] == "POSITIVE"
    if any(row["case_id"] not in labels for row in rows):
        raise PipelineError("Labels de desenvolvimento nao cobrem o full87 v22.")

    feature_keys = sorted(
        key
        for key, value in available[0]["features"].items()
        if isinstance(value, (int, float)) and not isinstance(value, bool)
    )
    analyses = []
    for key in feature_keys:
        values: list[tuple[bool, float]] = []
        for row in available:
            value = row["features"].get(key)
            if (
                not isinstance(value, (int, float))
                or isinstance(value, bool)
                or not math.isfinite(float(value))
            ):
                raise PipelineError(f"Feature escalar v22 invalida: {key}.")
            values.append((labels[row["case_id"]], float(value)))
        positive = [value for truth, value in values if truth]
        negative = [value for truth, value in values if not truth]
        auc = _auc(positive, negative)
        direction = 1 if auc >= 0.5 else -1
        meets, frontier = _frontier(values, direction=direction)
        analyses.append(
            {
                "feature": key,
                "roc_auc": auc,
                "best_direction_auc": max(auc, 1.0 - auc),
                "direction": "higher_is_positive" if direction == 1 else "lower_is_positive",
                "any_apparent_threshold_meets_75_75": meets,
                **frontier,
            }
        )
    analyses.sort(key=lambda item: (-item["best_direction_auc"], item["feature"]))
    positive_count = sum(labels[row["case_id"]] for row in available)
    negative_count = len(available) - positive_count
    result: dict[str, Any] = {
        "schema": EVALUATION_SCHEMA,
        "status": "development_exploratory_features_evaluated_not_qualified",
        "case_count": 87,
        "available_case_count": len(available),
        "unavailable_case_count": 87 - len(available),
        "available_positive_count": positive_count,
        "available_negative_count": negative_count,
        "feature_count": len(analyses),
        "feature_strategy": summary.get("feature_strategy", "global_liver_dynamic"),
        "algorithm_version": summary.get("algorithm_version"),
        "analyses": analyses,
        "best_feature": analyses[0] if analyses else None,
        "continuation_to_medgemma_recommended": bool(
            analyses
            and analyses[0]["best_direction_auc"] >= 0.70
            and analyses[0]["any_apparent_threshold_meets_75_75"] is True
        ),
        "qualified": False,
        "development_only": True,
        "nested_validation_performed": False,
        "holdout_v21_used_for_selection": False,
        "labels_opened_after_blind_features": True,
        "ground_truth_lesion_masks_read": 0,
        "feature_summary_sha256": _sha256(feature_root / "summary.json"),
        "features_sha256": _sha256(feature_root / "features.jsonl"),
        "development_labels_sha256": _sha256(Path(labels_path).resolve()),
        "research_only": True,
        "clinical_use_allowed": False,
        "requires_human_review": True,
    }
    output_dir = Path(output_dir).resolve()
    if output_dir.exists():
        raise PipelineError("Avaliacao de features v22 ja existe.")
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    staging = output_dir.parent / f"._v22enh_eval_{uuid.uuid4().hex[:8]}"
    staging.mkdir()
    try:
        _write_json_atomic(staging / "evaluation.json", result)
        best = result["best_feature"]
        report = (
            "# OpenSwissHCC v22 - realce multifasico exploratorio\n\n"
            f"- Casos com features: {len(available)} ({positive_count} positivos, {negative_count} negativos)\n"
            f"- Melhor feature: {best['feature'] if best else 'n/a'}\n"
            f"- Melhor AUC direcional: {best['best_direction_auc']:.4f}\n"
            f"- Algum limiar aparente 75%/75%: {best['any_apparent_threshold_meets_75_75'] if best else False}\n"
            f"- Continuar para MedGemma: {result['continuation_to_medgemma_recommended']}\n"
            "- Qualificado: false (desenvolvimento exploratorio; sem validacao aninhada)\n"
        )
        (staging / "report.md").write_text(report, encoding="utf-8")
        _publish_directory(staging, output_dir)
        return result
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise


__all__ = ["EVALUATION_SCHEMA", "evaluate_enhancement_features_development"]
