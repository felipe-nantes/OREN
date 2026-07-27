"""Direct wall-clock reproduction gate for frozen LLD-MMRI v23 predictions."""
from __future__ import annotations

import json
import math
import os
import shutil
import time
from pathlib import Path
from typing import Any, Callable

from dtwin.benchmark.lld_mmri_v23_download import _load_and_validate_protocol
from dtwin.benchmark.lld_mmri_v23_evaluation import TIMING_SCHEMA, _verify_predictions
from dtwin.benchmark.openswisshcc_alignment import _publish_directory, _sha256
from dtwin.benchmark.openswisshcc_v20_fusion import _canonical_sha
from dtwin.core import PipelineError
from dtwin.medgemma_screening import _write_json_atomic


CASE_TIMING_SCHEMA = "argos-lld-mmri-v23-direct-case-timing-v1"
RUNNER_ID = "argos-lld-mmri-v23-direct-case-runner-v1"
REQUIRED_STAGES = (
    "input_validation",
    "liver_segmentation",
    "panel_generation",
    "lesion_localizer",
    "candidate_shape",
    "medsiglip",
    "medgemma",
    "fusion_persistence",
)
DirectCaseRunner = Callable[[str], dict[str, Any]]


def _valid_checkpoint(path: Path) -> list[dict[str, Any]] | None:
    if not path.is_file():
        return None
    try:
        rows = [
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    except (OSError, json.JSONDecodeError):
        return None
    if not rows or any(not isinstance(row, dict) for row in rows):
        return None
    return rows


def _write_checkpoint(path: Path, rows: list[dict[str, Any]]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    backup = path.with_suffix(path.suffix + ".backup")
    payload = "".join(
        json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows
    )
    with temporary.open("w", encoding="utf-8", newline="\n") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())
    if _valid_checkpoint(temporary) != rows:
        temporary.unlink(missing_ok=True)
        raise PipelineError("Checkpoint temporal LLD-MMRI nao foi persistido integralmente.")
    if path.exists():
        os.replace(path, backup)
    os.replace(temporary, path)


def _load_checkpoint(path: Path) -> list[dict[str, Any]]:
    rows = _valid_checkpoint(path)
    if rows is not None:
        return rows
    backup = path.with_suffix(path.suffix + ".backup")
    rows = _valid_checkpoint(backup)
    if rows is None:
        if path.exists() or backup.exists():
            raise PipelineError("Checkpoint temporal LLD-MMRI e backup estao corrompidos.")
        return []
    temporary = path.with_suffix(path.suffix + ".recovered")
    shutil.copy2(backup, temporary)
    os.replace(temporary, path)
    return rows


def _validate_timing_row(
    row: dict[str, Any],
    *,
    case_id: str,
    prediction: dict[str, Any],
    maximum_seconds: float,
) -> None:
    unsigned = dict(row)
    signature = unsigned.pop("case_timing_signature", None)
    elapsed = row.get("elapsed_seconds")
    stages = row.get("stages")
    if (
        row.get("schema") != CASE_TIMING_SCHEMA
        or row.get("case_id") != case_id
        or signature != _canonical_sha(unsigned)
        or row.get("runner_id") != RUNNER_ID
        or row.get("prediction_signature") != prediction["prediction_signature"]
        or row.get("prediction") != prediction["prediction"]
        or row.get("maximum_seconds") != float(maximum_seconds)
        or isinstance(elapsed, bool)
        or not isinstance(elapsed, (int, float))
        or not math.isfinite(float(elapsed))
        or float(elapsed) < 0
        or row.get("within_budget") is not (
            float(elapsed) <= float(maximum_seconds)
        )
        or row.get("continuous_wall_clock") is not True
        or row.get("component_sum_only") is not False
        or row.get("ground_truth_read") is not False
        or row.get("lesion_masks_read") != 0
        or not isinstance(stages, dict)
        or set(stages) != set(REQUIRED_STAGES)
        or any(
            not isinstance(value, dict) or value.get("status") != "complete"
            for value in stages.values()
        )
    ):
        raise PipelineError(f"Checkpoint temporal LLD-MMRI invalido: {case_id}.")


def measure_lld_mmri_v23_direct_reproduction(
    *,
    protocol_root: Path,
    frozen_prediction_root: Path,
    output_root: Path,
    run_case: DirectCaseRunner,
    maximum_seconds: float = 180.0,
) -> dict[str, Any]:
    """Time one continuous raw-to-prediction callback for every frozen case."""

    if (
        isinstance(maximum_seconds, bool)
        or not isinstance(maximum_seconds, (int, float))
        or not math.isfinite(float(maximum_seconds))
        or float(maximum_seconds) <= 0
    ):
        raise PipelineError("Limite direto de tempo LLD-MMRI invalido.")
    protocol, _ = _load_and_validate_protocol(protocol_root)
    prediction_summary, predictions = _verify_predictions(frozen_prediction_root, protocol)
    case_ids = list(prediction_summary["case_ids"])
    technical_failure_case_ids = list(
        prediction_summary["technical_failure_case_ids"]
    )
    by_id = {str(row["case_id"]): row for row in predictions}
    output_root = Path(output_root).resolve()
    if output_root.exists():
        raise PipelineError("Medicao direta LLD-MMRI existente; sobrescrita recusada.")
    output_root.parent.mkdir(parents=True, exist_ok=True)
    staging = output_root.parent / f".{output_root.name}.incomplete"
    context = {
        "schema": "argos-lld-mmri-v23-direct-timing-checkpoint-context-v1",
        "case_ids": case_ids,
        "protocol_case_count": protocol["case_count"],
        "technical_failure_case_ids": technical_failure_case_ids,
        "protocol_signature": protocol["protocol_signature"],
        "prediction_run_signature": prediction_summary["run_signature"],
        "predictions_sha256": prediction_summary["predictions_sha256"],
        "maximum_seconds": float(maximum_seconds),
        "ground_truth_read": False,
        "lesion_masks_read": 0,
    }
    context["context_signature"] = _canonical_sha(context)
    context_path = staging / "checkpoint_context.json"
    checkpoint_path = staging / "checkpoint_cases.jsonl"
    if staging.exists():
        try:
            persisted_context = json.loads(context_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise PipelineError("Contexto do checkpoint temporal LLD-MMRI invalido.") from exc
        if persisted_context != context:
            raise PipelineError("Checkpoint temporal LLD-MMRI pertence a outra execucao.")
    else:
        staging.mkdir()
        _write_json_atomic(context_path, context)
    rows = _load_checkpoint(checkpoint_path)
    if len(rows) > len(case_ids):
        raise PipelineError("Checkpoint temporal LLD-MMRI excede a coorte elegivel.")
    for index, row in enumerate(rows):
        _validate_timing_row(
            row,
            case_id=case_ids[index],
            prediction=by_id[case_ids[index]],
            maximum_seconds=float(maximum_seconds),
        )
    try:
        for case_id in case_ids[len(rows):]:
            started = time.perf_counter()
            receipt = run_case(case_id)
            elapsed = time.perf_counter() - started
            stages = receipt.get("stages") if isinstance(receipt, dict) else None
            if (
                not isinstance(receipt, dict)
                or receipt.get("runner_id") != RUNNER_ID
                or receipt.get("case_id") != case_id
                or receipt.get("prediction_signature") != by_id[case_id]["prediction_signature"]
                or receipt.get("prediction") != by_id[case_id]["prediction"]
                or receipt.get("ground_truth_read") is not False
                or receipt.get("lesion_masks_read") != 0
                or not isinstance(stages, dict)
                or tuple(stages) != REQUIRED_STAGES
                or any(
                    not isinstance(value, dict) or value.get("status") != "complete"
                    for value in stages.values()
                )
                or not math.isfinite(elapsed)
                or elapsed < 0
            ):
                raise PipelineError(
                    f"Execucao direta LLD-MMRI nao reproduziu a predicao congelada: {case_id}."
                )
            base = {
                "schema": CASE_TIMING_SCHEMA,
                "case_id": case_id,
                "runner_id": RUNNER_ID,
                "elapsed_seconds": elapsed,
                "maximum_seconds": float(maximum_seconds),
                "within_budget": elapsed <= float(maximum_seconds),
                "prediction_signature": by_id[case_id]["prediction_signature"],
                "prediction": by_id[case_id]["prediction"],
                "stages": stages,
                "continuous_wall_clock": True,
                "component_sum_only": False,
                "model_loading_policy": "warmed_services_model_load_excluded_gateway_wait_included",
                "download_included": False,
                "worker_queue_included": False,
                "human_review_delay_included": False,
                "ground_truth_read": False,
                "lesion_masks_read": 0,
                "research_only": True,
                "clinical_use_allowed": False,
            }
            row = dict(base)
            row["case_timing_signature"] = _canonical_sha(base)
            _validate_timing_row(
                row,
                case_id=case_id,
                prediction=by_id[case_id],
                maximum_seconds=float(maximum_seconds),
            )
            rows.append(row)
            _write_checkpoint(checkpoint_path, rows)
        rows_path = staging / "cases.jsonl"
        rows_path.write_text(
            "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows),
            encoding="utf-8",
        )
        maximum = max(float(row["elapsed_seconds"]) for row in rows)
        base = {
            "schema": TIMING_SCHEMA,
            "status": "complete_measured_end_to_end",
            "protocol_case_count": protocol["case_count"],
            "case_count": len(rows),
            "case_ids": case_ids,
            "technical_failure_case_count": len(technical_failure_case_ids),
            "technical_failure_case_ids": technical_failure_case_ids,
            "technical_failures_count_as_primary_metric_errors": True,
            "prediction_run_signature": prediction_summary["run_signature"],
            "runner_id": RUNNER_ID,
            "required_stages": list(REQUIRED_STAGES),
            "continuous_wall_clock": True,
            "component_sum_only": False,
            "maximum_allowed_seconds": float(maximum_seconds),
            "max_end_to_end_seconds": maximum,
            "all_inference_eligible_cases_within_180_seconds": (
                float(maximum_seconds) == 180.0 and maximum <= 180.0
            ),
            # Legacy compatibility. Timing is measured only for inference-eligible
            # cases; technical failures have no fabricated end-to-end run.
            "all_cases_within_180_seconds": (
                float(maximum_seconds) == 180.0 and maximum <= 180.0
            ),
            "cases_sha256": _sha256(rows_path),
            "protocol_signature": protocol["protocol_signature"],
            "predictions_sha256": prediction_summary["predictions_sha256"],
            "all_predictions_exactly_reproduced": True,
            "ground_truth_read": False,
            "lesion_masks_read": 0,
            "research_only": True,
            "clinical_use_allowed": False,
            "requires_human_review": True,
        }
        summary = dict(base)
        summary["timing_signature"] = _canonical_sha(base)
        _write_json_atomic(staging / "summary.json", summary)
        checkpoint_path.unlink(missing_ok=True)
        checkpoint_path.with_suffix(checkpoint_path.suffix + ".backup").unlink(
            missing_ok=True
        )
        context_path.unlink(missing_ok=True)
        (staging / "failure.json").unlink(missing_ok=True)
        _publish_directory(staging, output_root)
        return summary
    except Exception as exc:
        _write_json_atomic(
            staging / "failure.json",
            {
                "schema": "argos-lld-mmri-v23-direct-timing-failure-v1",
                "completed_case_count": len(rows),
                "next_case_id": case_ids[len(rows)] if len(rows) < len(case_ids) else None,
                "error_type": type(exc).__name__,
                "error": str(exc),
                "checkpoint_preserved": True,
            },
        )
        raise


__all__ = [
    "CASE_TIMING_SCHEMA",
    "REQUIRED_STAGES",
    "RUNNER_ID",
    "measure_lld_mmri_v23_direct_reproduction",
]
