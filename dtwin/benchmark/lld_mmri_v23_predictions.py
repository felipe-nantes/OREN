"""Freeze label-blind LLD-MMRI predictions with the development-frozen v23 calibrator."""
from __future__ import annotations

import json
import math
import shutil
import time
import uuid
from pathlib import Path
from typing import Any

from dtwin.benchmark.lld_mmri_v23_download import _load_and_validate_protocol
from dtwin.benchmark.lld_mmri_v23_signals import RAW_SIGNAL_SUMMARY_SCHEMA
from dtwin.benchmark.openswisshcc_alignment import _publish_directory, _sha256
from dtwin.benchmark.openswisshcc_v20_fusion import V11_WEIGHTS, _canonical_sha
from dtwin.benchmark.openswisshcc_v23_shape_fusion import (
    _load_shape_bundle,
    _validated_calibrator,
    score_with_frozen_calibrator,
)
from dtwin.benchmark.public_independent_v21_calibrator import (
    RAW_SIGNAL_SCHEMA,
    _contains_protected_key,
)
from dtwin.core import PipelineError
from dtwin.medgemma_screening import _write_json_atomic

PREDICTION_SCHEMA = "argos-lld-mmri-v23-frozen-prediction-v1"
RUN_SCHEMA = "argos-lld-mmri-v23-frozen-prediction-batch-v1"


