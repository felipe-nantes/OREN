"""Post-inference evaluation and robust threshold exploration for volumetric v4."""
from __future__ import annotations

import json
import math
import random
import shutil
import statistics
import uuid
from pathlib import Path
from typing import Any, Callable, Mapping

from dtwin.benchmark.metrics import compute_benchmark_metrics
from dtwin.benchmark.openswisshcc_alignment import _load_json, _publish_directory, _sha256
from dtwin.benchmark.openswisshcc_evaluation import (
    _case_result,
    _load_labels_after_inference,
    _quantile,
)
from dtwin.benchmark.openswisshcc_volumetric_gate import verify_volumetric_freeze
from dtwin.benchmark.openswisshcc_volumetric_inference import INFERENCE_SCHEMA, RUN_SCHEMA
from dtwin.benchmark.reporting import write_run_outputs
from dtwin.core import PipelineError, now_utc


def _validate_run_before_truth(
    *, inference_root: Path, freeze: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, dict[str, Any]], dict[str, dict[str, float]]]:
    root = Path(inference_root).resolve()
    summary = _load_json(root / "inference_summary.json")
    if summary.get("schema") != RUN_SCHEMA or summary.get("status") != "complete":
        raise PipelineError("Execucao volumetrica nao esta tecnicamente completa.")
    if summary.get("ground_truth_read") is not False or summary.get("metrics_calculated") is not False:
        raise PipelineError("Resumo volumetrico viola o isolamento pre-avaliacao.")
    if (
        summary.get("experiment_signature") != freeze["experiment_signature"]
        or summary.get("review_signature") != freeze["review_signature"]
        or summary.get("case_count") != freeze["case_count"]
        or summary.get("panel_image_count") != freeze["panel_image_count"]
        or summary.get("success_count") != freeze["case_count"]
        or summary.get("failure_count") != 0
        or summary.get("all_cases_within_time_limit") is not True
    ):
        raise PipelineError("Resumo volumetrico diverge do freeze ou possui falha/timeout.")

    records: dict[str, dict[str, Any]] = {}
    signals: dict[str, dict[str, float]] = {}
    frozen_ids = [str(item["case_id"]) for item in freeze["candidates"]]
    visible_dirs = sorted(
        item.name for item in root.iterdir()
        if item.is_dir() and not item.name.startswith(".")
    )
    if visible_dirs != sorted(frozen_ids):
        raise PipelineError("Diretorios da inferencia nao cobrem exatamente a coorte congelada.")
    for frozen in freeze["candidates"]:
        case_id = str(frozen["case_id"])
        case_dir = root / case_id
        manifest = _load_json(case_dir / "inference_manifest.json")
        report_path = case_dir / "medgemma_report.json"
        panel_reports_path = case_dir / "medgemma_panel_reports.json"
        if (
            manifest.get("schema") != INFERENCE_SCHEMA
            or manifest.get("status") != "success_pending_human_review"
            or manifest.get("experiment_signature") != freeze["experiment_signature"]
            or manifest.get("candidate_signature") != frozen["candidate_signature"]
            or manifest.get("panel_set_sha256") != frozen["panel_set_sha256"]
            or manifest.get("panel_image_count") != frozen["panel_image_count"]
            or manifest.get("ground_truth_read") is not False
            or manifest.get("metrics_calculated") is not False
            or manifest.get("within_time_limit") is not True
            or not report_path.is_file() or not panel_reports_path.is_file()
            or _sha256(report_path) != manifest.get("report_sha256")
        ):
            raise PipelineError(f"Artefatos volumetricos invalidos no caso {case_id}.")
        envelope = _load_json(report_path)
        if (
            envelope.get("case_id") != case_id
            or envelope.get("qualification", {}).get("ground_truth_read") is not False
            or envelope.get("qualification", {}).get("metrics_calculated") is not False
            or envelope.get("qualification", {}).get("experiment_signature") != freeze["experiment_signature"]
        ):
            raise PipelineError(f"Envelope volumetrico invalido no caso {case_id}.")
        panel_reports = json.loads(panel_reports_path.read_text(encoding="utf-8"))
        if not isinstance(panel_reports, list) or len(panel_reports) != frozen["panel_image_count"]:
            raise PipelineError(f"Respostas por painel incompletas no caso {case_id}.")
        states = [str(item.get("report", {}).get("resultado_hipotese")) for item in panel_reports]
        expected_prediction = (
            "POSITIVA" if "POSITIVA" in states
            else "INCONCLUSIVA" if "INCONCLUSIVA" in states
            else "NEGATIVA"
        )
        if manifest.get("prediction") != expected_prediction:
            raise PipelineError(f"Agregacao final divergiu das respostas no caso {case_id}.")
        probability_rows: list[dict[str, float]] = []
        for number, (entry, frozen_panel) in enumerate(zip(panel_reports, frozen["panels"], strict=True), start=1):
            if (
                entry.get("panel_number") != number
                or entry.get("sha256") != frozen_panel["sha256"]
                or entry.get("image") != frozen_panel["image"]
            ):
                raise PipelineError(f"Ordem/hash de painel divergiu no caso {case_id}.")
            raw = entry.get("response_validation_audit", {}).get("choice_probabilities")
            try:
                row = {key: float(raw[key]) for key in ("POSITIVA", "NEGATIVA", "INCONCLUSIVA")}
            except (KeyError, TypeError, ValueError) as exc:
                raise PipelineError(f"Probabilidades ausentes no caso {case_id}.") from exc
            if any(not math.isfinite(value) or value < 0 or value > 1 for value in row.values()):
                raise PipelineError(f"Probabilidade invalida no caso {case_id}.")
            if not 0.999 <= sum(row.values()) <= 1.001:
                raise PipelineError(f"Probabilidades nao somam 1 no caso {case_id}.")
            probability_rows.append(row)
        records[case_id] = manifest
        signals[case_id] = _case_signals(probability_rows)
    return summary, records, signals


