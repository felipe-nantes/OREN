"""Scorer v18 do atlas axial em blocos sequenciais para o MedGemma 4B."""
from __future__ import annotations

import base64
import json
import math
import statistics
import time
from pathlib import Path
from urllib.request import Request

from dtwin.benchmark.openswisshcc_axial_atlas_score import (
    INSTRUCTION as V17_INSTRUCTION,
    _load_json,
    _load_protocol as _load_v17_protocol,
    _validate_case_frames,
    score_log_odds,
    validate_atlas_bundle,
)
from dtwin.benchmark.openswisshcc_highdimensional_inference import (
    _atomic_json,
    _canonical_hash,
    _request_json,
)
from dtwin.benchmark.openswisshcc_volume_score import (
    CHOICES,
    CONTRACT,
    SCORING_METHOD,
    _score_url,
    _validate_score_response,
)
from dtwin.core import PipelineError, sha256_of
from dtwin.medgemma_client import load_screening_config


PROTOCOL_SCHEMA = "argos-openswisshcc-v18-atlas-chunk-score-protocol-v2"
PREDICTION_SCHEMA = "argos-openswisshcc-v18-atlas-chunk-score-prediction-v2"
SUMMARY_SCHEMA = "argos-openswisshcc-v18-atlas-chunk-score-summary-v2"
CHUNK_SIZE = 5  # mínimo aceito pelo contrato HTTP
MAX_CHUNKS = 4
CASE_TIME_GATE_SECONDS = 180.0
INSTRUCTION = (
    V17_INSTRUCTION
    + " Nesta chamada voce recebe apenas um bloco sequencial do atlas completo. "
    "Decida somente sobre a evidencia deste bloco, sem presumir o conteudo dos demais blocos."
)
QUERY_TEMPLATE = (
    "Bloco {chunk_number}/{chunk_count}, contendo os frames sequenciais {first_frame} a "
    "{last_frame} de um atlas com {total_frames} frames. Examine todos os quadrantes reais. "
    "Classifique POSITIVA somente se este bloco mostrar lesao focal hepatica suspeita persistente; "
    "NEGATIVA se este bloco nao mostrar lesao focal suspeita; INCONCLUSIVA apenas se a qualidade "
    "deste bloco impedir a avaliacao. Complete somente o valor e feche o JSON iniciado."
)


