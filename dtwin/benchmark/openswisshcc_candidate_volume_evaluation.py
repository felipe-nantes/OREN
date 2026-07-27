"""Frozen development evaluation for the blind OpenSwissHCC v16 focal reader."""
from __future__ import annotations

import csv
import hashlib
import json
import math
import random
import shutil
import statistics
import uuid
from pathlib import Path
from typing import Any

from dtwin.benchmark.openswisshcc_alignment import _publish_directory, _sha256
from dtwin.benchmark.openswisshcc_candidate_volume_score import (
    CASE_TIME_GATE_SECONDS,
    CHOICES,
    PREDICTION_SCHEMA,
    PROGRESS_SCHEMA,
    SUMMARY_SCHEMA,
    _load_protocol,
    _validate_existing_prediction,
    validate_candidate_volume_bundle,
)
from dtwin.benchmark.openswisshcc_lesion_localizer_evaluation import _load_development_labels
from dtwin.benchmark.openswisshcc_localizer_roi_evaluation import _wilson
from dtwin.benchmark.openswisshcc_volumetric_evaluation import _best_threshold, _binary_metrics
from dtwin.core import PipelineError
from dtwin.medgemma_screening import _write_json_atomic


PROTOCOL_SCHEMA = "argos-openswisshcc-candidate-volume-evaluation-protocol-v16"
EVALUATION_SCHEMA = "argos-openswisshcc-candidate-volume-development-evaluation-v16"
PRIMARY_SIGNAL = "maximum_candidate_log_odds_positive_vs_negative_v1"
REPEATS = 50
FOLDS = 5
RANDOM_SEED = 20260716
FORBIDDEN_BLIND_KEYS = {
    "label",
    "ground_truth",
    "expected",
    "negative_subtype",
    "positive_subtype",
    "phenotype_tags",
    "target_condition",
}


def _load_json(path: Path, description: str) -> dict[str, Any]:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PipelineError(f"{description} ausente ou invalido.") from exc
    if not isinstance(value, dict):
        raise PipelineError(f"{description} deve ser um objeto JSON.")
    return value


