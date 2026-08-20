"""Scorer cego v19: atlas axial v17 com contexto RAG textual congelado."""
from __future__ import annotations

import base64
import hashlib
import json
import math
import statistics
import time
from pathlib import Path
from typing import Any
from urllib.request import Request

from dtwin.benchmark.openswisshcc_axial_atlas_score import (
    CASE_TIME_GATE_SECONDS,
    MAX_IMAGE_EDGE,
    _load_json,
    _validate_case_frames,
    atlas_query,
    score_log_odds,
    validate_atlas_bundle,
)
from dtwin.benchmark.openswisshcc_axial_atlas_score import (
    INSTRUCTION as V17_INSTRUCTION,
)
from dtwin.benchmark.openswisshcc_axial_atlas_score import (
    _load_protocol as _load_v17_protocol,
)
from dtwin.benchmark.openswisshcc_highdimensional_inference import (
    RESPONSE_PREFIX,
    _atomic_json,
    _canonical_hash,
    _request_json,
)
from dtwin.benchmark.openswisshcc_volume_score import (
    CHOICES,
    CONTRACT,
    PROBABILITY_TOLERANCE,
    SCORING_METHOD,
    _score_url,
    _validate_score_response,
)
from dtwin.core import PipelineError, sha256_of
from dtwin.medgemma_client import effective_config_sha256, load_screening_config
from dtwin.rag import build_rag_context
from dtwin.rag.grounding import build_rag_prompt_addendum

PROTOCOL_SCHEMA = "argos-openswisshcc-v19-atlas-rag-score-protocol-v1"
PREDICTION_SCHEMA = "argos-openswisshcc-v19-atlas-rag-score-prediction-v1"
RUN_CONTEXT_SCHEMA = "argos-openswisshcc-v19-atlas-rag-run-context-v1"
SUMMARY_SCHEMA = "argos-openswisshcc-v19-atlas-rag-score-summary-v1"
RAG_POLICY = "static_retrieval_frozen_before_blind_inference_v1"
AGGREGATION = "single_atlas_rag_log_odds_positive_vs_negative"


def _text_sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def rag_fingerprint(context: dict[str, Any]) -> dict[str, Any]:
    """Retém somente conteúdo determinístico e auditável do retrieval."""

    if context.get("enabled") is not True:
        raise PipelineError("v19 exige contexto RAG habilitado.")
    sources = context.get("sources")
    queries = context.get("queries")
    if not isinstance(sources, list) or not sources or not isinstance(queries, list):
        raise PipelineError("Contexto RAG v19 sem fontes ou consultas.")
    source_records = []
    for expected_number, source in enumerate(sources, 1):
        source_id = f"S{expected_number}"
        if source.get("source_id") != source_id or not str(source.get("text", "")).strip():
            raise PipelineError("Fonte RAG v19 inválida ou fora de ordem.")
        source_records.append(
            {
                "source_id": source_id,
                "chunk_id": str(source.get("chunk_id", "")),
                "doc_id": str(source.get("doc_id", "")),
                "source_sha256": str(source.get("sha256", "")),
                "text_sha256": _text_sha256(str(source["text"])),
                "score": float(source.get("score", 0.0)),
            }
        )
    query_records = []
    for query in queries:
        kept = query.get("kept_results")
        if not isinstance(kept, list):
            raise PipelineError("Consulta RAG v19 sem resultados auditáveis.")
        query_records.append(
            {
                "id": str(query.get("id", "")),
                "query_sha256": _text_sha256(str(query.get("query", ""))),
                "kept_chunk_ids": [str(item.get("chunk_id", "")) for item in kept],
            }
        )
    return {
        "retriever": context.get("retriever"),
        "corpus_version": context.get("corpus_version"),
        "index_path": context.get("index_path"),
        "index_sha256": context.get("index_sha256"),
        "retrieval_eval": context.get("retrieval_eval"),
        "retrieval_eval_sha256": context.get("retrieval_eval_sha256"),
        "top_k": context.get("top_k"),
        "max_sources": context.get("max_sources"),
        "max_chunk_chars": context.get("max_chunk_chars"),
        "min_score": context.get("min_score"),
        "source_count": context.get("source_count"),
        "query_count": context.get("query_count"),
        "context_sha256": context.get("context_sha256"),
        "queries": query_records,
        "sources": source_records,
    }


def _rag_material(config_path: Path, repo_root: Path) -> tuple[dict, dict, str, str]:
    config = load_screening_config(config_path)
    context = build_rag_context(config=config, repo_root=repo_root)
    fingerprint = rag_fingerprint(context)
    addendum = build_rag_prompt_addendum(context)
    instruction = f"{V17_INSTRUCTION}\n\n{addendum}".strip()
    max_chars = int(config["medgemma"].get("max_prompt_chars", 12000))
    if len(instruction) > max_chars:
        raise PipelineError("Instrução RAG v19 excede max_prompt_chars.")
    return config, fingerprint, addendum, instruction