def _json(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PipelineError(f"{label} ausente ou invalido.") from exc
    if not isinstance(value, dict):
        raise PipelineError(f"{label} deve ser objeto.")
    return value


def _jsonl(path: Path, label: str) -> list[dict[str, Any]]:
    try:
        rows = [
            json.loads(line)
            for line in Path(path).read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    except (OSError, json.JSONDecodeError) as exc:
        raise PipelineError(f"{label} ausente ou invalido.") from exc
    if not rows or any(not isinstance(row, dict) for row in rows):
        raise PipelineError(f"{label} vazio ou invalido.")
    return rows


def freeze_lld_mmri_v23_predictions(
    *,
    context: dict[str, Any],
    protocol_root: Path,
    calibrator_path: Path,
    raw_signals_root: Path,
    shape_root: Path,
    output_root: Path,
) -> dict[str, Any]:
    """Score every case without labels and atomically freeze the predictions."""

    case_ids = context.get("case_ids")
    protocol_case_count = context.get("protocol_case_count")
    technical_failure_case_ids = context.get("technical_failure_case_ids")
    review_signature = context.get("review_signature")
    if (
        not isinstance(case_ids, list)
        or not case_ids
        or len(case_ids) != len(set(case_ids))
        or not isinstance(protocol_case_count, int)
        or not isinstance(technical_failure_case_ids, list)
        or len(technical_failure_case_ids)
        != context.get("technical_failure_case_count")
        or len(set(technical_failure_case_ids)) != len(technical_failure_case_ids)
        or protocol_case_count != len(case_ids) + len(technical_failure_case_ids)
        or context.get("technical_failures_count_as_primary_metric_errors") is not True
        or not isinstance(review_signature, str)
        or len(review_signature) != 64
    ):
        raise PipelineError("Contexto LLD-MMRI invalido para congelar predicoes.")
    protocol, _ = _load_and_validate_protocol(protocol_root)
    expected_case_ids = [
        case_id
        for case_id in protocol.get("case_ids", [])
        if case_id not in set(technical_failure_case_ids)
    ]
    if (
        protocol.get("case_count") != protocol_case_count
        or case_ids != expected_case_ids
        or [case_id for case_id in protocol.get("case_ids", []) if case_id in set(technical_failure_case_ids)]
        != technical_failure_case_ids
    ):
        raise PipelineError("Protocolo LLD-MMRI divergiu da coorte revisada.")
    calibrator_path = Path(calibrator_path).resolve()
    calibrator = _validated_calibrator(_json(calibrator_path, "Calibrador v23"))
    protocol_threshold = protocol.get("decision_threshold")
    if (
        protocol.get("calibrator_signature") != calibrator["calibrator_signature"]
        or protocol.get("calibrator_sha256") != _sha256(calibrator_path)
        or isinstance(protocol_threshold, bool)
        or not isinstance(protocol_threshold, (int, float))
        or not math.isfinite(float(protocol_threshold))
        or float(protocol_threshold) != float(calibrator["decision_threshold"])
    ):
        raise PipelineError("Calibrador v23 divergiu do protocolo externo congelado.")

    raw_signals_root = Path(raw_signals_root).resolve()
    raw_path = raw_signals_root / "raw_signals.jsonl"
    raw_summary = _json(raw_signals_root / "summary.json", "Resumo de sinais v11")
    raw_rows = _jsonl(raw_path, "Sinais v11")
    if (
        raw_summary.get("schema") != RAW_SIGNAL_SUMMARY_SCHEMA
        or raw_summary.get("status") != "complete_raw_signals_no_labels_no_decision"
        or raw_summary.get("case_count") != len(case_ids)
        or raw_summary.get("case_ids") != case_ids
        or raw_summary.get("protocol_case_count") != protocol_case_count
        or raw_summary.get("technical_failure_case_count")
        != len(technical_failure_case_ids)
        or raw_summary.get("technical_failure_case_ids")
        != technical_failure_case_ids
        or raw_summary.get("technical_failures_excluded_from_inference") is not True
        or raw_summary.get("technical_failures_count_as_primary_metric_errors") is not True
        or raw_summary.get("signals_sha256") != _sha256(raw_path)
        or raw_summary.get("review_signature") != review_signature
        or raw_summary.get("ground_truth_read") is not False
        or raw_summary.get("metrics_calculated") is not False
        or raw_summary.get("final_decision") is not None
        or len(raw_rows) != len(case_ids)
    ):
        raise PipelineError("Bundle de sinais v11 LLD-MMRI incompleto ou adulterado.")
    raw_by_id: dict[str, dict[str, Any]] = {}
    for expected_id, row in zip(case_ids, raw_rows, strict=True):
        signals = row.get("signals")
        times = row.get("component_elapsed_seconds")
        if (
            row.get("schema") != RAW_SIGNAL_SCHEMA
            or row.get("case_id") != expected_id
            or row.get("review_signature") != review_signature
            or not isinstance(signals, dict)
            or set(signals) != set(V11_WEIGHTS)
            or any(
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(float(value))
                for value in signals.values()
            )
            or not isinstance(times, dict)
            or any(
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(float(value))
                or float(value) < 0
                for value in times.values()
            )
            or row.get("ground_truth_read") is not False
            or row.get("metrics_calculated") is not False
            or row.get("final_decision") is not None
            or row.get("holdout_opened") is not False
            or row.get("research_only") is not True
            or row.get("clinical_use_allowed") is not False
            or _contains_protected_key(row)
        ):
            raise PipelineError("Registro de sinal v11 LLD-MMRI invalido.")
        raw_by_id[expected_id] = row

    shape_summary, shapes = _load_shape_bundle(Path(shape_root).resolve(), case_ids)
    if shape_summary.get("review_signature") != review_signature:
        raise PipelineError("Ramo geometrico v23 divergiu da revisao LLD-MMRI.")
    shape_rows = _jsonl(Path(shape_root).resolve() / "features.jsonl", "Features geometricas v23")
    shape_times = {
        str(row.get("case_id")): float(row.get("elapsed_seconds", 0.0))
        for row in shape_rows
    }
    if set(shape_times) != set(case_ids) or any(
        not math.isfinite(value) or value < 0 for value in shape_times.values()
    ):
        raise PipelineError("Tempos geometricos v23 invalidos.")

    output_root = Path(output_root).resolve()
    if output_root.exists():
        raise PipelineError("Predicoes LLD-MMRI v23 existentes; sobrescrita recusada.")
    output_root.parent.mkdir(parents=True, exist_ok=True)
    staging = output_root.parent / f"._lldv23pred_{uuid.uuid4().hex[:8]}"
    staging.mkdir()
    started = time.monotonic()
    predictions: list[dict[str, Any]] = []
    try:
        for case_id in case_ids:
            raw = raw_by_id[case_id]
            result = score_with_frozen_calibrator(
                calibrator,
                signals={name: float(raw["signals"][name]) for name in V11_WEIGHTS},
                weighted_linearity=float(shapes[case_id]),
            )
            component_seconds = sum(
                float(value) for value in raw["component_elapsed_seconds"].values()
            )
            prepared_signal_seconds = component_seconds + shape_times[case_id]
            base = {
                "schema": PREDICTION_SCHEMA,
                "case_id": case_id,
                **result,
                "prepared_signal_seconds": prepared_signal_seconds,
                "prepared_signal_time_within_180_seconds": prepared_signal_seconds <= 180.0,
                "raw_signal_record_sha256": _canonical_sha(raw),
                "shape_weighted_linearity": float(shapes[case_id]),
                "review_signature": review_signature,
                "protocol_signature": protocol["protocol_signature"],
                "ground_truth_read": False,
                "metrics_calculated": False,
                "end_to_end_time_evaluated": False,
                "research_only": True,
                "clinical_use_allowed": False,
                "requires_human_review": True,
            }
            row = dict(base)
            row["prediction_signature"] = _canonical_sha(base)
            predictions.append(row)
        predictions_path = staging / "predictions.jsonl"
        predictions_path.write_text(
            "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in predictions),
            encoding="utf-8",
        )
        max_prepared = max(float(row["prepared_signal_seconds"]) for row in predictions)
        base = {
            "schema": RUN_SCHEMA,
            "status": "frozen_complete_predictions_before_labels",
            "protocol_case_count": protocol_case_count,
            "case_count": len(predictions),
            "case_ids": case_ids,
            "technical_failure_case_count": len(technical_failure_case_ids),
            "technical_failure_case_ids": technical_failure_case_ids,
            "technical_failures_excluded_from_inference": True,
            "technical_failures_count_as_primary_metric_errors": True,
            "positive_prediction_count": sum(row["prediction"] == "POSITIVE" for row in predictions),
            "negative_prediction_count": sum(row["prediction"] == "NEGATIVE" for row in predictions),
            "predictions_sha256": _sha256(predictions_path),
            "protocol_signature": protocol["protocol_signature"],
            "calibrator_signature": calibrator["calibrator_signature"],
            "review_signature": review_signature,
            "raw_signals_summary_sha256": _sha256(raw_signals_root / "summary.json"),
            "shape_summary_sha256": _sha256(Path(shape_root).resolve() / "summary.json"),
            "max_prepared_signal_seconds": max_prepared,
            "all_prepared_signal_times_within_180_seconds": max_prepared <= 180.0,
            "total_freeze_wall_seconds": time.monotonic() - started,
            "predictions_frozen": True,
            "ground_truth_read": False,
            "metrics_calculated": False,
            "end_to_end_time_evaluated": False,
            "end_to_end_180_second_gate_claimed": False,
            "qualified": False,
            "research_only": True,
            "clinical_use_allowed": False,
            "requires_human_review": True,
        }
        summary = dict(base)
        summary["run_signature"] = _canonical_sha(base)
        _write_json_atomic(staging / "summary.json", summary)
        _publish_directory(staging, output_root)
        return summary
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise


__all__ = [
    "PREDICTION_SCHEMA",
    "RUN_SCHEMA",
    "freeze_lld_mmri_v23_predictions",
]