def _canonical_sha(value: Any) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _finite(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise PipelineError("Score v16 deve ser numerico.")
    result = float(value)
    if not math.isfinite(result):
        raise PipelineError("Score v16 deve ser finito.")
    return result


def _contains_forbidden_key(value: Any) -> bool:
    if isinstance(value, dict):
        if any(str(key).lower() in FORBIDDEN_BLIND_KEYS for key in value):
            return True
        return any(_contains_forbidden_key(item) for item in value.values())
    if isinstance(value, list):
        return any(_contains_forbidden_key(item) for item in value)
    return False


def validate_blind_score_run(
    *,
    bundle_root: Path,
    run_root: Path,
    score_protocol_path: Path,
    expected_case_count: int = 87,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Validate every blind v16 prediction without reading protected labels."""

    bundle = validate_candidate_volume_bundle(bundle_root)
    protocol = _load_protocol(score_protocol_path)
    root = Path(run_root).resolve()
    progress_path = root / "progress.json"
    summary_path = root / "summary.json"
    progress = _load_json(progress_path, "Progresso cego v16")
    summary = _load_json(summary_path, "Resumo cego v16")
    if (
        bundle["case_count"] != expected_case_count
        or protocol.get("case_count") != expected_case_count
        or protocol.get("case_ids") != bundle["case_ids"]
        or protocol.get("bundle_cohort_sha256") != bundle["cohort_sha256"]
        or protocol.get("bundle_gallery_signature") != bundle["cohort"].get("gallery_signature")
        or progress.get("schema") != PROGRESS_SCHEMA
        or progress.get("status") != "complete"
        or progress.get("case_count") != expected_case_count
        or progress.get("completed_case_count") != expected_case_count
        or progress.get("pending_case_count") != 0
        or summary.get("schema") != SUMMARY_SCHEMA
        or summary.get("status") != "complete"
        or summary.get("case_count") != expected_case_count
        or summary.get("completed_case_count") != expected_case_count
        or summary.get("pending_case_count") != 0
        or summary.get("candidate_request_count") != bundle["candidate_stack_count"]
        or summary.get("protocol_signature") != protocol["protocol_signature"]
        or progress.get("protocol_signature") != protocol["protocol_signature"]
        or summary.get("predictions") != progress.get("predictions")
        or summary.get("scoring_timing_seconds", {}).get("all_within_180") is not True
        or summary.get("timing_scope") != "precomputed_candidate_scoring_only"
        or summary.get("end_to_end_180_seconds_proven") is not False
        or summary.get("accuracy_claimed") is not False
    ):
        raise PipelineError("Execucao cega v16 incompleta ou divergente do protocolo.")
    for payload in (progress, summary):
        if (
            payload.get("ground_truth_read") is not False
            or payload.get("metrics_calculated") is not False
            or payload.get("holdout_opened") is not False
            or payload.get("research_only") is not True
            or payload.get("clinical_use_allowed") is not False
            or payload.get("requires_human_review") is not True
            or _contains_forbidden_key(payload)
        ):
            raise PipelineError("Execucao v16 violou cegamento ou salvaguardas.")
    records = progress.get("predictions")
    if not isinstance(records, list) or len(records) != expected_case_count:
        raise PipelineError("Indice de predicoes v16 incompleto.")
    by_case = {case["case_id"]: case for case in bundle["cases"]}
    if len(by_case) != expected_case_count:
        raise PipelineError("Bundle v16 possui casos duplicados.")
    validated: list[dict[str, Any]] = []
    seen: set[str] = set()
    for record in records:
        case_id = str(record.get("case_id", ""))
        prediction_path = root / "predictions" / f"{case_id}.json"
        case = by_case.get(case_id)
        if (
            not case_id
            or case is None
            or case_id in seen
            or record.get("prediction_sha256") != _sha256(prediction_path)
        ):
            raise PipelineError("Indice v16 duplicado, desconhecido ou com hash divergente.")
        prediction = _validate_existing_prediction(prediction_path, case, protocol)
        aggregation = prediction.get("aggregation", {})
        score = _finite(aggregation.get("case_score"))
        if (
            prediction.get("schema") != PREDICTION_SCHEMA
            or aggregation.get("method") != PRIMARY_SIGNAL
            or aggregation.get("selected_candidate_classification") not in CHOICES
            or record.get("case_score") != score
            or record.get("selected_candidate_number") != aggregation.get("selected_candidate_number")
            or record.get("scoring_elapsed_seconds") != prediction.get("scoring_elapsed_seconds")
            or prediction.get("time_gate_passed") is not True
            or float(prediction.get("scoring_elapsed_seconds", CASE_TIME_GATE_SECONDS + 1))
            > CASE_TIME_GATE_SECONDS
            or _contains_forbidden_key(prediction)
        ):
            raise PipelineError(f"Predicao cega v16 invalida: {case_id}.")
        seen.add(case_id)
        validated.append(
            {
                "case_id": case_id,
                "case_score": score,
                "selected_candidate_classification": aggregation[
                    "selected_candidate_classification"
                ],
                "selected_candidate_number": aggregation["selected_candidate_number"],
                "candidate_stack_count": prediction["candidate_stack_count"],
                "scoring_elapsed_seconds": float(prediction["scoring_elapsed_seconds"]),
                "prediction_sha256": record["prediction_sha256"],
            }
        )
    if seen != set(bundle["case_ids"]):
        raise PipelineError("Predicoes v16 nao cobrem os casos congelados.")
    return {
        "bundle": bundle,
        "score_protocol": protocol,
        "progress_sha256": _sha256(progress_path),
        "summary_sha256": _sha256(summary_path),
        "summary": summary,
    }, validated


def create_evaluation_protocol(
    *,
    bundle_root: Path,
    run_root: Path,
    score_protocol_path: Path,
    output_path: Path,
    expected_case_count: int = 87,
) -> dict[str, Any]:
    context, rows = validate_blind_score_run(
        bundle_root=bundle_root,
        run_root=run_root,
        score_protocol_path=score_protocol_path,
        expected_case_count=expected_case_count,
    )
    output = Path(output_path).resolve()
    if output.exists():
        raise PipelineError("Protocolo de avaliacao v16 ja existe; sobrescrita recusada.")
    vector = [
        [
            row["case_id"],
            row["case_score"],
            row["selected_candidate_classification"],
            row["prediction_sha256"],
        ]
        for row in rows
    ]
    summary = context["summary"]
    payload = {
        "schema": PROTOCOL_SCHEMA,
        "status": "frozen_before_protected_development_labels",
        "case_count": expected_case_count,
        "case_ids": [row["case_id"] for row in rows],
        "score_protocol_signature": context["score_protocol"]["protocol_signature"],
        "score_progress_sha256": context["progress_sha256"],
        "score_summary_sha256": context["summary_sha256"],
        "raw_blind_vector_sha256": _canonical_sha(vector),
        "primary_signal": PRIMARY_SIGNAL,
        "component_direction": "higher_is_more_suspicious",
        "primary_estimator": "leave_one_out_threshold_fit_on_training_only",
        "threshold_selection": "maximize_minimum_sensitivity_specificity_then_balanced_accuracy_on_training_only",
        "robustness_estimator": f"repeated_stratified_{FOLDS}fold_{REPEATS}_repeats_seed_{RANDOM_SEED}_threshold_fit_inside_training_only",
        "secondary_diagnostics": [
            "zero_log_odds_threshold_not_eligible_for_model_selection",
            "selected_candidate_raw_categorical_inconclusive_counted_as_error",
        ],
        "secondary_diagnostics_cannot_replace_primary": True,
        "confidence_intervals": "wilson_95_percent_on_primary_loocv_confusion_matrix",
        "development_gate": {
            "minimum_loocv_sensitivity": 0.75,
            "minimum_loocv_specificity": 0.75,
            "required_repeated_runs_passing_75_75": REPEATS,
            "inconclusive_is_error_for_raw_categorical_diagnostic": True,
        },
        "score_time_gate_seconds": CASE_TIME_GATE_SECONDS,
        "observed_score_timing_seconds": summary["scoring_timing_seconds"],
        "score_time_gate_passed": summary["scoring_timing_seconds"]["all_within_180"],
        "timing_scope": summary["timing_scope"],
        "full_raw_dicom_end_to_end_180_seconds_proven": False,
        "ground_truth_read": False,
        "metrics_calculated": False,
        "holdout_opened": False,
        "research_only": True,
        "clinical_use_allowed": False,
        "requires_human_review": True,
    }
    payload["protocol_signature"] = _canonical_sha(payload)
    output.parent.mkdir(parents=True, exist_ok=True)
    _write_json_atomic(output, payload)
    return payload


def verify_evaluation_protocol(
    *,
    bundle_root: Path,
    run_root: Path,
    score_protocol_path: Path,
    evaluation_protocol_path: Path,
    expected_case_count: int = 87,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    context, rows = validate_blind_score_run(
        bundle_root=bundle_root,
        run_root=run_root,
        score_protocol_path=score_protocol_path,
        expected_case_count=expected_case_count,
    )
    protocol = _load_json(evaluation_protocol_path, "Protocolo de avaliacao v16")
    unsigned = {key: value for key, value in protocol.items() if key != "protocol_signature"}
    vector = [
        [
            row["case_id"],
            row["case_score"],
            row["selected_candidate_classification"],
            row["prediction_sha256"],
        ]
        for row in rows
    ]
    if (
        protocol.get("schema") != PROTOCOL_SCHEMA
        or protocol.get("status") != "frozen_before_protected_development_labels"
        or protocol.get("protocol_signature") != _canonical_sha(unsigned)
        or protocol.get("case_count") != expected_case_count
        or protocol.get("case_ids") != [row["case_id"] for row in rows]
        or protocol.get("score_protocol_signature")
        != context["score_protocol"]["protocol_signature"]
        or protocol.get("score_progress_sha256") != context["progress_sha256"]
        or protocol.get("score_summary_sha256") != context["summary_sha256"]
        or protocol.get("raw_blind_vector_sha256") != _canonical_sha(vector)
        or protocol.get("primary_signal") != PRIMARY_SIGNAL
        or protocol.get("secondary_diagnostics_cannot_replace_primary") is not True
        or protocol.get("score_time_gate_passed") is not True
        or protocol.get("full_raw_dicom_end_to_end_180_seconds_proven") is not False
        or protocol.get("ground_truth_read") is not False
        or protocol.get("metrics_calculated") is not False
        or protocol.get("holdout_opened") is not False
    ):
        raise PipelineError("Protocolo de avaliacao v16 invalido ou divergente do run cego.")
    return protocol, rows


def _loocv(scores: list[float], truth: list[bool]) -> dict[str, Any]:
    predicted: list[bool] = []
    thresholds: list[float] = []
    for test_index, score in enumerate(scores):
        train = [index for index in range(len(scores)) if index != test_index]
        threshold, _ = _best_threshold(
            [scores[index] for index in train], [truth[index] for index in train]
        )
        predicted.append(score >= threshold)
        thresholds.append(threshold)
    return {**_binary_metrics(truth, predicted), "thresholds": thresholds}


def _repeated_nested(
    scores: list[float],
    truth: list[bool],
    *,
    repeats: int = REPEATS,
    folds: int = FOLDS,
) -> dict[str, Any]:
    positive = [index for index, value in enumerate(truth) if value]
    negative = [index for index, value in enumerate(truth) if not value]
    if min(len(positive), len(negative)) < folds:
        raise PipelineError("Coorte insuficiente para validacao estratificada v16.")
    outcomes: list[dict[str, Any]] = []
    for repeat in range(repeats):
        rng = random.Random(RANDOM_SEED + repeat)
        pos, neg = positive[:], negative[:]
        rng.shuffle(pos)
        rng.shuffle(neg)
        groups: list[list[int]] = [[] for _ in range(folds)]
        for index, item in enumerate(pos):
            groups[index % folds].append(item)
        for index, item in enumerate(neg):
            groups[index % folds].append(item)
        predicted = [False] * len(scores)
        for test_indices in groups:
            test = set(test_indices)
            train = [index for index in range(len(scores)) if index not in test]
            threshold, _ = _best_threshold(
                [scores[index] for index in train], [truth[index] for index in train]
            )
            for index in test_indices:
                predicted[index] = scores[index] >= threshold
        outcomes.append(_binary_metrics(truth, predicted))
    return {
        "repeats": repeats,
        "folds": folds,
        "seed": RANDOM_SEED,
        "threshold_fit_inside_each_training_fold": True,
        "runs_passing_75_75": sum(item["passed_75_75"] for item in outcomes),
        "median_sensitivity": statistics.median(item["sensitivity"] for item in outcomes),
        "median_specificity": statistics.median(item["specificity"] for item in outcomes),
        "minimum_sensitivity": min(item["sensitivity"] for item in outcomes),
        "minimum_specificity": min(item["specificity"] for item in outcomes),
    }


def _raw_categorical(rows: list[dict[str, Any]], truth: list[bool]) -> dict[str, Any]:
    tp = tn = fp = fn = inconclusive = 0
    for row, expected_positive in zip(rows, truth, strict=True):
        classification = row["selected_candidate_classification"]
        inconclusive += int(classification == "INCONCLUSIVA")
        if expected_positive:
            tp += int(classification == "POSITIVA")
            fn += int(classification != "POSITIVA")
        else:
            tn += int(classification == "NEGATIVA")
            fp += int(classification != "NEGATIVA")
    sensitivity = tp / (tp + fn) if tp + fn else None
    specificity = tn / (tn + fp) if tn + fp else None
    return {
        "tp": tp,
        "tn": tn,
        "fp": fp,
        "fn": fn,
        "sensitivity": sensitivity,
        "specificity": specificity,
        "inconclusive_count": inconclusive,
        "inconclusive_counted_as_error": True,
        "passed_75_75": bool(
            sensitivity is not None
            and specificity is not None
            and sensitivity >= 0.75
            and specificity >= 0.75
        ),
    }


def evaluate_development(
    *,
    bundle_root: Path,
    run_root: Path,
    score_protocol_path: Path,
    evaluation_protocol_path: Path,
    labels_path: Path,
    output_dir: Path,
    allow_protected_development_labels: bool = False,
    expected_case_count: int = 87,
) -> dict[str, Any]:
    protocol, rows = verify_evaluation_protocol(
        bundle_root=bundle_root,
        run_root=run_root,
        score_protocol_path=score_protocol_path,
        evaluation_protocol_path=evaluation_protocol_path,
        expected_case_count=expected_case_count,
    )
    if allow_protected_development_labels is not True:
        raise PipelineError(
            "Abertura dos labels protegidos para a v16 nao foi autorizada explicitamente."
        )
    output = Path(output_dir).resolve()
    if output.exists():
        raise PipelineError("Avaliacao v16 ja existe; sobrescrita recusada.")
    case_ids = [row["case_id"] for row in rows]
    labels, labels_hash = _load_development_labels(labels_path, case_ids)
    truth = [labels[case_id]["label"] == "POSITIVE" for case_id in case_ids]
    if min(sum(truth), len(truth) - sum(truth)) < FOLDS:
        raise PipelineError("Coorte de desenvolvimento v16 invalida.")
    scores = [row["case_score"] for row in rows]
    apparent_threshold, apparent = _best_threshold(scores, truth)
    primary = _loocv(scores, truth)
    repeated = _repeated_nested(scores, truth)
    zero_threshold = _binary_metrics(truth, [score >= 0.0 for score in scores])
    raw = _raw_categorical(rows, truth)
    accuracy_gate = bool(
        primary["sensitivity"] >= protocol["development_gate"]["minimum_loocv_sensitivity"]
        and primary["specificity"] >= protocol["development_gate"]["minimum_loocv_specificity"]
        and repeated["runs_passing_75_75"]
        == protocol["development_gate"]["required_repeated_runs_passing_75_75"]
    )
    full_operational_gate = bool(
        protocol["score_time_gate_passed"]
        and protocol["full_raw_dicom_end_to_end_180_seconds_proven"]
    )
    result = {
        "schema": EVALUATION_SCHEMA,
        "status": (
            "development_accuracy_gate_passed_operational_gate_unproven"
            if accuracy_gate
            else "development_accuracy_gate_not_passed"
        ),
        "case_count": len(rows),
        "positive_count": sum(truth),
        "negative_count": len(truth) - sum(truth),
        "primary_signal": PRIMARY_SIGNAL,
        "apparent_threshold_for_future_calibrator_freeze": apparent_threshold,
        "apparent_metrics": apparent,
        "primary_loocv_metrics": primary,
        "primary_loocv_confidence_intervals": {
            "sensitivity_95": _wilson(primary["tp"], primary["tp"] + primary["fn"]),
            "specificity_95": _wilson(primary["tn"], primary["tn"] + primary["fp"]),
        },
        "repeated_stratified_5fold": repeated,
        "secondary_diagnostics_not_eligible_for_selection": {
            "zero_log_odds_threshold": zero_threshold,
            "selected_candidate_raw_categorical": raw,
        },
        "development_accuracy_gate_passed": accuracy_gate,
        "score_time_gate_180_seconds_passed": protocol["score_time_gate_passed"],
        "full_raw_dicom_end_to_end_180_seconds_proven": False,
        "full_operational_gate_passed": full_operational_gate,
        "goal_75_75_and_full_180_proven": accuracy_gate and full_operational_gate,
        "evaluation_protocol_signature": protocol["protocol_signature"],
        "protected_development_labels_sha256": labels_hash,
        "holdout_opened": False,
        "qualified": False,
        "ground_truth_read": True,
        "metrics_calculated": True,
        "research_only": True,
        "clinical_use_allowed": False,
        "requires_human_review": True,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    staging = output.parent / f"._v16eval_{uuid.uuid4().hex[:8]}"
    staging.mkdir()
    try:
        _write_json_atomic(staging / "evaluation.json", result)
        with (staging / "case_scores.csv").open(
            "w", encoding="utf-8", newline=""
        ) as handle:
            fields = [
                "case_id",
                "label",
                "case_score",
                "selected_candidate_classification",
                "selected_candidate_number",
                "candidate_stack_count",
                "scoring_elapsed_seconds",
                "prediction_sha256",
            ]
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            for row in rows:
                writer.writerow({**row, "label": labels[row["case_id"]]["label"]})
        _publish_directory(staging, output)
        return result
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