def freeze_rag_protocol(
    *,
    atlas_root: Path,
    v17_score_protocol_path: Path,
    config_path: Path,
    output_path: Path,
    repo_root: Path | None = None,
) -> dict:
    repo_root = Path(repo_root or Path.cwd()).resolve()
    bundle = validate_atlas_bundle(atlas_root)
    if bundle["case_count"] != 87:
        raise PipelineError("v19 exige o atlas full87 aprovado.")
    source = _load_v17_protocol(v17_score_protocol_path)
    config, fingerprint, addendum, instruction = _rag_material(
        config_path, repo_root
    )
    med = config["medgemma"]
    if (
        source["atlas_cohort_sha256"] != bundle["cohort_sha256"]
        or source["case_ids"] != bundle["case_ids"]
        or source["model_id"] != med["model_id"]
        or source["model_version"] != med["model_version"]
    ):
        raise PipelineError("Atlas, modelo ou protocolo fonte divergiram para v19.")
    base = {
        "schema_version": PROTOCOL_SCHEMA,
        "status": "frozen_before_v19_blind_development_inference",
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
        "effective_config_sha256": effective_config_sha256(config),
        "rag_policy": RAG_POLICY,
        "rag_fingerprint": fingerprint,
        "rag_addendum_sha256": _text_sha256(addendum),
        "instruction": instruction,
        "instruction_sha256": _text_sha256(instruction),
        "scoring": {
            "response_prefix": RESPONSE_PREFIX,
            "choices": list(CHOICES),
            "method": SCORING_METHOD,
            "requests_per_case": 1,
            "automatic_retries": 0,
            "score": "log_odds_positive_vs_negative",
            "epsilon": 1e-8,
            "probability_tolerance": PROBABILITY_TOLERANCE,
        },
        "aggregation": AGGREGATION,
        "case_time_gate_seconds": CASE_TIME_GATE_SECONDS,
        "maximum_image_edge": MAX_IMAGE_EDGE,
        "evaluation": {
            "primary_estimator": "leave_one_out_threshold_fit_on_n_minus_1_only",
            "minimum_sensitivity": 0.75,
            "minimum_specificity": 0.75,
            "inconclusive_counted_as_error": True,
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
        if _load_json(output, "Protocolo v19") != protocol:
            raise PipelineError("Protocolo v19 existente diverge; sobrescrita recusada.")
        return protocol
    output.parent.mkdir(parents=True, exist_ok=True)
    _atomic_json(output, protocol)
    return protocol


def _load_protocol(path: Path) -> dict:
    protocol = _load_json(path, "Protocolo v19")
    signature = protocol.pop("protocol_signature", None)
    if signature != _canonical_hash(protocol):
        raise PipelineError("Assinatura do protocolo v19 diverge.")
    protocol["protocol_signature"] = signature
    scoring = protocol.get("scoring", {})
    if (
        protocol.get("schema_version") != PROTOCOL_SCHEMA
        or protocol.get("status") != "frozen_before_v19_blind_development_inference"
        or protocol.get("development_labels_previously_opened") is not True
        or protocol.get("ground_truth_available_to_inference") is not False
        or protocol.get("rag_policy") != RAG_POLICY
        or protocol.get("rag_addendum_sha256") is None
        or protocol.get("instruction_sha256") != _text_sha256(str(protocol.get("instruction", "")))
        or scoring.get("method") != SCORING_METHOD
        or scoring.get("choices") != list(CHOICES)
        or scoring.get("requests_per_case") != 1
        or scoring.get("automatic_retries") != 0
        or protocol.get("aggregation") != AGGREGATION
        or protocol.get("case_time_gate_seconds") != CASE_TIME_GATE_SECONDS
        or protocol.get("holdout_opened") is not False
    ):
        raise PipelineError("Protocolo v19 inválido ou não congelado.")
    return protocol


def _validate_context(
    *, atlas_root: Path, protocol_path: Path, config_path: Path, repo_root: Path
) -> tuple[dict, dict, dict]:
    bundle = validate_atlas_bundle(atlas_root)
    protocol = _load_protocol(protocol_path)
    config, fingerprint, addendum, instruction = _rag_material(config_path, repo_root)
    med = config["medgemma"]
    if (
        protocol["atlas_cohort_sha256"] != bundle["cohort_sha256"]
        or protocol["case_ids"] != bundle["case_ids"]
        or protocol["model_id"] != med["model_id"]
        or protocol["model_version"] != med["model_version"]
        or protocol["endpoint_url"] != _score_url(str(med["endpoint_url"]))
        or protocol["effective_config_sha256"] != effective_config_sha256(config)
        or protocol["rag_fingerprint"] != fingerprint
        or protocol["rag_addendum_sha256"] != _text_sha256(addendum)
        or protocol["instruction"] != instruction
    ):
        raise PipelineError("Config, corpus RAG, atlas ou protocolo v19 divergiram.")
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
        or int(health.get("volume_score_max_image_edge", 0)) < MAX_IMAGE_EDGE
    ):
        raise PipelineError("Gateway MedGemma incompatível com v19.")
    return bundle, protocol, health


def _score_case(*, case: dict, protocol: dict, health: dict, output_path: Path) -> dict:
    images = _validate_case_frames(case["case_dir"], case["manifest"])
    query = atlas_query(case["manifest"])
    payload = {
        "contract": CONTRACT,
        "model_id": protocol["model_id"],
        "model_version": protocol["model_version"],
        "instruction": protocol["instruction"],
        "images": [
            {"mime_type": "image/png", "base64": base64.b64encode(raw).decode("ascii")}
            for raw in images
        ],
        "query": query,
        "scoring": {"response_prefix": protocol["scoring"]["response_prefix"]},
    }
    request = Request(
        protocol["endpoint_url"],
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    started = time.monotonic()
    response = _request_json(request, timeout=CASE_TIME_GATE_SECONDS)
    elapsed = time.monotonic() - started
    if elapsed > CASE_TIME_GATE_SECONDS:
        raise PipelineError(f"Caso {case['case_id']} excedeu 180 segundos no v19.")
    validated = _validate_score_response(response, protocol=protocol, slice_count=len(images))
    result = {
        "schema_version": PREDICTION_SCHEMA,
        "status": "technical_passed",
        "case_id": case["case_id"],
        "protocol_signature": protocol["protocol_signature"],
        "atlas_manifest_sha256": case["manifest_sha256"],
        "atlas_set_sha256": case["atlas_set_sha256"],
        "frame_count": len(images),
        "query_sha256": _canonical_hash({"query": query}),
        "rag_context_sha256": protocol["rag_fingerprint"]["context_sha256"],
        "rag_addendum_sha256": protocol["rag_addendum_sha256"],
        "classification": validated["classification"],
        "choice_probabilities": validated["choice_probabilities"],
        "choice_token_metadata": validated["choice_token_metadata"],
        "tie_detected": validated["tie_detected"],
        "log_odds_positive_vs_negative": score_log_odds(validated["choice_probabilities"]),
        "request_elapsed_seconds": round(elapsed, 4),
        "gateway_timings_seconds": response.get("timings_seconds"),
        "time_gate_passed": True,
        "health_model_id": health.get("model_id"),
        "ground_truth_read_during_inference": False,
        "lesion_mask_read_during_inference": False,
        "metrics_calculated_during_inference": False,
        "holdout_opened": False,
        "research_only": True,
        "clinical_use_allowed": False,
        "requires_human_review": True,
    }
    _atomic_json(output_path, result)
    return result


def _validate_existing(path: Path, case: dict, protocol: dict) -> dict:
    result = _load_json(path, "Predição v19")
    if (
        result.get("schema_version") != PREDICTION_SCHEMA
        or result.get("status") != "technical_passed"
        or result.get("case_id") != case["case_id"]
        or result.get("protocol_signature") != protocol["protocol_signature"]
        or result.get("atlas_manifest_sha256") != case["manifest_sha256"]
        or result.get("atlas_set_sha256") != case["atlas_set_sha256"]
        or result.get("frame_count") != case["frame_count"]
        or result.get("query_sha256") != _canonical_hash({"query": atlas_query(case["manifest"])})
        or result.get("rag_context_sha256") != protocol["rag_fingerprint"]["context_sha256"]
        or result.get("rag_addendum_sha256") != protocol["rag_addendum_sha256"]
        or result.get("time_gate_passed") is not True
        or float(result.get("request_elapsed_seconds", 181)) > CASE_TIME_GATE_SECONDS
        or result.get("ground_truth_read_during_inference") is not False
        or result.get("lesion_mask_read_during_inference") is not False
        or result.get("metrics_calculated_during_inference") is not False
        or result.get("holdout_opened") is not False
    ):
        raise PipelineError("Predição v19 existente diverge ou está contaminada.")
    response = {
        "contract": CONTRACT,
        "model_id": protocol["model_id"],
        "model_version": protocol["model_version"],
        "slice_count": case["frame_count"],
        "scoring_method": SCORING_METHOD,
        "choice": result.get("classification"),
        "choice_probabilities": result.get("choice_probabilities"),
        "choice_token_metadata": result.get("choice_token_metadata"),
        "tie_detected": result.get("tie_detected"),
        "research_only": True,
        "clinical_use_allowed": False,
        "requires_human_review": True,
    }
    validated = _validate_score_response(response, protocol=protocol, slice_count=case["frame_count"])
    expected_score = score_log_odds(validated["choice_probabilities"])
    if not math.isclose(
        float(result.get("log_odds_positive_vs_negative")), expected_score, rel_tol=0, abs_tol=1e-12
    ):
        raise PipelineError("Score v19 reutilizado foi alterado.")
    return result


def run_rag_batch(
    *,
    atlas_root: Path,
    protocol_path: Path,
    config_path: Path,
    output_root: Path,
    repo_root: Path | None = None,
    max_new_cases: int | None = None,
    progress_callback=None,
) -> dict:
    if max_new_cases is not None and max_new_cases < 1:
        raise PipelineError("max_new_cases v19 deve ser positivo.")
    repo_root = Path(repo_root or Path.cwd()).resolve()
    bundle, protocol, health = _validate_context(
        atlas_root=atlas_root,
        protocol_path=protocol_path,
        config_path=config_path,
        repo_root=repo_root,
    )
    output_root = Path(output_root).resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    predictions_dir = output_root / "predictions"
    predictions_dir.mkdir(exist_ok=True)
    run_context = {
        "schema_version": RUN_CONTEXT_SCHEMA,
        "protocol_signature": protocol["protocol_signature"],
        "atlas_cohort_sha256": bundle["cohort_sha256"],
        "rag_context_sha256": protocol["rag_fingerprint"]["context_sha256"],
        "case_ids": bundle["case_ids"],
        "ground_truth_read_during_inference": False,
        "lesion_mask_read_during_inference": False,
        "metrics_calculated_during_inference": False,
        "holdout_opened": False,
    }
    context_path = output_root / "run_context.json"
    if context_path.exists() and _load_json(context_path, "Contexto v19") != run_context:
        raise PipelineError("Diretório v19 pertence a outro protocolo.")
    if not context_path.exists():
        _atomic_json(context_path, run_context)
    results, new_count = [], 0
    for index, case in enumerate(bundle["cases"], 1):
        path = predictions_dir / f"{case['case_id']}.json"
        reused = path.exists()
        if reused:
            result = _validate_existing(path, case, protocol)
        elif max_new_cases is not None and new_count >= max_new_cases:
            continue
        else:
            result = _score_case(
                case=case, protocol=protocol, health=health, output_path=path
            )
            new_count += 1
        results.append(result)
        if progress_callback:
            progress_callback(
                {
                    "index": index,
                    "case_count": bundle["case_count"],
                    "case_id": case["case_id"],
                    "frame_count": case["frame_count"],
                    "request_elapsed_seconds": result["request_elapsed_seconds"],
                    "reused": reused,
                }
            )
    records = [
        {
            "case_id": result["case_id"],
            "prediction_sha256": sha256_of(predictions_dir / f"{result['case_id']}.json"),
            "classification": result["classification"],
            "log_odds_positive_vs_negative": result["log_odds_positive_vs_negative"],
            "request_elapsed_seconds": result["request_elapsed_seconds"],
        }
        for result in results
    ]
    complete = len(records) == bundle["case_count"]
    summary = {
        "schema_version": SUMMARY_SCHEMA,
        "status": "complete" if complete else "partial",
        "protocol_signature": protocol["protocol_signature"],
        "rag_context_sha256": protocol["rag_fingerprint"]["context_sha256"],
        "case_count": bundle["case_count"],
        "completed_case_count": len(records),
        "pending_case_count": bundle["case_count"] - len(records),
        "predictions": records,
        "request_count": len(records),
        "request_timing_seconds": None,
        "ground_truth_read_during_inference": False,
        "lesion_mask_read_during_inference": False,
        "metrics_calculated_during_inference": False,
        "holdout_opened": False,
        "accuracy_claimed": False,
        "research_only": True,
        "clinical_use_allowed": False,
        "requires_human_review": True,
    }
    if complete:
        timings = [float(result["request_elapsed_seconds"]) for result in results]
        summary["request_timing_seconds"] = {
            "minimum": min(timings),
            "median": statistics.median(timings),
            "mean": statistics.fmean(timings),
            "maximum": max(timings),
            "all_within_180": all(value <= CASE_TIME_GATE_SECONDS for value in timings),
        }
    _atomic_json(output_root / "summary.json", summary)
    return summary

