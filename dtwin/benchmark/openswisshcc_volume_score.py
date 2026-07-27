"""Protocolo congelado e inferência cega do escore volumétrico v14."""
from __future__ import annotations

import base64
import json
import math
import statistics
import time
from pathlib import Path
from urllib.parse import urlparse, urlunparse
from urllib.request import Request

from dtwin.benchmark.openswisshcc_highdimensional_batch import (
    validate_highdimensional_blind_bundle,
)
from dtwin.benchmark.openswisshcc_highdimensional_inference import (
    INSTRUCTION,
    QUERY,
    RESPONSE_PREFIX,
    TIME_GATE_SECONDS,
    _atomic_json,
    _canonical_hash,
    _request_json,
    validate_highdimensional_stack,
)
from dtwin.core import PipelineError, sha256_of
from dtwin.medgemma_client import load_screening_config


CONTRACT = "dtwin-medgemma-volume-score-v1"
SCORING_METHOD = "first_token_restricted_softmax_v1"
CHOICES = ("POSITIVA", "NEGATIVA", "INCONCLUSIVA")
PROTOCOL_SCHEMA = "argos-openswisshcc-volume-score-protocol-v1"
PREDICTION_SCHEMA = "argos-openswisshcc-volume-score-prediction-v1"
PROGRESS_SCHEMA = "argos-openswisshcc-volume-score-progress-v1"
SUMMARY_SCHEMA = "argos-openswisshcc-volume-score-summary-v1"
PILOT_SCHEMA = "argos-openswisshcc-volume-score-determinism-pilot-v1"
PROBABILITY_TOLERANCE = 1e-6


def _score_url(endpoint_url: str) -> str:
    parsed = urlparse(str(endpoint_url))
    if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise PipelineError("Pontuação volumétrica exige endpoint HTTP exclusivamente local.")
    return urlunparse(parsed._replace(path="/score-volume", params="", query="", fragment=""))


