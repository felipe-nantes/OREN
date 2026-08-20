"""Runner resumível das predições cegas high-dimensional v13."""
from __future__ import annotations

import base64
import json
import statistics
import time
from pathlib import Path
from urllib.request import Request

from dtwin.benchmark.openswisshcc_highdimensional_batch import (
    BATCH_PROTOCOL_SCHEMA,
    validate_highdimensional_blind_bundle,
)
from dtwin.benchmark.openswisshcc_highdimensional_inference import (
    CONTRACT,
    TIME_GATE_SECONDS,
    _atomic_json,
    _canonical_hash,
    _request_json,
    validate_highdimensional_stack,
)
from dtwin.core import PipelineError, sha256_of
from dtwin.medgemma_client import load_screening_config

PREDICTION_SCHEMA = "argos-openswisshcc-highdimensional-batch-prediction-v1"
PROGRESS_SCHEMA = "argos-openswisshcc-highdimensional-batch-progress-v1"
SUMMARY_SCHEMA = "argos-openswisshcc-highdimensional-batch-summary-v1"


def _load_batch_protocol(path: Path) -> dict:
    try:
        protocol = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PipelineError("Protocolo batch high-dimensional ausente ou inválido.") from exc
    signature = protocol.pop("protocol_signature", None)
    if signature != _canonical_hash(protocol):
        raise PipelineError("Assinatura do protocolo batch diverge.")
    protocol["protocol_signature"] = signature
    if (
        protocol.get("schema") != BATCH_PROTOCOL_SCHEMA
        or protocol.get("status") != "frozen_before_predictions"
        or protocol.get("ground_truth_read") is not False
        or protocol.get("metrics_calculated") is not False
        or protocol.get("holdout_opened") is not False
        or protocol.get("research_only") is not True
        or protocol.get("clinical_use_allowed") is not False
        or protocol.get("requires_human_review") is not True
        or protocol.get("generation", {}).get("requests_per_case") != 1
        or protocol.get("generation", {}).get("automatic_retries") != 0
    ):
        raise PipelineError("Protocolo batch não está congelado ou viola salvaguardas.")
    return protocol


def _validate_existing_prediction(
    path: Path, *, protocol: dict, stack_record: dict
) -> dict:
    try:
        result = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PipelineError("Predição existente ausente ou inválida.") from exc
    if (
        result.get("schema") != PREDICTION_SCHEMA
        or result.get("status") != "technical_passed"
        or result.get("case_id") != stack_record["case_id"]
        or result.get("protocol_signature") != protocol["protocol_signature"]
        or result.get("stack_manifest_sha256") != stack_record["stack_manifest_sha256"]
        or result.get("classification") not in {"POSITIVA", "NEGATIVA", "INCONCLUSIVA"}
        or result.get("output_schema_valid") is not True
        or result.get("time_gate_passed") is not True
        or result.get("ground_truth_read") is not False
        or result.get("metrics_calculated") is not False
        or result.get("holdout_opened") is not False
    ):
        raise PipelineError("Predição existente não é reutilizável no protocolo atual.")
    return result


