"""Retrospective diagnostics for frozen external signals; never selects deployment policy."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np

from dtwin.core import PipelineError
from dtwin.learning.external_bundle_evaluation import _metrics
from dtwin.learning.protocol import canonical_sha256, load_protected_cases, sha256_file

SCHEMA = "oren-external-signal-diagnostics-v1"


def _json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PipelineError(f"JSON externo invalido: {path}") from exc
    if not isinstance(value, dict):
        raise PipelineError(f"Objeto JSON esperado: {path}")
    return value


def _jsonl(path: Path) -> list[dict[str, Any]]:
    try:
        return [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]
    except (OSError, json.JSONDecodeError) as exc:
        raise PipelineError(f"JSONL externo invalido: {path}") from exc


def _load_prediction_root(root: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    freeze = _json(Path(root) / "prediction_freeze.json")
    unsigned = dict(freeze)
    signature = unsigned.pop("prediction_signature", None)
    if signature != canonical_sha256(unsigned):
        raise PipelineError("Assinatura de predicao externa diverge.")
    path = Path(root) / "predictions.jsonl"
    if freeze.get("predictions_sha256") != sha256_file(path):
        raise PipelineError("Predicoes externas foram alteradas.")
    rows = _jsonl(path)
    if any("label" in row or "ground_truth" in row for row in rows):
        raise PipelineError("Predicao externa contem ground truth.")
    return freeze, rows


def _quantiles(values: list[float]) -> dict[str, float] | None:
    if not values:
        return None
    array = np.asarray(values, dtype=np.float64)
    return {name: float(value) for name, value in zip(
        ("min", "q25", "median", "q75", "max"), np.quantile(array, (0, .25, .5, .75, 1))
    )}


def _oracle(rows: list[dict[str, Any]], labels: dict[str, str]) -> dict[str, Any]:
    scores = sorted({float(row["score"]) for row in rows if row.get("score") is not None})
    if not scores:
        return {"threshold": None, "feasible_75_75_threshold_count": 0}
    thresholds = [scores[0] - 1e-12, scores[-1] + 1e-12, *scores]
    candidates = []
    for threshold in thresholds:
        adjusted = [{
            **row,
            "prediction": (
                "TECHNICAL_FAILURE" if row.get("technical_failure")
                else ("POSITIVE" if float(row["score"]) >= threshold else "NEGATIVE")
            ),
        } for row in rows]
        metric = _metrics(adjusted, labels)
        candidates.append((threshold, metric))
    best = max(candidates, key=lambda item: (
        min(item[1]["sensitivity"], item[1]["specificity"]),
        item[1]["balanced_accuracy"], -abs(item[0] - .5),
    ))
    return {
        "threshold": float(best[0]), "metrics": best[1],
        "feasible_75_75_threshold_count": sum(
            metric["sensitivity"] >= .75 and metric["specificity"] >= .75
            for _, metric in candidates
        ),
        "retrospective_only_not_deployable": True,
    }


def build_external_signal_diagnostics(
    *, prediction_roots: dict[str, Path], training_protocol_config_path: Path,
    workspace_root: Path, protected_dataset_ids: set[str], output_path: Path,
) -> dict[str, Any]:
    if Path(output_path).exists():
        raise PipelineError("Diagnostico externo ja existe; saida e imutavel.")
    protected = {
        case.case_id: case for case in load_protected_cases(
            training_protocol_config_path, workspace_root
        ) if case.dataset_id in protected_dataset_ids
    }
    labels = {case_id: case.label for case_id, case in protected.items()}
    sources: dict[str, Any] = {}
    scores_by_signal: dict[str, dict[str, float]] = {}
    expected = set(labels)
    for name, root in prediction_roots.items():
        freeze, rows = _load_prediction_root(root)
        if {str(row["case_id"]) for row in rows} != expected:
            raise PipelineError(f"Cobertura externa divergente no sinal {name}.")
        score_map = {
            str(row["case_id"]): float(row["score"])
            for row in rows if row.get("score") is not None
        }
        scores_by_signal[name] = score_map
        sources[name] = {
            "prediction_signature": freeze["prediction_signature"],
            "frozen_metrics": _metrics(rows, labels),
            "score_distribution_positive": _quantiles([
                score for case_id, score in score_map.items() if labels[case_id] == "POSITIVE"
            ]),
            "score_distribution_negative": _quantiles([
                score for case_id, score in score_map.items() if labels[case_id] == "NEGATIVE"
            ]),
            "retrospective_threshold_oracle": _oracle(rows, labels),
        }
    correlations: dict[str, float | None] = {}
    names = list(prediction_roots)
    for index, left in enumerate(names):
        for right in names[index + 1:]:
            common = sorted(set(scores_by_signal[left]) & set(scores_by_signal[right]))
            correlations[f"{left}_vs_{right}"] = (
                float(np.corrcoef(
                    [scores_by_signal[left][case_id] for case_id in common],
                    [scores_by_signal[right][case_id] for case_id in common],
                )[0, 1]) if len(common) > 1 else None
            )
    body = {
        "schema": SCHEMA, "signals": sources, "score_correlations": correlations,
        "case_count": len(labels), "labels_opened_for_retrospective_diagnostics": True,
        "diagnostics_must_not_be_used_to_rethreshold_same_cohort": True,
        "lesion_masks_read": 0, "research_only": True, "clinical_use_allowed": False,
    }
    report = {**body, "diagnostic_signature": canonical_sha256(body)}
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    Path(output_path).write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return report


__all__ = ["build_external_signal_diagnostics"]
