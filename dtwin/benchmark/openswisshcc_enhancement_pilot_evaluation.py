"""Predeclared v22 exact-top5 pilot evaluation, isolated from inference."""
from __future__ import annotations

import json
import shutil
import uuid
from pathlib import Path
from typing import Any

from dtwin.benchmark.metrics import wilson_interval
from dtwin.benchmark.openswisshcc_alignment import _publish_directory, _sha256
from dtwin.benchmark.openswisshcc_candidate_volume_score import (
    PREDICTION_SCHEMA,
    RUN_CONTEXT_SCHEMA,
    SUMMARY_SCHEMA,
)
from dtwin.benchmark.openswisshcc_enhancement_score_preflight import PREFLIGHT_SCHEMA
from dtwin.benchmark.openswisshcc_highdimensional_inference import (
    _atomic_json,
    _canonical_hash,
)
from dtwin.core import PipelineError
from dtwin.medgemma_screening import _write_json_atomic

PROTOCOL_SCHEMA = "argos-openswisshcc-enhancement-top5-pilot-evaluation-protocol-v22"
EVALUATION_SCHEMA = "argos-openswisshcc-enhancement-top5-pilot-evaluation-v22"
LABEL_SCHEMA = "argos-openswisshcc-ground-truth-v1"
EXPECTED_CASE_COUNT = 10
CASE_TIME_GATE_SECONDS = 180.0
TARGET = 0.75
CHOICES = ("POSITIVA", "NEGATIVA", "INCONCLUSIVA")
DECISION_PRIORITY = ("POSITIVA", "INCONCLUSIVA", "NEGATIVA")


def _load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PipelineError(f"JSON invalido na avaliacao piloto v22: {path}.") from exc
    if not isinstance(value, dict):
        raise PipelineError(f"Objeto JSON esperado na avaliacao piloto v22: {path}.")
    return value


def _jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    try:
        for line_number, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError
            rows.append(value)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        number = locals().get("line_number", 0)
        raise PipelineError(f"JSONL invalido na linha {number} da avaliacao piloto v22.") from exc
    return rows


def _refuse_holdout(*paths: Path) -> None:
    if any(
        any("holdout" in part.lower() for part in Path(path).resolve().parts)
        for path in paths
    ):
        raise PipelineError("Avaliacao piloto v22 recusou caminho de holdout.")


def _validate_preflight(path: Path) -> dict[str, Any]:
    value = _load(path)
    case_ids = [str(row.get("case_id", "")) for row in value.get("cases", [])]
    if (
        value.get("schema") != PREFLIGHT_SCHEMA
        or value.get("status") != "passed_pending_explicit_human_review"
        or value.get("case_count") != EXPECTED_CASE_COUNT
        or value.get("candidate_stack_count") != 48
        or len(case_ids) != EXPECTED_CASE_COUNT
        or len(set(case_ids)) != EXPECTED_CASE_COUNT
        or any(not case_id.startswith("anon-") for case_id in case_ids)
        or value.get("human_review_signed") is not False
        or value.get("inference_authorized") is not False
        or value.get("inference_executed") is not False
        or value.get("labels_read") is not False
        or value.get("lesion_masks_read") is not False
        or value.get("holdout_opened") is not False
        or value.get("case_time_gate_seconds") != CASE_TIME_GATE_SECONDS
    ):
        raise PipelineError("Preflight v22 invalido para congelar avaliacao piloto.")
    value["_case_ids"] = case_ids
    return value


