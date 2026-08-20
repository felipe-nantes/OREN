"""Métricas multiclasse para o benchmark de patologia e variação hepática.

O ground truth de subtipo é anexado ao resultado somente depois da inferência.
Falha técnica, inconclusivo ou subtipo não determinado contam como erro na
métrica primária, em consonância com a política conservadora do benchmark.
"""
from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from .metrics import wilson_interval

SUBTYPE_CLASSES = ("hcc", "fnh", "hemangioma", "hepatic_cyst")
SUBTYPE_LABELS_PT = {
    "hcc": "HCC",
    "fnh": "FNH",
    "hemangioma": "Hemangioma",
    "hepatic_cyst": "Cisto hepático",
}
SUBTYPE_TO_BINARY_LABEL = {
    "hcc": "positive",
    "fnh": "negative",
    "hemangioma": "negative",
    "hepatic_cyst": "negative",
}
UNDETERMINED = "undetermined"


def binary_label_for_subtype(subtype: str) -> str:
    """Retorna o endpoint patológico binário, recusando vocabulário aberto."""
    try:
        return SUBTYPE_TO_BINARY_LABEL[subtype]
    except KeyError as exc:
        raise ValueError(f"Subtipo de referência inválido: {subtype!r}") from exc


def _predicted_subtype(row: dict[str, Any]) -> str:
    if row.get("status") != "decisive" or row.get("subtype_determined") is not True:
        return UNDETERMINED
    value = str(row.get("subtype") or "")
    return value if value in SUBTYPE_CLASSES else UNDETERMINED


def compute_subtype_metrics(
    results: Iterable[dict[str, Any]],
    *,
    minimum_balanced_accuracy: float = 0.75,
    confidence: float = 0.95,
) -> dict[str, Any]:
    """Calcula top-1, recall macro e matriz 4×5 com penalização integral."""
    rows = list(results)
    for row in rows:
        truth = row.get("truth_subtype")
        if truth not in SUBTYPE_CLASSES:
            raise ValueError(f"truth_subtype ausente ou inválido: {truth!r}")

    predicted_values = (*SUBTYPE_CLASSES, UNDETERMINED)
    confusion = {
        truth: {predicted: 0 for predicted in predicted_values}
        for truth in SUBTYPE_CLASSES
    }
    correct = 0
    determined = 0
    per_class: dict[str, dict[str, Any]] = {}

    for row in rows:
        truth = str(row["truth_subtype"])
        predicted = _predicted_subtype(row)
        confusion[truth][predicted] += 1
        is_correct = predicted == truth
        row["subtype_correct"] = is_correct
        row["predicted_subtype_for_scoring"] = predicted
        correct += int(is_correct)
        determined += int(predicted != UNDETERMINED)

    recalls: list[float] = []
    represented: list[str] = []
    for truth in SUBTYPE_CLASSES:
        total = sum(confusion[truth].values())
        class_correct = confusion[truth][truth]
        recall = round(class_correct / total, 4) if total else None
        if recall is not None:
            recalls.append(recall)
            represented.append(truth)
        per_class[truth] = {
            "label": SUBTYPE_LABELS_PT[truth],
            "total": total,
            "correct": class_correct,
            "errors": total - class_correct,
            "recall": recall,
            "confidence_interval_95": wilson_interval(class_correct, total, confidence),
        }

    total = len(rows)
    balanced_accuracy = round(sum(recalls) / len(recalls), 4) if recalls else None
    top1_accuracy = round(correct / total, 4) if total else None
    determination_rate = round(determined / total, 4) if total else None
    complete = len(represented) == len(SUBTYPE_CLASSES)
    met = bool(
        complete
        and balanced_accuracy is not None
        and balanced_accuracy >= minimum_balanced_accuracy
    )
    return {
        "scope": "primary_all_cases_four_class_subtype",
        "classes": list(SUBTYPE_CLASSES),
        "labels_pt": dict(SUBTYPE_LABELS_PT),
        "scoring_policy": (
            "technical_failure_inconclusive_or_undetermined_counts_as_subtype_error"
        ),
        "total_cases": total,
        "correct_cases": correct,
        "error_cases": total - correct,
        "determined_cases": determined,
        "undetermined_cases": total - determined,
        "top1_accuracy": top1_accuracy,
        "balanced_accuracy": balanced_accuracy,
        "determination_rate": determination_rate,
        "confidence_intervals_95": {
            "top1_accuracy": wilson_interval(correct, total, confidence),
            "determination_rate": wilson_interval(determined, total, confidence),
            "balanced_accuracy": None,
        },
        "balanced_accuracy_ci_method": "not_implemented",
        "represented_classes": represented,
        "class_coverage_complete": complete,
        "per_class": per_class,
        "confusion_matrix": confusion,
        "target": {
            "minimum_balanced_accuracy": minimum_balanced_accuracy,
            "balanced_accuracy": balanced_accuracy,
            "requires_all_four_classes": True,
            "met": met,
            "reason": (
                None
                if met
                else (
                    "missing_reference_classes"
                    if not complete
                    else "balanced_accuracy_below_target"
                )
            ),
        },
    }
