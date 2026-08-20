"""Avaliação protegida do scorer em blocos OpenSwissHCC v18."""
from __future__ import annotations

import csv
import json
import math
import shutil
import statistics
import uuid
from pathlib import Path
from typing import Any

from dtwin.benchmark.openswisshcc_alignment import _publish_directory, _sha256
from dtwin.benchmark.openswisshcc_axial_atlas_chunk_score import (
    CASE_TIME_GATE_SECONDS,
    PREDICTION_SCHEMA,
    SUMMARY_SCHEMA,
    _load_protocol,
    partition_frame_indices,
)
from dtwin.benchmark.openswisshcc_axial_atlas_evaluation import (
    _loocv,
    _raw_metrics,
    _roc_auc,
)
from dtwin.benchmark.openswisshcc_axial_atlas_score import score_log_odds
from dtwin.benchmark.openswisshcc_lesion_localizer_evaluation import (
    _load_development_labels,
)
from dtwin.benchmark.openswisshcc_localizer_roi_evaluation import _wilson
from dtwin.benchmark.openswisshcc_volumetric_evaluation import _best_threshold
from dtwin.core import PipelineError
from dtwin.medgemma_screening import _write_json_atomic

EVALUATION_SCHEMA = "argos-openswisshcc-v18-atlas-chunk-development-evaluation-v1"


def _json(path: Path, description: str) -> dict[str, Any]:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PipelineError(f"{description} ausente ou inválido.") from exc
    if not isinstance(value, dict):
        raise PipelineError(f"{description} deve ser objeto JSON.")
    return value