def _infer_case(
    *,
    bundle_root: Path,
    stack_record: dict,
    protocol: dict,
    health: dict,
    prediction_path: Path,
) -> dict:
    case_id = stack_record["case_id"]
    stack_dir = bundle_root / "stacks" / case_id
    manifest, images = validate_highdimensional_stack(stack_dir)
    if (
        sha256_of(stack_dir / "manifest.json") != stack_record["stack_manifest_sha256"]
        or manifest.get("case_id") != case_id
        or manifest.get("slice_count") != stack_record["slice_count"]
    ):
        raise PipelineError("Pilha mudou após o congelamento do bundle.")
    payload = {
        "contract": CONTRACT,
        "model_id": protocol["model_id"],
        "model_version": protocol["model_version"],
        "instruction": protocol["instruction"],
        "images": [
            {"mime_type": "image/png", "base64": base64.b64encode(raw).decode("ascii")}
            for raw in images
        ],
        "query": protocol["query"],
        "generation": {
            "max_output_tokens": protocol["generation"]["max_output_tokens"],
            "response_prefix": protocol["generation"]["response_prefix"],
        },
    }
    request = Request(
        protocol["endpoint_url"],
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    started = time.monotonic()
    response = _request_json(request, timeout=TIME_GATE_SECONDS)
    elapsed = time.monotonic() - started
    if (
        response.get("contract") != CONTRACT
        or response.get("model_id") != protocol["model_id"]
        or response.get("model_version") != protocol["model_version"]
        or response.get("slice_count") != len(images)
        or response.get("research_only") is not True
        or response.get("clinical_use_allowed") is not False
        or response.get("requires_human_review") is not True
    ):
        raise PipelineError("Resposta volumétrica violou contrato ou salvaguardas.")
    raw_output = response.get("output")
    report = None
    classification = None
    try:
        report = json.loads(raw_output) if isinstance(raw_output, str) else None
        candidate = report.get("resultado_hipotese") if isinstance(report, dict) else None
        if candidate in {"POSITIVA", "NEGATIVA", "INCONCLUSIVA"}:
            classification = candidate
    except json.JSONDecodeError:
        pass
    valid = classification is not None
    result = {
        "schema": PREDICTION_SCHEMA,
        "status": "technical_passed" if valid and elapsed <= TIME_GATE_SECONDS else "technical_failed",
        "case_id": case_id,
        "protocol_signature": protocol["protocol_signature"],
        "stack_manifest_sha256": stack_record["stack_manifest_sha256"],
        "slice_count": len(images),
        "classification": classification,
        "report": report,
        "raw_output": raw_output,
        "gateway_timings_seconds": response.get("timings_seconds"),
        "request_elapsed_seconds": round(elapsed, 4),
        "time_gate_seconds": TIME_GATE_SECONDS,
        "time_gate_passed": elapsed <= TIME_GATE_SECONDS,
        "output_schema_valid": valid,
        "health_model_id": health.get("model_id"),
        "ground_truth_read": False,
        "metrics_calculated": False,
        "holdout_opened": False,
        "research_only": True,
        "clinical_use_allowed": False,
        "requires_human_review": True,
    }
    _atomic_json(prediction_path, result)
    if result["status"] != "technical_passed":
        raise PipelineError(f"Caso {case_id} falhou schema ou gate temporal.")
    return result


def _write_progress(
    *, output_root: Path, protocol: dict, bundle: dict, predictions: list[dict]
) -> dict:
    records = [{
        "case_id": item["case_id"],
        "prediction_sha256": sha256_of(output_root / "predictions" / f"{item['case_id']}.json"),
        "classification": item["classification"],
        "request_elapsed_seconds": item["request_elapsed_seconds"],
        "time_gate_passed": item["time_gate_passed"],
    } for item in predictions]
    progress = {
        "schema": PROGRESS_SCHEMA,
        "status": "complete" if len(records) == bundle["case_count"] else "partial",
        "protocol_signature": protocol["protocol_signature"],
        "case_count": bundle["case_count"],
        "completed_case_count": len(records),
        "pending_case_count": bundle["case_count"] - len(records),
        "predictions": records,
        "ground_truth_read": False,
        "metrics_calculated": False,
        "holdout_opened": False,
        "research_only": True,
        "clinical_use_allowed": False,
        "requires_human_review": True,
    }
    _atomic_json(output_root / "progress.json", progress)
    if progress["status"] == "complete":
        timings = [item["request_elapsed_seconds"] for item in predictions]
        classes = {label: sum(item["classification"] == label for item in predictions)
                   for label in ("POSITIVA", "NEGATIVA", "INCONCLUSIVA")}
        summary = {
            "schema": SUMMARY_SCHEMA,
            "status": "blind_predictions_complete",
            "protocol_signature": protocol["protocol_signature"],
            "case_count": len(predictions),
            "classification_counts_without_ground_truth": classes,
            "request_seconds_min": min(timings),
            "request_seconds_median": statistics.median(timings),
            "request_seconds_max": max(timings),
            "all_time_gates_passed": all(item["time_gate_passed"] for item in predictions),
            "progress_sha256": sha256_of(output_root / "progress.json"),
            "ground_truth_read": False,
            "metrics_calculated": False,
            "holdout_opened": False,
            "research_only": True,
            "clinical_use_allowed": False,
            "requires_human_review": True,
        }
        _atomic_json(output_root / "summary.json", summary)
    return progress


def run_highdimensional_blind_batch(
    *,
    bundle_root: Path,
    protocol_path: Path,
    config_path: Path,
    output_root: Path,
    max_new_cases: int | None = None,
    progress_callback=None,
) -> dict:
    if max_new_cases is not None and max_new_cases < 1:
        raise PipelineError("max_new_cases deve ser positivo.")
    bundle_root = Path(bundle_root).resolve()
    bundle = validate_highdimensional_blind_bundle(bundle_root)
    protocol = _load_batch_protocol(protocol_path)
    if (
        sha256_of(bundle_root / "bundle.json") != protocol.get("bundle_sha256")
        or bundle.get("bundle_signature") != protocol.get("bundle_signature")
        or bundle.get("case_ids") != protocol.get("case_ids")
        or bundle.get("maximum_slices") != protocol.get("maximum_slices")
    ):
        raise PipelineError("Bundle diverge do protocolo batch congelado.")
    config = load_screening_config(config_path)
    med = config["medgemma"]
    if (
        med.get("model_id") != protocol.get("model_id")
        or med.get("model_version") != protocol.get("model_version")
    ):
        raise PipelineError("Configuração do modelo diverge do protocolo batch.")
    health = _request_json(
        Request(str(med["healthcheck_url"]), headers={"Accept": "application/json"}, method="GET"),
        timeout=15,
    )
    if (
        health.get("status") != "ready"
        or health.get("model_id") != protocol["model_id"]
        or health.get("model_version") != protocol["model_version"]
        or health.get("volume_contract") != CONTRACT
        or health.get("volume_supported") is not True
    ):
        raise PipelineError("Health não confirmou o contrato batch congelado.")

    output_root = Path(output_root).resolve()
    predictions_root = output_root / "predictions"
    predictions_root.mkdir(parents=True, exist_ok=True)
    by_case = {item["case_id"]: item for item in bundle["stacks"]}
    predictions = []
    new_count = 0
    for index, case_id in enumerate(bundle["case_ids"], start=1):
        record = by_case[case_id]
        path = predictions_root / f"{case_id}.json"
        if path.exists():
            result = _validate_existing_prediction(path, protocol=protocol, stack_record=record)
            reused = True
        elif max_new_cases is not None and new_count >= max_new_cases:
            break
        else:
            result = _infer_case(
                bundle_root=bundle_root,
                stack_record=record,
                protocol=protocol,
                health=health,
                prediction_path=path,
            )
            new_count += 1
            reused = False
        predictions.append(result)
        _write_progress(
            output_root=output_root,
            protocol=protocol,
            bundle=bundle,
            predictions=predictions,
        )
        if progress_callback:
            progress_callback({
                "index": index,
                "case_count": bundle["case_count"],
                "case_id": case_id,
                "classification": result["classification"],
                "request_elapsed_seconds": result["request_elapsed_seconds"],
                "reused": reused,
            })
    return _write_progress(
        output_root=output_root,
        protocol=protocol,
        bundle=bundle,
        predictions=predictions,
    )