def freeze_volume_score_protocol(
    *,
    bundle_root: Path,
    config_path: Path,
    out_path: Path,
) -> dict:
    """Congela o protocolo antes de qualquer pontuação v14."""

    bundle_root = Path(bundle_root).resolve()
    bundle = validate_highdimensional_blind_bundle(bundle_root)
    med = load_screening_config(config_path)["medgemma"]
    base = {
        "schema": PROTOCOL_SCHEMA,
        "status": "frozen_before_scores",
        "bundle_sha256": sha256_of(bundle_root / "bundle.json"),
        "bundle_signature": bundle["bundle_signature"],
        "case_count": bundle["case_count"],
        "case_ids": bundle["case_ids"],
        "maximum_slices": bundle["maximum_slices"],
        "model_id": med["model_id"],
        "model_version": med["model_version"],
        "contract": CONTRACT,
        "endpoint_url": _score_url(str(med["endpoint_url"])),
        "instruction": INSTRUCTION,
        "query": QUERY,
        "scoring": {
            "response_prefix": RESPONSE_PREFIX,
            "choices": list(CHOICES),
            "method": SCORING_METHOD,
            "requests_per_case": 1,
            "automatic_retries": 0,
            "determinism_pilot_repetitions": 2,
            "probability_tolerance": PROBABILITY_TOLERANCE,
        },
        "time_gate_seconds_per_request": TIME_GATE_SECONDS,
        "ground_truth_read": False,
        "metrics_calculated": False,
        "holdout_opened": False,
        "research_only": True,
        "clinical_use_allowed": False,
        "requires_human_review": True,
    }
    protocol = dict(base)
    protocol["protocol_signature"] = _canonical_hash(base)
    out_path = Path(out_path)
    if out_path.exists():
        try:
            existing = json.loads(out_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise PipelineError("Protocolo v14 existente é inválido.") from exc
        if existing != protocol:
            raise PipelineError("Protocolo v14 existente diverge; sobrescrita recusada.")
        return existing
    _atomic_json(out_path, protocol)
    return protocol


def _load_protocol(path: Path) -> dict:
    try:
        protocol = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PipelineError("Protocolo v14 ausente ou inválido.") from exc
    signature = protocol.pop("protocol_signature", None)
    if signature != _canonical_hash(protocol):
        raise PipelineError("Assinatura do protocolo v14 diverge.")
    protocol["protocol_signature"] = signature
    scoring = protocol.get("scoring", {})
    if (
        protocol.get("schema") != PROTOCOL_SCHEMA
        or protocol.get("status") != "frozen_before_scores"
        or protocol.get("contract") != CONTRACT
        or scoring.get("response_prefix") != RESPONSE_PREFIX
        or scoring.get("choices") != list(CHOICES)
        or scoring.get("method") != SCORING_METHOD
        or scoring.get("requests_per_case") != 1
        or scoring.get("automatic_retries") != 0
        or scoring.get("determinism_pilot_repetitions") != 2
        or scoring.get("probability_tolerance") != PROBABILITY_TOLERANCE
        or protocol.get("time_gate_seconds_per_request") != TIME_GATE_SECONDS
        or protocol.get("ground_truth_read") is not False
        or protocol.get("metrics_calculated") is not False
        or protocol.get("holdout_opened") is not False
        or protocol.get("research_only") is not True
        or protocol.get("clinical_use_allowed") is not False
        or protocol.get("requires_human_review") is not True
    ):
        raise PipelineError("Protocolo v14 não está congelado ou viola salvaguardas.")
    if _score_url(protocol.get("endpoint_url", "")) != protocol.get("endpoint_url"):
        raise PipelineError("Endpoint v14 não corresponde a /score-volume local.")
    return protocol


def _validate_score_response(response: dict, *, protocol: dict, slice_count: int) -> dict:
    if (
        response.get("contract") != CONTRACT
        or response.get("model_id") != protocol["model_id"]
        or response.get("model_version") != protocol["model_version"]
        or response.get("slice_count") != slice_count
        or response.get("scoring_method") != SCORING_METHOD
        or response.get("research_only") is not True
        or response.get("clinical_use_allowed") is not False
        or response.get("requires_human_review") is not True
        or type(response.get("tie_detected")) is not bool
    ):
        raise PipelineError("Resposta v14 violou contrato ou salvaguardas.")

    probabilities = response.get("choice_probabilities")
    if not isinstance(probabilities, dict) or set(probabilities) != set(CHOICES):
        raise PipelineError("Resposta v14 não contém exatamente as três probabilidades.")
    normalized: dict[str, float] = {}
    for label in CHOICES:
        value = probabilities[label]
        if type(value) not in {int, float}:
            raise PipelineError("Probabilidade v14 deve ser numérica.")
        value = float(value)
        if not math.isfinite(value) or not 0.0 <= value <= 1.0:
            raise PipelineError("Probabilidade v14 deve ser finita e pertencer a [0,1].")
        normalized[label] = value
    if not math.isclose(sum(normalized.values()), 1.0, rel_tol=0.0, abs_tol=PROBABILITY_TOLERANCE):
        raise PipelineError("Probabilidades v14 não somam 1 dentro da tolerância.")

    maximum = max(normalized.values())
    winners = [label for label in CHOICES if normalized[label] == maximum]
    expected_choice = winners[0]
    if response.get("choice") != expected_choice:
        raise PipelineError("Classe v14 não corresponde ao argmax determinístico.")
    if response.get("tie_detected") is not (len(winners) > 1):
        raise PipelineError("Flag de empate v14 diverge das probabilidades.")

    metadata = response.get("choice_token_metadata")
    if not isinstance(metadata, dict) or set(metadata) != set(CHOICES):
        raise PipelineError("Metadados de tokens v14 estão incompletos.")
    first_ids = []
    normalized_metadata = {}
    for label in CHOICES:
        item = metadata[label]
        if not isinstance(item, dict) or set(item) != {"first_token_id", "token_count"}:
            raise PipelineError("Metadado de token v14 possui campos inesperados.")
        first_id = item["first_token_id"]
        token_count = item["token_count"]
        if type(first_id) is not int or first_id < 0 or type(token_count) is not int or token_count < 1:
            raise PipelineError("Metadado de token v14 possui valor inválido.")
        first_ids.append(first_id)
        normalized_metadata[label] = {
            "first_token_id": first_id,
            "token_count": token_count,
        }
    if len(set(first_ids)) != len(CHOICES):
        raise PipelineError("Primeiros tokens v14 não são distintos.")
    return {
        "classification": expected_choice,
        "choice_probabilities": normalized,
        "choice_token_metadata": normalized_metadata,
        "tie_detected": bool(response["tie_detected"]),
    }


def _validate_existing_prediction(path: Path, *, protocol: dict, stack_record: dict) -> dict:
    try:
        result = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PipelineError("Pontuação v14 existente é inválida.") from exc
    if (
        result.get("schema") != PREDICTION_SCHEMA
        or result.get("status") != "technical_passed"
        or result.get("case_id") != stack_record["case_id"]
        or result.get("protocol_signature") != protocol["protocol_signature"]
        or result.get("stack_manifest_sha256") != stack_record["stack_manifest_sha256"]
        or result.get("scoring_method") != SCORING_METHOD
        or result.get("classification") not in CHOICES
        or result.get("time_gate_passed") is not True
        or result.get("score_schema_valid") is not True
        or result.get("ground_truth_read") is not False
        or result.get("metrics_calculated") is not False
        or result.get("holdout_opened") is not False
        or result.get("research_only") is not True
        or result.get("clinical_use_allowed") is not False
        or result.get("requires_human_review") is not True
    ):
        raise PipelineError("Pontuação v14 existente não é reutilizável.")
    _validate_score_response(
        {
            "contract": CONTRACT,
            "model_id": protocol["model_id"],
            "model_version": protocol["model_version"],
            "slice_count": result.get("slice_count"),
            "choice": result.get("classification"),
            "choice_probabilities": result.get("choice_probabilities"),
            "scoring_method": result.get("scoring_method"),
            "choice_token_metadata": result.get("choice_token_metadata"),
            "tie_detected": result.get("tie_detected"),
            "research_only": result.get("research_only"),
            "clinical_use_allowed": result.get("clinical_use_allowed"),
            "requires_human_review": result.get("requires_human_review"),
        },
        protocol=protocol,
        slice_count=stack_record["slice_count"],
    )
    return result


def _validate_context(
    *, bundle_root: Path, protocol_path: Path, config_path: Path
) -> tuple[dict, dict, dict]:
    bundle_root = Path(bundle_root).resolve()
    bundle = validate_highdimensional_blind_bundle(bundle_root)
    protocol = _load_protocol(protocol_path)
    if (
        sha256_of(bundle_root / "bundle.json") != protocol.get("bundle_sha256")
        or bundle.get("bundle_signature") != protocol.get("bundle_signature")
        or bundle.get("case_ids") != protocol.get("case_ids")
        or bundle.get("maximum_slices") != protocol.get("maximum_slices")
    ):
        raise PipelineError("Bundle diverge do protocolo v14 congelado.")
    med = load_screening_config(config_path)["medgemma"]
    if (
        med.get("model_id") != protocol.get("model_id")
        or med.get("model_version") != protocol.get("model_version")
        or _score_url(str(med.get("endpoint_url", ""))) != protocol.get("endpoint_url")
    ):
        raise PipelineError("Configuração do modelo diverge do protocolo v14.")
    health = _request_json(
        Request(str(med["healthcheck_url"]), headers={"Accept": "application/json"}, method="GET"),
        timeout=15,
    )
    if (
        health.get("status") != "ready"
        or health.get("model_id") != protocol["model_id"]
        or health.get("model_version") != protocol["model_version"]
        or health.get("volume_score_contract") != CONTRACT
        or health.get("volume_score_method") != SCORING_METHOD
        or health.get("volume_score_supported") is not True
    ):
        raise PipelineError("Health não confirmou o contrato v14 congelado.")
    return bundle, protocol, health


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
        raise PipelineError("Pilha mudou após o congelamento do bundle v14.")
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
        "scoring": {"response_prefix": protocol["scoring"]["response_prefix"]},
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
    validated = _validate_score_response(response, protocol=protocol, slice_count=len(images))
    time_passed = elapsed <= TIME_GATE_SECONDS
    result = {
        "schema": PREDICTION_SCHEMA,
        "status": "technical_passed" if time_passed else "technical_failed",
        "case_id": case_id,
        "protocol_signature": protocol["protocol_signature"],
        "stack_manifest_sha256": stack_record["stack_manifest_sha256"],
        "slice_count": len(images),
        "classification": validated["classification"],
        "choice_probabilities": validated["choice_probabilities"],
        "choice_token_metadata": validated["choice_token_metadata"],
        "tie_detected": validated["tie_detected"],
        "scoring_method": SCORING_METHOD,
        "gateway_timings_seconds": response.get("timings_seconds"),
        "request_elapsed_seconds": round(elapsed, 4),
        "time_gate_seconds": TIME_GATE_SECONDS,
        "time_gate_passed": time_passed,
        "score_schema_valid": True,
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
        raise PipelineError(f"Caso {case_id} excedeu o gate temporal v14.")
    return result


def run_volume_score_determinism_pilot(
    *,
    bundle_root: Path,
    protocol_path: Path,
    config_path: Path,
    output_root: Path,
    case_id: str | None = None,
) -> dict:
    """Executa duas pontuações planejadas do mesmo caso e exige estabilidade."""

    bundle_root = Path(bundle_root).resolve()
    bundle, protocol, health = _validate_context(
        bundle_root=bundle_root,
        protocol_path=protocol_path,
        config_path=config_path,
    )
    selected = case_id or bundle["case_ids"][0]
    if selected not in bundle["case_ids"]:
        raise PipelineError("Caso do piloto v14 não pertence ao bundle congelado.")
    by_case = {item["case_id"]: item for item in bundle["stacks"]}
    output_root = Path(output_root).resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    paths = [output_root / "replicate_1.json", output_root / "replicate_2.json"]
    if any(path.exists() for path in paths) or (output_root / "summary.json").exists():
        raise PipelineError("Artefato do piloto v14 já existe; sobrescrita recusada.")
    results = [
        _infer_case(
            bundle_root=bundle_root,
            stack_record=by_case[selected],
            protocol=protocol,
            health=health,
            prediction_path=path,
        )
        for path in paths
    ]
    differences = {
        label: abs(
            results[0]["choice_probabilities"][label]
            - results[1]["choice_probabilities"][label]
        )
        for label in CHOICES
    }
    tolerance = float(protocol["scoring"]["probability_tolerance"])
    deterministic = (
        results[0]["classification"] == results[1]["classification"]
        and max(differences.values()) <= tolerance
    )
    summary = {
        "schema": PILOT_SCHEMA,
        "status": "technical_passed" if deterministic else "technical_failed",
        "case_id": selected,
        "protocol_signature": protocol["protocol_signature"],
        "replicate_sha256": [sha256_of(path) for path in paths],
        "classifications": [result["classification"] for result in results],
        "absolute_probability_differences": differences,
        "probability_tolerance": tolerance,
        "deterministic": deterministic,
        "all_time_gates_passed": all(result["time_gate_passed"] for result in results),
        "request_elapsed_seconds": [result["request_elapsed_seconds"] for result in results],
        "ground_truth_read": False,
        "metrics_calculated": False,
        "holdout_opened": False,
        "research_only": True,
        "clinical_use_allowed": False,
        "requires_human_review": True,
    }
    _atomic_json(output_root / "summary.json", summary)
    if summary["status"] != "technical_passed":
        raise PipelineError("Piloto v14 não foi determinístico dentro da tolerância congelada.")
    return summary


def _write_progress(
    *, output_root: Path, protocol: dict, bundle: dict, predictions: list[dict]
) -> dict:
    records = [
        {
            "case_id": item["case_id"],
            "prediction_sha256": sha256_of(
                output_root / "predictions" / f"{item['case_id']}.json"
            ),
            "classification": item["classification"],
            "choice_probabilities": item["choice_probabilities"],
            "request_elapsed_seconds": item["request_elapsed_seconds"],
            "time_gate_passed": item["time_gate_passed"],
        }
        for item in predictions
    ]
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
        class_counts = {
            label: sum(item["classification"] == label for item in predictions)
            for label in CHOICES
        }
        probability_means = {
            label: statistics.fmean(
                item["choice_probabilities"][label] for item in predictions
            )
            for label in CHOICES
        }
        summary = {
            "schema": SUMMARY_SCHEMA,
            "status": "blind_scores_complete",
            "protocol_signature": protocol["protocol_signature"],
            "case_count": len(predictions),
            "classification_counts_without_ground_truth": class_counts,
            "mean_restricted_probabilities_without_ground_truth": probability_means,
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


def run_volume_score_blind_batch(
    *,
    bundle_root: Path,
    protocol_path: Path,
    config_path: Path,
    output_root: Path,
    max_new_cases: int | None = None,
    progress_callback=None,
) -> dict:
    """Executa o v14 de modo resumível, sem ler labels ou métricas."""

    if max_new_cases is not None and max_new_cases < 1:
        raise PipelineError("max_new_cases deve ser positivo.")
    bundle_root = Path(bundle_root).resolve()
    bundle, protocol, health = _validate_context(
        bundle_root=bundle_root,
        protocol_path=protocol_path,
        config_path=config_path,
    )
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
            progress_callback(
                {
                    "index": index,
                    "case_count": bundle["case_count"],
                    "case_id": case_id,
                    "classification": result["classification"],
                    "choice_probabilities": result["choice_probabilities"],
                    "request_elapsed_seconds": result["request_elapsed_seconds"],
                    "reused": reused,
                }
            )
    return _write_progress(
        output_root=output_root,
        protocol=protocol,
        bundle=bundle,
        predictions=predictions,
    )