def _finite(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise PipelineError("Valor numérico v18 inválido.")
    result = float(value)
    if not math.isfinite(result):
        raise PipelineError("Valor v18 deve ser finito.")
    return result


def validate_chunk_scores(
    *, score_root: Path, protocol_path: Path, expected_case_count: int = 87
) -> tuple[dict, dict, list[dict]]:
    root = Path(score_root).resolve()
    protocol = _load_protocol(protocol_path)
    summary_path = root / "summary.json"
    summary = _json(summary_path, "Resumo v18")
    if (
        summary.get("schema_version") != SUMMARY_SCHEMA
        or summary.get("status") != "complete"
        or summary.get("case_count") != expected_case_count
        or summary.get("completed_case_count") != expected_case_count
        or summary.get("pending_case_count") != 0
        or summary.get("protocol_signature") != protocol["protocol_signature"]
        or summary.get("ground_truth_read_during_inference") is not False
        or summary.get("metrics_calculated_during_inference") is not False
        or summary.get("holdout_opened") is not False
    ):
        raise PipelineError("Resumo v18 incompleto ou contaminado.")
    records = summary.get("predictions")
    if not isinstance(records, list) or len(records) != expected_case_count:
        raise PipelineError("Resumo v18 não contém todas as predições.")
    case_ids = [str(record.get("case_id", "")) for record in records]
    if case_ids != protocol["case_ids"] or len(set(case_ids)) != expected_case_count:
        raise PipelineError("IDs v18 duplicados ou fora da ordem congelada.")
    rows = []
    total_requests = 0
    prediction_dir = root / "predictions"
    for record in records:
        case_id = str(record["case_id"])
        path = (prediction_dir / f"{case_id}.json").resolve()
        if not path.is_relative_to(prediction_dir.resolve()) or not path.is_file():
            raise PipelineError(f"Predição v18 ausente: {case_id}.")
        if _sha256(path) != record.get("prediction_sha256"):
            raise PipelineError(f"Hash v18 diverge: {case_id}.")
        prediction = _json(path, f"Predição v18 {case_id}")
        frame_count = prediction.get("frame_count")
        expected_chunks = partition_frame_indices(frame_count)
        chunks = prediction.get("chunks")
        if (
            prediction.get("schema_version") != PREDICTION_SCHEMA
            or prediction.get("status") != "technical_passed"
            or prediction.get("case_id") != case_id
            or prediction.get("protocol_signature") != protocol["protocol_signature"]
            or prediction.get("holdout_opened") is not False
            or prediction.get("ground_truth_read_during_inference") is not False
            or prediction.get("metrics_calculated_during_inference") is not False
            or prediction.get("time_gate_passed") is not True
            or prediction.get("aggregation") != protocol["aggregation"]
            or prediction.get("represented_frame_numbers") != list(range(1, frame_count + 1))
            or not isinstance(chunks, list)
            or len(chunks) != len(expected_chunks)
        ):
            raise PipelineError(f"Predição v18 inválida ou contaminada: {case_id}.")
        validated_chunks = []
        for number, (chunk, expected_indices) in enumerate(zip(chunks, expected_chunks, strict=True), 1):
            probabilities = chunk.get("choice_probabilities")
            if (
                chunk.get("chunk_number") != number
                or chunk.get("chunk_count") != len(chunks)
                or chunk.get("frame_numbers") != [index + 1 for index in expected_indices]
                or not isinstance(probabilities, dict)
                or set(probabilities) != {"POSITIVA", "NEGATIVA", "INCONCLUSIVA"}
            ):
                raise PipelineError(f"Bloco v18 inválido: {case_id}/{number}.")
            values = {key: _finite(value) for key, value in probabilities.items()}
            if any(value < 0 or value > 1 for value in values.values()) or not math.isclose(sum(values.values()), 1.0, rel_tol=0, abs_tol=1e-6):
                raise PipelineError(f"Probabilidades v18 inválidas: {case_id}/{number}.")
            maximum = max(values.values())
            winners = [key for key in ("POSITIVA", "NEGATIVA", "INCONCLUSIVA") if values[key] == maximum]
            if chunk.get("classification") != winners[0] or chunk.get("tie_detected") is not (len(winners) > 1):
                raise PipelineError(f"Argmax v18 diverge: {case_id}/{number}.")
            calculated = score_log_odds(values)
            if not math.isclose(calculated, _finite(chunk.get("log_odds_positive_vs_negative")), rel_tol=0, abs_tol=1e-12):
                raise PipelineError(f"Log-odds v18 diverge: {case_id}/{number}.")
            validated_chunks.append((calculated, number, chunk["classification"]))
        selected = max(validated_chunks, key=lambda item: (item[0], -item[1]))
        if (
            prediction.get("selected_chunk_number") != selected[1]
            or prediction.get("classification") != selected[2]
            or record.get("classification") != selected[2]
            or not math.isclose(_finite(prediction.get("log_odds_positive_vs_negative")), selected[0], rel_tol=0, abs_tol=1e-12)
            or not math.isclose(_finite(record.get("log_odds_positive_vs_negative")), selected[0], rel_tol=0, abs_tol=1e-12)
        ):
            raise PipelineError(f"Agregação v18 diverge: {case_id}.")
        elapsed = _finite(prediction.get("case_elapsed_seconds"))
        if elapsed < 0 or elapsed > CASE_TIME_GATE_SECONDS or not math.isclose(elapsed, _finite(record.get("case_elapsed_seconds")), rel_tol=0, abs_tol=1e-6):
            raise PipelineError(f"Tempo v18 inválido: {case_id}.")
        total_requests += len(chunks)
        rows.append({"case_id": case_id, "score": selected[0], "classification": selected[2], "case_elapsed_seconds": elapsed, "chunk_count": len(chunks), "prediction_sha256": record["prediction_sha256"]})
    if summary.get("request_count") != total_requests:
        raise PipelineError("Contagem de requisições v18 diverge.")
    timings = summary.get("case_timing_seconds")
    elapsed_values = [row["case_elapsed_seconds"] for row in rows]
    if not isinstance(timings, dict) or timings.get("all_within_180") is not True or not math.isclose(_finite(timings.get("maximum")), max(elapsed_values), abs_tol=1e-9):
        raise PipelineError("Resumo temporal v18 diverge.")
    return protocol, summary, rows


def evaluate_chunk_development(
    *,
    score_root: Path,
    protocol_path: Path,
    labels_path: Path,
    output_dir: Path,
    allow_protected_development_labels: bool = False,
    expected_case_count: int = 87,
) -> dict:
    protocol, summary, rows = validate_chunk_scores(score_root=score_root, protocol_path=protocol_path, expected_case_count=expected_case_count)
    if allow_protected_development_labels is not True:
        raise PipelineError("Abertura dos labels para avaliação v18 não foi autorizada.")
    labels_path = Path(labels_path).resolve()
    if labels_path.name != "development_labels.jsonl" or labels_path.parent.name != "protected_ground_truth" or "holdout" in str(labels_path).lower():
        raise PipelineError("Avaliador v18 aceita somente labels protegidos de desenvolvimento.")
    output = Path(output_dir).resolve()
    if output.exists():
        raise PipelineError("Avaliação v18 já existe.")
    case_ids = [row["case_id"] for row in rows]
    labels, labels_hash = _load_development_labels(labels_path, case_ids)
    truth = [labels[case_id]["label"] == "POSITIVE" for case_id in case_ids]
    scores = [row["score"] for row in rows]
    loocv = _loocv(scores, truth)
    apparent_threshold, apparent = _best_threshold(scores, truth)
    raw = _raw_metrics(rows, truth)
    gate = bool(loocv["sensitivity"] >= protocol["evaluation"]["minimum_sensitivity"] and loocv["specificity"] >= protocol["evaluation"]["minimum_specificity"] and summary["case_timing_seconds"]["maximum"] <= CASE_TIME_GATE_SECONDS)
    result = {
        "schema_version": EVALUATION_SCHEMA,
        "status": "development_reader_gate_passed" if gate else "development_reader_gate_failed",
        "case_count": len(rows),
        "positive_count": sum(truth),
        "negative_count": len(truth) - sum(truth),
        "primary_signal": protocol["aggregation"],
        "primary_loocv_metrics": {key: value for key, value in loocv.items() if key != "thresholds"},
        "primary_loocv_threshold_summary": {"minimum": min(loocv["thresholds"]), "median": statistics.median(loocv["thresholds"]), "maximum": max(loocv["thresholds"])},
        "primary_loocv_confidence_intervals": {"sensitivity_95": _wilson(loocv["tp"], loocv["tp"] + loocv["fn"]), "specificity_95": _wilson(loocv["tn"], loocv["tn"] + loocv["fp"])},
        "secondary_diagnostics_not_eligible_to_replace_primary": {"apparent_roc_auc": _roc_auc(scores, truth), "apparent_threshold_for_future_freeze": apparent_threshold, "apparent_metrics": apparent, "raw_argmax": raw},
        "development_reader_gate_passed": gate,
        "request_count": summary["request_count"],
        "case_timing_seconds": summary["case_timing_seconds"],
        "precomputed_atlas_scoring_time_gate_passed": summary["case_timing_seconds"]["all_within_180"],
        "end_to_end_180_seconds_proven": False,
        "protocol_signature": protocol["protocol_signature"],
        "score_summary_sha256": _sha256(Path(score_root).resolve() / "summary.json"),
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
    staging = output.parent / f"._v18eval_{uuid.uuid4().hex[:8]}"
    staging.mkdir()
    try:
        _write_json_atomic(staging / "evaluation.json", result)
        with (staging / "case_scores.csv").open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=["case_id", "label", "score", "raw_classification", "chunk_count", "case_elapsed_seconds"])
            writer.writeheader()
            for row in rows:
                writer.writerow({"case_id": row["case_id"], "label": labels[row["case_id"]]["label"], "score": row["score"], "raw_classification": row["classification"], "chunk_count": row["chunk_count"], "case_elapsed_seconds": row["case_elapsed_seconds"]})
        _publish_directory(staging, output)
    finally:
        if staging.exists():
            shutil.rmtree(staging)
    return result