def _case_signals(rows: list[dict[str, float]]) -> dict[str, float]:
    pos = [row["POSITIVA"] for row in rows]
    neg = [row["NEGATIVA"] for row in rows]
    inc = [row["INCONCLUSIVA"] for row in rows]
    margins = [p - n for p, n in zip(pos, neg, strict=True)]
    top2 = sorted(pos, reverse=True)[:2]
    return {
        "mean_positive": statistics.fmean(pos),
        "median_positive": statistics.median(pos),
        "max_positive": max(pos),
        "top2_mean_positive": statistics.fmean(top2),
        "mean_positive_minus_negative": statistics.fmean(margins),
        "max_positive_minus_negative": max(margins),
        "positive_vote_fraction": sum(
            p >= n and p >= i for p, n, i in zip(pos, neg, inc, strict=True)
        ) / len(rows),
        "inverse_mean_negative": -statistics.fmean(neg),
        "inverse_max_negative": -max(neg),
        "mean_inconclusive_minus_negative": statistics.fmean(
            [i - n for i, n in zip(inc, neg, strict=True)]
        ),
    }


def _binary_metrics(truth: list[bool], predicted: list[bool]) -> dict[str, Any]:
    tp = sum(t and p for t, p in zip(truth, predicted, strict=True))
    tn = sum((not t) and (not p) for t, p in zip(truth, predicted, strict=True))
    fp = sum((not t) and p for t, p in zip(truth, predicted, strict=True))
    fn = sum(t and (not p) for t, p in zip(truth, predicted, strict=True))
    sensitivity = tp / (tp + fn) if tp + fn else 0.0
    specificity = tn / (tn + fp) if tn + fp else 0.0
    return {
        "tp": tp, "tn": tn, "fp": fp, "fn": fn,
        "sensitivity": sensitivity, "specificity": specificity,
        "balanced_accuracy": (sensitivity + specificity) / 2,
        "minimum_gate_metric": min(sensitivity, specificity),
        "passed_75_75": sensitivity >= 0.75 and specificity >= 0.75,
    }


