"""Avaliação protegida do scorer OpenSwissHCC v19 atlas + RAG."""
from __future__ import annotations

import csv
import json
import math
import statistics
import uuid
from pathlib import Path
from typing import Any

from dtwin.benchmark.openswisshcc_alignment import _publish_directory, _sha256
from dtwin.benchmark.openswisshcc_axial_atlas_evaluation import (
    _canonical_sha,
    _contains_forbidden_key,
    _finite,
    _loocv,
    _raw_metrics,
    _roc_auc,
)
from dtwin.benchmark.openswisshcc_axial_atlas_rag_score import (
    PREDICTION_SCHEMA,
    SUMMARY_SCHEMA,
    _load_protocol as _load_score_protocol,
    score_log_odds,
)
from dtwin.benchmark.openswisshcc_axial_atlas_score import CASE_TIME_GATE_SECONDS
from dtwin.benchmark.openswisshcc_lesion_localizer_evaluation import (
    _load_development_labels,
)
from dtwin.benchmark.openswisshcc_localizer_roi_evaluation import _wilson
from dtwin.benchmark.openswisshcc_volumetric_evaluation import (
    _best_threshold,
)
from dtwin.core import PipelineError
from dtwin.medgemma_screening import _write_json_atomic


PROTOCOL_SCHEMA = "argos-openswisshcc-v19-atlas-rag-evaluation-protocol-v1"
EVALUATION_SCHEMA = "argos-openswisshcc-v19-atlas-rag-development-evaluation-v1"


def _load_json(path: Path, description: str) -> dict[str, Any]:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PipelineError(f"{description} ausente ou inválido.") from exc
    if not isinstance(value, dict):
        raise PipelineError(f"{description} deve ser objeto JSON.")
    return value