def freeze_enhancement_pilot_evaluation_protocol(
    *, preflight_path: Path, intended_score_root: Path, output_path: Path
) -> dict[str, Any]:
    """Freeze all decision rules while the intended prediction root is absent."""

    preflight_path = Path(preflight_path).resolve()
    intended_score_root = Path(intended_score_root).resolve()
    output_path = Path(output_path).resolve()
    _refuse_holdout(preflight_path, intended_score_root, output_path)
    if intended_score_root.exists():
        raise PipelineError("Predicoes v22 ja existem; congelamento tardio recusado.")
    preflight = _validate_preflight(preflight_path)
    base: dict[str, Any] = {
        "schema": PROTOCOL_SCHEMA,
        "status": "frozen_before_human_review_and_predictions",
        "source_preflight_sha256": _sha256(preflight_path),
        "gallery_signature": preflight["source_hashes"]["gallery_signature"],
        "case_ids": preflight["_case_ids"],
        "case_count": EXPECTED_CASE_COUNT,
        "candidate_stack_count": preflight["candidate_stack_count"],
        "intended_score_run_id": intended_score_root.name,
        "prediction_schema": PREDICTION_SCHEMA,
        "case_decision_rule": {
            "priority": list(DECISION_PRIORITY),
            "positive": "at_least_one_candidate_classification_equals_POSITIVA",
            "inconclusive": "no_positive_and_at_least_one_candidate_classification_equals_INCONCLUSIVA",
            "negative": "all_candidate_classifications_equal_NEGATIVA",
            "score_threshold_calibration": "none",
        },
        "primary_metrics": {
            "positive_ground_truth": "POSITIVE",
            "negative_ground_truth": "NEGATIVE",
            "inconclusive_on_positive": "count_as_false_negative",
            "inconclusive_on_negative": "count_as_false_positive",
            "sensitivity_target": TARGET,
            "specificity_target": TARGET,
            "confidence_intervals": "wilson_95_percent",
        },
        "time_gate": {
            "scope": "precomputed_exact_top5_candidate_scoring_per_case",
            "maximum_seconds": CASE_TIME_GATE_SECONDS,
            "every_case_must_pass": True,
            "raw_dicom_end_to_end_proven_by_this_pilot": False,
        },
        "pilot_only": True,
        "pilot_can_qualify_final_system": False,
        "predictions_present_at_freeze": False,
        "labels_read": False,
        "lesion_masks_read": False,
        "holdout_opened": False,
        "inference_executed": False,
        "research_only": True,
        "clinical_use_allowed": False,
        "requires_human_review": True,
    }
    protocol = dict(base)
    protocol["protocol_signature"] = _canonical_hash(base)
    if output_path.exists():
        existing = _load(output_path)
        if existing != protocol:
            raise PipelineError("Protocolo de avaliacao v22 existente diverge.")
        return existing
    output_path.parent.mkdir(parents=True, exist_ok=True)
    _atomic_json(output_path, protocol)
    return protocol


def _load_protocol(path: Path) -> dict[str, Any]:
    protocol = _load(path)
    unsigned = dict(protocol)
    signature = unsigned.pop("protocol_signature", None)
    if (
        signature != _canonical_hash(unsigned)
        or protocol.get("schema") != PROTOCOL_SCHEMA
        or protocol.get("status") != "frozen_before_human_review_and_predictions"
        or protocol.get("case_count") != EXPECTED_CASE_COUNT
        or protocol.get("case_decision_rule", {}).get("priority") != list(DECISION_PRIORITY)
        or protocol.get("case_decision_rule", {}).get("score_threshold_calibration") != "none"
        or protocol.get("primary_metrics", {}).get("inconclusive_on_positive") != "count_as_false_negative"
        or protocol.get("primary_metrics", {}).get("inconclusive_on_negative") != "count_as_false_positive"
        or protocol.get("time_gate", {}).get("maximum_seconds") != CASE_TIME_GATE_SECONDS
        or protocol.get("pilot_can_qualify_final_system") is not False
        or protocol.get("labels_read") is not False
        or protocol.get("holdout_opened") is not False
    ):
        raise PipelineError("Protocolo de avaliacao piloto v22 invalido ou adulterado.")
    return protocol


def _case_decision(candidate_results: list[dict[str, Any]]) -> str:
    values = [str(row.get("classification", "")) for row in candidate_results]
    if not values or any(value not in CHOICES for value in values):
        raise PipelineError("Classificacoes candidatas invalidas na avaliacao v22.")
    if "POSITIVA" in values:
        return "POSITIVA"
    if "INCONCLUSIVA" in values:
        return "INCONCLUSIVA"
    return "NEGATIVA"