def partition_frame_indices(frame_count: int, chunk_size: int = CHUNK_SIZE) -> list[list[int]]:
    if isinstance(frame_count, bool) or not isinstance(frame_count, int) or frame_count < chunk_size:
        raise PipelineError("Quantidade de frames v18 deve atender ao mínimo do gateway.")
    if isinstance(chunk_size, bool) or not isinstance(chunk_size, int) or chunk_size < 1:
        raise PipelineError("Tamanho de bloco v18 deve ser positivo.")
    chunk_count = min(MAX_CHUNKS, max(1, frame_count // chunk_size))
    base, remainder = divmod(frame_count, chunk_count)
    sizes = [base + (1 if index < remainder else 0) for index in range(chunk_count)]
    chunks, start = [], 0
    for size in sizes:
        chunks.append(list(range(start, start + size)))
        start += size
    flattened = [index for chunk in chunks for index in chunk]
    if flattened != list(range(frame_count)) or len(set(flattened)) != frame_count:
        raise PipelineError("Particionamento v18 não cobre cada frame exatamente uma vez.")
    return chunks


def freeze_chunk_protocol(
    *,
    atlas_root: Path,
    v17_score_protocol_path: Path,
    config_path: Path,
    output_path: Path,
) -> dict:
    bundle = validate_atlas_bundle(atlas_root)
    if bundle["case_count"] != 87 or bundle["maximum_frames"] > CHUNK_SIZE * MAX_CHUNKS:
        raise PipelineError("v18 exige o atlas full87 com no máximo quatro blocos.")
    source = _load_v17_protocol(v17_score_protocol_path)
    med = load_screening_config(config_path)["medgemma"]
    if (
        source["atlas_cohort_sha256"] != bundle["cohort_sha256"]
        or source["case_ids"] != bundle["case_ids"]
        or source["model_id"] != med["model_id"]
        or source["model_version"] != med["model_version"]
    ):
        raise PipelineError("Atlas, modelo ou protocolo fonte divergiram para v18.")
    chunk_counts = [len(partition_frame_indices(case["frame_count"])) for case in bundle["cases"]]
    base = {
        "schema_version": PROTOCOL_SCHEMA,
        "status": "frozen_before_v18_development_inference",
        "development_labels_previously_opened": True,
        "ground_truth_available_to_inference": False,
        "source_v17_score_protocol_signature": source["protocol_signature"],
        "atlas_cohort_sha256": bundle["cohort_sha256"],
        "case_ids": bundle["case_ids"],
        "case_count": bundle["case_count"],
        "model_id": med["model_id"],
        "model_version": med["model_version"],
        "contract": CONTRACT,
        "endpoint_url": _score_url(str(med["endpoint_url"])),
        "instruction": INSTRUCTION,
        "query_template": QUERY_TEMPLATE,
        "scoring_method": SCORING_METHOD,
        "choices": list(CHOICES),
        "minimum_frames_per_chunk": CHUNK_SIZE,
        "partition": "balanced_max_four_chunks_minimum_five_frames",
        "maximum_chunks_per_case": MAX_CHUNKS,
        "observed_chunk_count_range": [min(chunk_counts), max(chunk_counts)],
        "automatic_retries": 0,
        "aggregation": "maximum_chunk_log_odds_positive_vs_negative",
        "case_time_gate_seconds": CASE_TIME_GATE_SECONDS,
        "evaluation": {
            "primary_estimator": "leave_one_out_threshold_fit_on_n_minus_1_only",
            "minimum_sensitivity": 0.75,
            "minimum_specificity": 0.75,
            "inconclusive_counted_as_error_for_categorical_diagnostic": True,
        },
        "ground_truth_read_during_inference": False,
        "metrics_calculated_during_inference": False,
        "holdout_opened": False,
        "research_only": True,
        "clinical_use_allowed": False,
        "requires_human_review": True,
    }
    protocol = {**base, "protocol_signature": _canonical_hash(base)}
    output = Path(output_path)
    if output.exists():
        if _load_json(output, "Protocolo v18") != protocol:
            raise PipelineError("Protocolo v18 existente diverge; sobrescrita recusada.")
        return protocol
    output.parent.mkdir(parents=True, exist_ok=True)
    _atomic_json(output, protocol)
    return protocol


def _load_protocol(path: Path) -> dict:
    protocol = _load_json(path, "Protocolo v18")
    signature = protocol.pop("protocol_signature", None)
    if signature != _canonical_hash(protocol):
        raise PipelineError("Assinatura do protocolo v18 diverge.")
    protocol["protocol_signature"] = signature
    if (
        protocol.get("schema_version") != PROTOCOL_SCHEMA
        or protocol.get("status") != "frozen_before_v18_development_inference"
        or protocol.get("development_labels_previously_opened") is not True
        or protocol.get("ground_truth_available_to_inference") is not False
        or protocol.get("minimum_frames_per_chunk") != CHUNK_SIZE
        or protocol.get("partition") != "balanced_max_four_chunks_minimum_five_frames"
        or protocol.get("maximum_chunks_per_case") != MAX_CHUNKS
        or protocol.get("automatic_retries") != 0
        or protocol.get("aggregation") != "maximum_chunk_log_odds_positive_vs_negative"
        or protocol.get("holdout_opened") is not False
    ):
        raise PipelineError("Protocolo v18 inválido ou não congelado.")
    return protocol


def _validate_context(*, atlas_root: Path, protocol_path: Path, config_path: Path) -> tuple[dict, dict, dict]:
    bundle = validate_atlas_bundle(atlas_root)
    protocol = _load_protocol(protocol_path)
    med = load_screening_config(config_path)["medgemma"]
    if (
        protocol["atlas_cohort_sha256"] != bundle["cohort_sha256"]
        or protocol["case_ids"] != bundle["case_ids"]
        or protocol["model_id"] != med["model_id"]
        or protocol["model_version"] != med["model_version"]
        or protocol["endpoint_url"] != _score_url(str(med["endpoint_url"]))
    ):
        raise PipelineError("Contexto v18 divergiu após o congelamento.")
    health = _request_json(Request(str(med["healthcheck_url"]), headers={"Accept": "application/json"}, method="GET"), timeout=15)
    if (
        health.get("status") != "ready"
        or health.get("model_id") != protocol["model_id"]
        or health.get("model_version") != protocol["model_version"]
        or health.get("volume_score_contract") != CONTRACT
        or health.get("volume_score_method") != SCORING_METHOD
        or health.get("volume_score_supported") is not True
    ):
        raise PipelineError("Gateway MedGemma incompatível com v18.")
    return bundle, protocol, health


def _chunk_query(*, number: int, count: int, indices: list[int], total: int) -> str:
    return QUERY_TEMPLATE.format(
        chunk_number=number,
        chunk_count=count,
        first_frame=indices[0] + 1,
        last_frame=indices[-1] + 1,
        total_frames=total,
    )


def _score_case(*, case: dict, protocol: dict, health: dict, out_path: Path) -> dict:
    images = _validate_case_frames(case["case_dir"], case["manifest"])
    chunks = partition_frame_indices(len(images))
    if len(chunks) > MAX_CHUNKS:
        raise PipelineError("Caso v18 excede o máximo congelado de blocos.")
    results = []
    case_started = time.monotonic()
    for chunk_number, indices in enumerate(chunks, 1):
        query = _chunk_query(number=chunk_number, count=len(chunks), indices=indices, total=len(images))
        payload = {
            "contract": CONTRACT,
            "model_id": protocol["model_id"],
            "model_version": protocol["model_version"],
            "instruction": protocol["instruction"],
            "images": [
                {"mime_type": "image/png", "base64": base64.b64encode(images[index]).decode("ascii")}
                for index in indices
            ],
            "query": query,
            "scoring": {"response_prefix": '{"resultado_hipotese":"'},
        }
        request = Request(protocol["endpoint_url"], data=json.dumps(payload).encode("utf-8"), headers={"Content-Type": "application/json", "Accept": "application/json"}, method="POST")
        started = time.monotonic()
        response = _request_json(request, timeout=CASE_TIME_GATE_SECONDS)
        elapsed = time.monotonic() - started
        validated = _validate_score_response(response, protocol=protocol, slice_count=len(indices))
        results.append(
            {
                "chunk_number": chunk_number,
                "chunk_count": len(chunks),
                "frame_numbers": [index + 1 for index in indices],
                "query_sha256": _canonical_hash({"query": query}),
                "classification": validated["classification"],
                "choice_probabilities": validated["choice_probabilities"],
                "choice_token_metadata": validated["choice_token_metadata"],
                "tie_detected": validated["tie_detected"],
                "log_odds_positive_vs_negative": score_log_odds(validated["choice_probabilities"]),
                "request_elapsed_seconds": round(elapsed, 4),
                "gateway_timings_seconds": response.get("timings_seconds"),
            }
        )
    case_elapsed = time.monotonic() - case_started
    represented = [number for result in results for number in result["frame_numbers"]]
    if represented != list(range(1, len(images) + 1)) or len(set(represented)) != len(images):
        raise PipelineError("Cobertura de frames v18 incompleta ou duplicada.")
    if case_elapsed > CASE_TIME_GATE_SECONDS:
        raise PipelineError(f"Caso {case['case_id']} excedeu 180 segundos no v18.")
    selected = max(results, key=lambda item: (item["log_odds_positive_vs_negative"], -item["chunk_number"]))
    result = {
        "schema_version": PREDICTION_SCHEMA,
        "status": "technical_passed",
        "case_id": case["case_id"],
        "protocol_signature": protocol["protocol_signature"],
        "atlas_manifest_sha256": case["manifest_sha256"],
        "atlas_set_sha256": case["atlas_set_sha256"],
        "frame_count": len(images),
        "chunk_count": len(results),
        "chunk_frame_counts": [len(item["frame_numbers"]) for item in results],
        "represented_frame_numbers": represented,
        "chunks": results,
        "aggregation": protocol["aggregation"],
        "selected_chunk_number": selected["chunk_number"],
        "classification": selected["classification"],
        "log_odds_positive_vs_negative": selected["log_odds_positive_vs_negative"],
        "case_elapsed_seconds": round(case_elapsed, 4),
        "case_time_gate_seconds": CASE_TIME_GATE_SECONDS,
        "time_gate_passed": True,
        "health_model_id": health.get("model_id"),
        "development_labels_previously_opened": True,
        "ground_truth_read_during_inference": False,
        "metrics_calculated_during_inference": False,
        "holdout_opened": False,
        "research_only": True,
        "clinical_use_allowed": False,
        "requires_human_review": True,
    }
    _atomic_json(out_path, result)
    return result


def _validate_existing(path: Path, case: dict, protocol: dict) -> dict:
    result = _load_json(path, "Predição v18")
    if (
        result.get("schema_version") != PREDICTION_SCHEMA
        or result.get("status") != "technical_passed"
        or result.get("case_id") != case["case_id"]
        or result.get("protocol_signature") != protocol["protocol_signature"]
        or result.get("atlas_manifest_sha256") != case["manifest_sha256"]
        or result.get("atlas_set_sha256") != case["atlas_set_sha256"]
        or result.get("holdout_opened") is not False
        or result.get("ground_truth_read_during_inference") is not False
        or result.get("time_gate_passed") is not True
    ):
        raise PipelineError("Predição v18 existente diverge ou está contaminada.")
    expected = list(range(1, case["frame_count"] + 1))
    if result.get("represented_frame_numbers") != expected:
        raise PipelineError("Predição v18 reutilizada perdeu cobertura de frames.")
    chunks = result.get("chunks")
    if not isinstance(chunks, list) or len(chunks) != len(partition_frame_indices(case["frame_count"])):
        raise PipelineError("Predição v18 reutilizada possui blocos inválidos.")
    best = max(float(item["log_odds_positive_vs_negative"]) for item in chunks)
    if not math.isclose(best, float(result.get("log_odds_positive_vs_negative")), rel_tol=0, abs_tol=1e-12):
        raise PipelineError("Agregação v18 reutilizada diverge.")
    return result


def run_chunk_batch(
    *,
    atlas_root: Path,
    protocol_path: Path,
    config_path: Path,
    output_root: Path,
    max_new_cases: int | None = None,
    progress_callback=None,
) -> dict:
    if max_new_cases is not None and max_new_cases < 1:
        raise PipelineError("max_new_cases v18 deve ser positivo.")
    bundle, protocol, health = _validate_context(atlas_root=atlas_root, protocol_path=protocol_path, config_path=config_path)
    output_root = Path(output_root).resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    predictions_dir = output_root / "predictions"
    predictions_dir.mkdir(exist_ok=True)
    context = {
        "schema_version": "argos-openswisshcc-v18-atlas-chunk-run-context-v1",
        "protocol_signature": protocol["protocol_signature"],
        "atlas_cohort_sha256": bundle["cohort_sha256"],
        "case_ids": bundle["case_ids"],
        "ground_truth_read_during_inference": False,
        "holdout_opened": False,
    }
    context_path = output_root / "run_context.json"
    if context_path.exists() and _load_json(context_path, "Contexto v18") != context:
        raise PipelineError("Diretório v18 pertence a outro protocolo.")
    if not context_path.exists():
        _atomic_json(context_path, context)
    results, new_count = [], 0
    for index, case in enumerate(bundle["cases"], 1):
        path = predictions_dir / f"{case['case_id']}.json"
        reused = path.exists()
        if reused:
            result = _validate_existing(path, case, protocol)
        elif max_new_cases is not None and new_count >= max_new_cases:
            continue
        else:
            result = _score_case(case=case, protocol=protocol, health=health, out_path=path)
            new_count += 1
        results.append(result)
        if progress_callback:
            progress_callback({"index": index, "case_count": bundle["case_count"], "case_id": case["case_id"], "chunk_count": result["chunk_count"], "case_elapsed_seconds": result["case_elapsed_seconds"], "reused": reused})
    records = [
        {
            "case_id": result["case_id"],
            "prediction_sha256": sha256_of(predictions_dir / f"{result['case_id']}.json"),
            "classification": result["classification"],
            "log_odds_positive_vs_negative": result["log_odds_positive_vs_negative"],
            "chunk_count": result["chunk_count"],
            "case_elapsed_seconds": result["case_elapsed_seconds"],
        }
        for result in results
    ]
    complete = len(records) == bundle["case_count"]
    summary = {
        "schema_version": SUMMARY_SCHEMA,
        "status": "complete" if complete else "partial",
        "protocol_signature": protocol["protocol_signature"],
        "case_count": bundle["case_count"],
        "completed_case_count": len(records),
        "pending_case_count": bundle["case_count"] - len(records),
        "predictions": records,
        "request_count": sum(result["chunk_count"] for result in results),
        "case_timing_seconds": None,
        "development_labels_previously_opened": True,
        "ground_truth_read_during_inference": False,
        "metrics_calculated_during_inference": False,
        "holdout_opened": False,
        "research_only": True,
        "clinical_use_allowed": False,
        "requires_human_review": True,
    }
    if complete:
        timings = [float(result["case_elapsed_seconds"]) for result in results]
        summary["case_timing_seconds"] = {"minimum": min(timings), "median": statistics.median(timings), "mean": statistics.fmean(timings), "maximum": max(timings), "all_within_180": all(value <= CASE_TIME_GATE_SECONDS for value in timings)}
    _atomic_json(output_root / "summary.json", summary)
    return summary