def _best_threshold(scores: list[float], truth: list[bool]) -> tuple[float, dict[str, Any]]:
    unique = sorted(set(scores))
    thresholds = [unique[0] - 1e-12] + [
        (left + right) / 2 for left, right in zip(unique, unique[1:])
    ] + [unique[-1] + 1e-12]
    candidates = []
    for threshold in thresholds:
        metrics = _binary_metrics(truth, [score >= threshold for score in scores])
        candidates.append((
            metrics["minimum_gate_metric"], metrics["balanced_accuracy"],
            -abs(metrics["sensitivity"] - metrics["specificity"]), -threshold,
            threshold, metrics,
        ))
    best = max(candidates)
    return float(best[-2]), best[-1]


def _loocv(scores: list[float], truth: list[bool]) -> dict[str, Any]:
    predicted = []
    thresholds = []
    for held_out in range(len(scores)):
        train_scores = [value for index, value in enumerate(scores) if index != held_out]
        train_truth = [value for index, value in enumerate(truth) if index != held_out]
        threshold, _ = _best_threshold(train_scores, train_truth)
        thresholds.append(threshold)
        predicted.append(scores[held_out] >= threshold)
    return {**_binary_metrics(truth, predicted), "thresholds": thresholds}


def _repeated_stratified_cv(
    scores: list[float], truth: list[bool], *, repeats: int = 50, folds: int = 5,
) -> dict[str, Any]:
    positive = [i for i, value in enumerate(truth) if value]
    negative = [i for i, value in enumerate(truth) if not value]
    outcomes = []
    for repeat in range(repeats):
        rng = random.Random(20260714 + repeat)
        pos = positive[:]
        neg = negative[:]
        rng.shuffle(pos)
        rng.shuffle(neg)
        groups = [[] for _ in range(folds)]
        for index, item in enumerate(pos):
            groups[index % folds].append(item)
        for index, item in enumerate(neg):
            groups[index % folds].append(item)
        predicted = [False] * len(scores)
        for test_indices in groups:
            test = set(test_indices)
            train_indices = [i for i in range(len(scores)) if i not in test]
            threshold, _ = _best_threshold(
                [scores[i] for i in train_indices], [truth[i] for i in train_indices]
            )
            for i in test_indices:
                predicted[i] = scores[i] >= threshold
        outcomes.append(_binary_metrics(truth, predicted))
    return {
        "repeats": repeats,
        "folds": folds,
        "runs_passing_75_75": sum(item["passed_75_75"] for item in outcomes),
        "median_sensitivity": statistics.median(item["sensitivity"] for item in outcomes),
        "median_specificity": statistics.median(item["specificity"] for item in outcomes),
        "minimum_sensitivity": min(item["sensitivity"] for item in outcomes),
        "minimum_specificity": min(item["specificity"] for item in outcomes),
    }


def _explore_signals(
    *, case_ids: list[str], truth_by_id: dict[str, dict[str, Any]],
    signals: dict[str, dict[str, float]],
) -> dict[str, Any]:
    truth = [truth_by_id[case_id]["label"] == "POSITIVE" for case_id in case_ids]
    features = sorted(next(iter(signals.values())))
    results = []
    for feature in features:
        scores = [signals[case_id][feature] for case_id in case_ids]
        threshold, apparent = _best_threshold(scores, truth)
        results.append({
            "feature": feature,
            "direction": "higher_is_positive",
            "apparent_best_threshold": threshold,
            "apparent_metrics": apparent,
            "loocv_metrics": _loocv(scores, truth),
            "repeated_stratified_5fold": _repeated_stratified_cv(scores, truth),
        })
    results.sort(
        key=lambda item: (
            item["loocv_metrics"]["minimum_gate_metric"],
            item["loocv_metrics"]["balanced_accuracy"],
        ),
        reverse=True,
    )
    return {
        "status": "development_only_exploration_not_qualified",
        "thresholds_selected_using_development_labels": True,
        "holdout_opened": False,
        "selection_rule": "maximize minimum(sensitivity,specificity), then balanced accuracy",
        "features": results,
    }