def validate_blind_scores(
    *, score_root: Path, score_protocol_path: Path, expected_case_count: int = 87
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    root = Path(score_root).resolve()
    protocol = _load_score_protocol(Path(score_protocol_path).resolve())
    summary_path = root / "summary.json"
    summary = _load_json(summary_path, "Resumo cego v19")
    if (
        summary.get("schema_version") != SUMMARY_SCHEMA
        or summary.get("status") != "complete"
        or summary.get("case_count") != expected_case_count
        or summary.get("completed_case_count") != expected_case_count
        or summary.get("pending_case_count") != 0
        or summary.get("request_count") != expected_case_count
        or summary.get("protocol_signature") != protocol["protocol_signature"]
        or summary.get("rag_context_sha256")
        != protocol["rag_fingerprint"]["context_sha256"]
        or summary.get("ground_truth_read_during_inference") is not False
        or summary.get("lesion_mask_read_during_inference") is not False
        or summary.get("metrics_calculated_during_inference") is not False
        or summary.get("holdout_opened") is not False
        or summary.get("accuracy_claimed") is not False
        or _contains_forbidden_key(summary)
    ):
        raise PipelineError("Resumo cego v19 viola o protocolo protegido.")
    records = summary.get("predictions")
    if not isinstance(records, list) or len(records) != expected_case_count:
        raise PipelineError("Resumo cego v19 não contém todas as predições.")
    case_ids = [str(item.get("case_id", "")) for item in records]
    if case_ids != protocol.get("case_ids") or len(set(case_ids)) != expected_case_count:
        raise PipelineError("Ordem ou IDs dos scores cegos v19 divergem.")

    validated: list[dict[str, Any]] = []
    prediction_dir = root / "predictions"
    for record in records:
        case_id = str(record["case_id"])
        path = (prediction_dir / f"{case_id}.json").resolve()
        if not path.is_relative_to(prediction_dir.resolve()) or not path.is_file():
            raise PipelineError(f"Predição v19 ausente: {case_id}.")
        if _sha256(path) != record.get("prediction_sha256"):
            raise PipelineError(f"Hash da predição v19 diverge: {case_id}.")
        prediction = _load_json(path, f"Predição v19 {case_id}")
        probabilities = prediction.get("choice_probabilities")
        if (
            prediction.get("schema_version") != PREDICTION_SCHEMA
            or prediction.get("status") != "technical_passed"
            or prediction.get("case_id") != case_id
            or prediction.get("protocol_signature") != protocol["protocol_signature"]
            or prediction.get("rag_context_sha256")
            != protocol["rag_fingerprint"]["context_sha256"]
            or prediction.get("rag_addendum_sha256") != protocol["rag_addendum_sha256"]
            or prediction.get("classification")
            not in {"POSITIVA", "NEGATIVA", "INCONCLUSIVA"}
            or prediction.get("ground_truth_read_during_inference") is not False
            or prediction.get("lesion_mask_read_during_inference") is not False
            or prediction.get("metrics_calculated_during_inference") is not False
            or prediction.get("holdout_opened") is not False
            or prediction.get("time_gate_passed") is not True
            or prediction.get("research_only") is not True
            or prediction.get("clinical_use_allowed") is not False
            or not isinstance(probabilities, dict)
            or set(probabilities) != {"POSITIVA", "NEGATIVA", "INCONCLUSIVA"}
            or _contains_forbidden_key(prediction)
        ):
            raise PipelineError(f"Predição v19 inválida ou contaminada: {case_id}.")
        values = {key: _finite(value) for key, value in probabilities.items()}
        if any(value < 0 or value > 1 for value in values.values()) or not math.isclose(
            sum(values.values()), 1.0, rel_tol=0, abs_tol=1e-6
        ):
            raise PipelineError(f"Probabilidades v19 inválidas: {case_id}.")
        maximum = max(values.values())
        winners = [key for key, value in values.items() if value == maximum]
        if (
            prediction["classification"] not in winners
            or bool(prediction.get("tie_detected")) != (len(winners) > 1)
            or record.get("classification") != prediction["classification"]
        ):
            raise PipelineError(f"Argmax v19 diverge: {case_id}.")
        score = score_log_odds(values)
        if not math.isclose(
            score,
            _finite(prediction.get("log_odds_positive_vs_negative")),
            rel_tol=0,
            abs_tol=1e-12,
        ) or not math.isclose(
            score,
            _finite(record.get("log_odds_positive_vs_negative")),
            rel_tol=0,
            abs_tol=1e-12,
        ):
            raise PipelineError(f"Log-odds v19 diverge: {case_id}.")
        elapsed = _finite(prediction.get("request_elapsed_seconds"))
        if elapsed < 0 or elapsed > CASE_TIME_GATE_SECONDS or not math.isclose(
            elapsed,
            _finite(record.get("request_elapsed_seconds")),
            rel_tol=0,
            abs_tol=1e-6,
        ):
            raise PipelineError(f"Tempo v19 inválido: {case_id}.")
        validated.append(
            {
                "case_id": case_id,
                "score": score,
                "classification": prediction["classification"],
                "request_elapsed_seconds": elapsed,
                "prediction_sha256": record["prediction_sha256"],
            }
        )
    timings = summary.get("request_timing_seconds", {})
    observed = [row["request_elapsed_seconds"] for row in validated]
    if (
        timings.get("all_within_180") is not True
        or not math.isclose(_finite(timings.get("minimum")), min(observed), abs_tol=1e-9)
        or not math.isclose(_finite(timings.get("median")), statistics.median(observed), abs_tol=1e-9)
        or not math.isclose(_finite(timings.get("mean")), statistics.fmean(observed), abs_tol=1e-9)
        or not math.isclose(_finite(timings.get("maximum")), max(observed), abs_tol=1e-9)
    ):
        raise PipelineError("Resumo temporal v19 diverge das predições.")
    return summary, validated


def freeze_evaluation_protocol(
    *,
    score_root: Path,
    score_protocol_path: Path,
    output_path: Path,
    expected_case_count: int = 87,
) -> dict[str, Any]:
    summary, rows = validate_blind_scores(
        score_root=score_root,
        score_protocol_path=score_protocol_path,
        expected_case_count=expected_case_count,
    )
    vector = [[row["case_id"], row["score"], row["prediction_sha256"]] for row in rows]
    base = {
        "schema_version": PROTOCOL_SCHEMA,
        "status": "frozen_before_protected_development_labels",
        "case_count": expected_case_count,
        "case_ids": [row["case_id"] for row in rows],
        "score_protocol_signature": summary["protocol_signature"],
        "rag_context_sha256": summary["rag_context_sha256"],
        "score_summary_sha256": _sha256(Path(score_root).resolve() / "summary.json"),
        "blind_score_vector_sha256": _canonical_sha(vector),
        "primary_signal": "rag_atlas_log_odds_positive_vs_negative",
        "signal_direction": "higher_is_more_suspicious",
        "primary_estimator": "leave_one_out_threshold_fit_on_n_minus_1_only",
        "threshold_selection": "maximize_minimum_sensitivity_specificity_then_balanced_accuracy_on_training_only",
        "secondary_diagnostics": [
            "apparent_roc_auc",
            "apparent_threshold_for_future_freeze_only",
            "raw_argmax_with_inconclusive_counted_as_error",
        ],
        "development_gate": {
            "minimum_loocv_sensitivity": 0.75,
            "minimum_loocv_specificity": 0.75,
            "maximum_precomputed_atlas_scoring_seconds": CASE_TIME_GATE_SECONDS,
        },
        "confidence_intervals": "wilson_95_percent_on_loocv_confusion_matrix",
        "observed_maximum_precomputed_scoring_seconds": summary["request_timing_seconds"]["maximum"],
        "end_to_end_180_seconds_proven": False,
        "ground_truth_read": False,
        "metrics_calculated": False,
        "holdout_opened": False,
        "research_only": True,
        "clinical_use_allowed": False,
        "requires_human_review": True,
    }
    protocol = {**base, "protocol_signature": _canonical_sha(base)}
    output = Path(output_path).resolve()
    if output.exists():
        if _load_json(output, "Protocolo de avaliação v19") != protocol:
            raise PipelineError("Protocolo de avaliação v19 existente diverge.")
        return protocol
    output.parent.mkdir(parents=True, exist_ok=True)
    _write_json_atomic(output, protocol)
    return protocol


def verify_evaluation_protocol(
    *,
    score_root: Path,
    score_protocol_path: Path,
    protocol_path: Path,
    expected_case_count: int = 87,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    summary, rows = validate_blind_scores(
        score_root=score_root,
        score_protocol_path=score_protocol_path,
        expected_case_count=expected_case_count,
    )
    protocol = _load_json(protocol_path, "Protocolo de avaliação v19")
    signature = protocol.pop("protocol_signature", None)
    if signature != _canonical_sha(protocol):
        raise PipelineError("Assinatura do protocolo de avaliação v19 diverge.")
    protocol["protocol_signature"] = signature
    vector = [[row["case_id"], row["score"], row["prediction_sha256"]] for row in rows]
    if (
        protocol.get("schema_version") != PROTOCOL_SCHEMA
        or protocol.get("status") != "frozen_before_protected_development_labels"
        or protocol.get("case_ids") != [row["case_id"] for row in rows]
        or protocol.get("score_protocol_signature") != summary["protocol_signature"]
        or protocol.get("rag_context_sha256") != summary["rag_context_sha256"]
        or protocol.get("score_summary_sha256")
        != _sha256(Path(score_root).resolve() / "summary.json")
        or protocol.get("blind_score_vector_sha256") != _canonical_sha(vector)
        or protocol.get("ground_truth_read") is not False
        or protocol.get("metrics_calculated") is not False
        or protocol.get("holdout_opened") is not False
    ):
        raise PipelineError("Protocolo de avaliação v19 não corresponde aos scores cegos.")
    return protocol, rows


def evaluate_development(
    *,
    score_root: Path,
    score_protocol_path: Path,
    protocol_path: Path,
    labels_path: Path,
    output_dir: Path,
    allow_protected_development_labels: bool = False,
    expected_case_count: int = 87,
) -> dict[str, Any]:
    protocol, rows = verify_evaluation_protocol(
        score_root=score_root,
        score_protocol_path=score_protocol_path,
        protocol_path=protocol_path,
        expected_case_count=expected_case_count,
    )
    if allow_protected_development_labels is not True:
        raise PipelineError("Abertura dos labels de desenvolvimento v19 não foi autorizada.")
    labels_path = Path(labels_path).resolve()
    if labels_path.name != "development_labels.jsonl" or any(
        "holdout" in part.lower() for part in labels_path.parts
    ):
        raise PipelineError("Avaliador v19 aceita somente development_labels.jsonl, nunca holdout.")
    output = Path(output_dir).resolve()
    if output.exists():
        raise PipelineError("Avaliação de desenvolvimento v19 já existe.")
    case_ids = [row["case_id"] for row in rows]
    labels, labels_hash = _load_development_labels(labels_path, case_ids)
    truth = [labels[case_id]["label"] == "POSITIVE" for case_id in case_ids]
    if not any(truth) or all(truth):
        raise PipelineError("Coorte v19 deve conter positivos e negativos.")
    scores = [row["score"] for row in rows]
    apparent_threshold, apparent = _best_threshold(scores, truth)
    loocv = _loocv(scores, truth)
    raw = _raw_metrics(rows, truth)
    gate = bool(
        loocv["sensitivity"] >= protocol["development_gate"]["minimum_loocv_sensitivity"]
        and loocv["specificity"] >= protocol["development_gate"]["minimum_loocv_specificity"]
        and protocol["observed_maximum_precomputed_scoring_seconds"]
        <= protocol["development_gate"]["maximum_precomputed_atlas_scoring_seconds"]
    )
    result = {
        "schema_version": EVALUATION_SCHEMA,
        "status": "development_reader_gate_passed" if gate else "development_reader_gate_failed",
        "case_count": len(rows),
        "positive_count": sum(truth),
        "negative_count": len(truth) - sum(truth),
        "primary_signal": protocol["primary_signal"],
        "primary_loocv_metrics": {key: value for key, value in loocv.items() if key != "thresholds"},
        "primary_loocv_threshold_summary": {
            "minimum": min(loocv["thresholds"]),
            "median": statistics.median(loocv["thresholds"]),
            "maximum": max(loocv["thresholds"]),
        },
        "primary_loocv_confidence_intervals": {
            "sensitivity_95": _wilson(loocv["tp"], loocv["tp"] + loocv["fn"]),
            "specificity_95": _wilson(loocv["tn"], loocv["tn"] + loocv["fp"]),
        },
        "secondary_diagnostics_not_eligible_to_replace_primary": {
            "apparent_roc_auc": _roc_auc(scores, truth),
            "apparent_threshold_for_future_freeze": apparent_threshold,
            "apparent_metrics": apparent,
            "raw_argmax": raw,
        },
        "development_reader_gate_passed": gate,
        "precomputed_atlas_scoring_time_gate_passed": bool(
            protocol["observed_maximum_precomputed_scoring_seconds"] <= CASE_TIME_GATE_SECONDS
        ),
        "observed_maximum_precomputed_scoring_seconds": protocol["observed_maximum_precomputed_scoring_seconds"],
        "end_to_end_180_seconds_proven": False,
        "protocol_signature": protocol["protocol_signature"],
        "score_summary_sha256": protocol["score_summary_sha256"],
        "rag_context_sha256": protocol["rag_context_sha256"],
        "protected_development_labels_sha256": labels_hash,
        "ground_truth_read": True,
        "metrics_calculated": True,
        "holdout_opened": False,
        "qualified": False,
        "research_only": True,
        "clinical_use_allowed": False,
        "requires_human_review": True,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    staging = output.parent / f"._v19eval_{uuid.uuid4().hex[:8]}"
    staging.mkdir()
    try:
        _write_json_atomic(staging / "evaluation.json", result)
        with (staging / "case_scores.csv").open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=["case_id", "label", "score", "raw_classification", "request_elapsed_seconds"],
            )
            writer.writeheader()
            for row in rows:
                writer.writerow(
                    {
                        "case_id": row["case_id"],
                        "label": labels[row["case_id"]]["label"],
                        "score": row["score"],
                        "raw_classification": row["classification"],
                        "request_elapsed_seconds": row["request_elapsed_seconds"],
                    }
                )
        _publish_directory(staging, output)
    finally:
        if staging.exists():
            import shutil

            shutil.rmtree(staging)
    return result