def evaluate_enhancement_pilot(
    *,
    protocol_path: Path,
    preflight_path: Path,
    score_root: Path,
    labels_path: Path,
    output_root: Path,
) -> dict[str, Any]:
    """Evaluate only after a complete, bundle-bound score run exists."""

    protocol_path = Path(protocol_path).resolve()
    preflight_path = Path(preflight_path).resolve()
    score_root = Path(score_root).resolve()
    labels_path = Path(labels_path).resolve()
    output_root = Path(output_root).resolve()
    _refuse_holdout(protocol_path, preflight_path, score_root, labels_path, output_root)
    if output_root.exists():
        raise PipelineError("Saida da avaliacao piloto v22 ja existe.")
    protocol = _load_protocol(protocol_path)
    preflight = _validate_preflight(preflight_path)
    if (
        protocol["source_preflight_sha256"] != _sha256(preflight_path)
        or protocol["gallery_signature"] != preflight["source_hashes"]["gallery_signature"]
        or protocol["case_ids"] != preflight["_case_ids"]
        or protocol["intended_score_run_id"] != score_root.name
    ):
        raise PipelineError("Protocolo, preflight e run de scores v22 divergiram.")

    summary_path = score_root / "summary.json"
    context_path = score_root / "run_context.json"
    summary = _load(summary_path)
    context = _load(context_path)
    records = summary.get("predictions")
    if (
        summary.get("schema") != SUMMARY_SCHEMA
        or summary.get("status") != "complete"
        or summary.get("case_count") != EXPECTED_CASE_COUNT
        or summary.get("completed_case_count") != EXPECTED_CASE_COUNT
        or summary.get("pending_case_count") != 0
        or summary.get("ground_truth_read") is not False
        or summary.get("holdout_opened") is not False
        or summary.get("metrics_calculated") is not False
        or not isinstance(records, list)
        or len(records) != EXPECTED_CASE_COUNT
        or context.get("schema") != RUN_CONTEXT_SCHEMA
        or context.get("case_ids") != protocol["case_ids"]
        or context.get("bundle_cohort_sha256") != preflight["source_hashes"]["bundle_cohort_sha256"]
        or context.get("bundle_gallery_signature") != protocol["gallery_signature"]
        or context.get("ground_truth_read") is not False
        or context.get("holdout_opened") is not False
        or context.get("metrics_calculated") is not False
    ):
        raise PipelineError("Run de scores v22 incompleto, divergente ou inseguro.")

    predictions: dict[str, dict[str, Any]] = {}
    total_candidate_requests = 0
    for record in records:
        case_id = str(record.get("case_id", ""))
        path = score_root / "predictions" / f"{case_id}.json"
        if (
            case_id in predictions
            or case_id not in protocol["case_ids"]
            or not path.is_file()
            or _sha256(path) != record.get("prediction_sha256")
        ):
            raise PipelineError("Predicao v22 ausente, duplicada ou adulterada.")
        value = _load(path)
        if (
            value.get("schema") != PREDICTION_SCHEMA
            or value.get("status") != "technical_passed"
            or value.get("case_id") != case_id
            or value.get("time_gate_passed") is not True
            or float(value.get("scoring_elapsed_seconds", CASE_TIME_GATE_SECONDS + 1)) > CASE_TIME_GATE_SECONDS
            or value.get("ground_truth_read") is not False
            or value.get("holdout_opened") is not False
            or value.get("metrics_calculated") is not False
            or not isinstance(value.get("candidate_results"), list)
            or len(value["candidate_results"]) != int(value.get("candidate_stack_count", -1))
        ):
            raise PipelineError("Predicao v22 violou contrato ou gate temporal.")
        predictions[case_id] = value
        total_candidate_requests += len(value["candidate_results"])
    if set(predictions) != set(protocol["case_ids"]):
        raise PipelineError("Predicoes v22 nao cobrem exatamente o piloto.")
    if (
        total_candidate_requests != preflight["candidate_stack_count"]
        or int(summary.get("candidate_request_count", -1)) != total_candidate_requests
    ):
        raise PipelineError("Quantidade de chamadas candidatas v22 divergiu do exact-top5.")

    labels: dict[str, str] = {}
    for row in _jsonl(labels_path):
        case_id = str(row.get("case_id", ""))
        label = str(row.get("label", ""))
        if row.get("schema") != LABEL_SCHEMA or label not in {"POSITIVE", "NEGATIVE"} or case_id in labels:
            raise PipelineError("Labels publicos invalidos na avaliacao piloto v22.")
        labels[case_id] = label
    if not set(protocol["case_ids"]) <= set(labels):
        raise PipelineError("Labels publicos nao cobrem integralmente o piloto v22.")

    tp = tn = fp = fn = inconclusive = 0
    rows = []
    for case_id in protocol["case_ids"]:
        truth = labels[case_id]
        prediction = predictions[case_id]
        decision = _case_decision(prediction["candidate_results"])
        inconclusive += int(decision == "INCONCLUSIVA")
        if truth == "POSITIVE":
            if decision == "POSITIVA":
                tp += 1
            else:
                fn += 1
        else:
            if decision == "NEGATIVA":
                tn += 1
            else:
                fp += 1
        rows.append(
            {
                "case_id": case_id,
                "label": truth,
                "decision": decision,
                "candidate_classifications": [row["classification"] for row in prediction["candidate_results"]],
                "scoring_elapsed_seconds": float(prediction["scoring_elapsed_seconds"]),
            }
        )
    sensitivity = tp / (tp + fn) if tp + fn else 0.0
    specificity = tn / (tn + fp) if tn + fp else 0.0
    max_seconds = max(row["scoring_elapsed_seconds"] for row in rows)
    gate = sensitivity >= TARGET and specificity >= TARGET and max_seconds <= CASE_TIME_GATE_SECONDS
    result: dict[str, Any] = {
        "schema": EVALUATION_SCHEMA,
        "status": "development_pilot_evaluated",
        "protocol_signature": protocol["protocol_signature"],
        "case_count": EXPECTED_CASE_COUNT,
        "confusion_matrix": {"tp": tp, "tn": tn, "fp": fp, "fn": fn},
        "sensitivity": sensitivity,
        "specificity": specificity,
        "sensitivity_95_wilson": wilson_interval(tp, tp + fn),
        "specificity_95_wilson": wilson_interval(tn, tn + fp),
        "inconclusive_count": inconclusive,
        "inconclusives_counted_as_errors": True,
        "maximum_scoring_seconds": max_seconds,
        "all_scoring_time_gates_passed": max_seconds <= CASE_TIME_GATE_SECONDS,
        "pilot_75_75_180_gate_passed": gate,
        "pilot_only": True,
        "qualified": False,
        "final_system_qualification_claimed": False,
        "raw_dicom_end_to_end_180_seconds_proven": False,
        "rows": rows,
        "source_hashes": {
            "protocol_sha256": _sha256(protocol_path),
            "preflight_sha256": _sha256(preflight_path),
            "score_summary_sha256": _sha256(summary_path),
            "run_context_sha256": _sha256(context_path),
            "development_labels_sha256": _sha256(labels_path),
        },
        "labels_read_only_after_complete_predictions": True,
        "lesion_masks_read": False,
        "holdout_opened": False,
        "research_only": True,
        "clinical_use_allowed": False,
        "requires_human_review": True,
    }
    output_root.parent.mkdir(parents=True, exist_ok=True)
    staging = output_root.parent / f"._v22pilot_eval_{uuid.uuid4().hex[:8]}"
    staging.mkdir()
    try:
        _write_json_atomic(staging / "evaluation.json", result)
        _publish_directory(staging, output_root)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return result


__all__ = [
    "EVALUATION_SCHEMA",
    "PROTOCOL_SCHEMA",
    "evaluate_enhancement_pilot",
    "freeze_enhancement_pilot_evaluation_protocol",
]