def evaluate_volumetric_development_run(
    *, panel_root: Path, review_path: Path, freeze_path: Path,
    inference_root: Path, protected_labels_path: Path, output_dir: Path,
    config_paths: Mapping[str, Path], expected_case_count: int = 88,
    expected_positive: int = 39, expected_negative: int = 49,
) -> dict[str, Any]:
    """Validate all blinded artifacts, then open development labels exactly here."""
    output_dir = Path(output_dir).resolve()
    if output_dir.exists():
        raise PipelineError("Diretorio de avaliacao ja existe; nao sera sobrescrito.")
    freeze = verify_volumetric_freeze(
        freeze_path=freeze_path, panel_root=panel_root, review_path=review_path,
        config_paths=config_paths, expected_case_count=expected_case_count,
    )
    summary, records, signals = _validate_run_before_truth(
        inference_root=inference_root, freeze=freeze
    )
    case_ids = sorted(records)
    labels, protected_hash = _load_labels_after_inference(
        protected_labels_path,
        expected_ids=case_ids,
        expected_positive=expected_positive,
        expected_negative=expected_negative,
    )
    results = [
        _case_result(
            case_id=case_id, inference_root=Path(inference_root).resolve(),
            record=records[case_id], label=labels[case_id], protected_hash=protected_hash,
        )
        for case_id in case_ids
    ]
    metrics = compute_benchmark_metrics(results, minimum_sensitivity=0.75, minimum_specificity=0.75)
    elapsed = [float(records[case_id]["elapsed_seconds"]) for case_id in case_ids]
    timing = {
        "case_count": len(elapsed),
        "mean_seconds": statistics.fmean(elapsed),
        "median_seconds": statistics.median(elapsed),
        "p95_seconds": _quantile(elapsed, 0.95),
        "max_seconds": max(elapsed),
        "limit_seconds": float(freeze["max_case_seconds"]),
        "timeout_count": 0,
        "passed": max(elapsed) <= float(freeze["max_case_seconds"]),
    }
    exploration = _explore_signals(case_ids=case_ids, truth_by_id=labels, signals=signals)
    run_manifest = {
        "schema": "argos-openswisshcc-volumetric-evaluation-v1",
        "run_id": freeze["experiment_version"],
        "created_at": now_utc(),
        "model_id": "google/medgemma-1.5-4b-it",
        "model_parameter_scale": "4B",
        "review_signature": freeze["review_signature"],
        "experiment_signature": freeze["experiment_signature"],
        "inference_summary_sha256": _sha256(Path(inference_root) / "inference_summary.json"),
        "protected_ground_truth_sha256": protected_hash,
        "ground_truth_opened_after_complete_inference_validation": True,
        "official_aggregation_rule": freeze["aggregation_rule"],
        "development_signal_exploration_is_not_holdout_claim": True,
        "research_only": True,
        "clinical_use_allowed": False,
        "requires_human_review": True,
    }
    staging = output_dir.with_name(f".{output_dir.name}.staging.{uuid.uuid4().hex}")
    staging.mkdir(parents=True)
    try:
        write_run_outputs(staging, run_manifest, results, metrics)
        (staging / "timing_metrics.json").write_text(
            json.dumps(timing, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        (staging / "signal_exploration.json").write_text(
            json.dumps(exploration, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        score_rows = [
            {"case_id": case_id, "label": labels[case_id]["label"], **signals[case_id]}
            for case_id in case_ids
        ]
        (staging / "case_signals.jsonl").write_text(
            "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in score_rows),
            encoding="utf-8",
        )
        gate = {
            "official_sensitivity_specificity_gate": metrics["gate"],
            "time_gate": timing,
            "passed": bool(metrics["gate"]["passed"] and timing["passed"]),
            "holdout_not_evaluated": True,
            "exploratory_thresholds_do_not_change_official_result": True,
        }
        (staging / "qualification_gate.json").write_text(
            json.dumps(gate, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        _publish_directory(staging, output_dir)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return {
        "metrics": metrics,
        "timing": timing,
        "signal_exploration": exploration,
        "passed": bool(metrics["gate"]["passed"] and timing["passed"]),
        "output_dir": str(output_dir),
        "inference_case_count": summary["case_count"],
    }
