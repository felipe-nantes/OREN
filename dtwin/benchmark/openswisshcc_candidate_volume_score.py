"""Frozen blind scoring for v16 candidate-centred multisequence MRI stacks."""
from __future__ import annotations

import base64
import json
import math
import re
import statistics
import time
from pathlib import Path
from urllib.request import Request

from PIL import Image

from dtwin.benchmark.openswisshcc_candidate_volume import (
    CANDIDATE_SCHEMA,
    CASE_SCHEMA,
    COHORT_SCHEMA,
)
from dtwin.benchmark.openswisshcc_candidate_volume import (
    CONTRACT as VOLUME_INPUT_CONTRACT,
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
from dtwin.medgemma_client import load_screening_config

REVIEW_SCHEMA = "argos-openswisshcc-candidate-volume-review-v16"
PROTOCOL_SCHEMA = "argos-openswisshcc-candidate-volume-score-protocol-v16"
PREDICTION_SCHEMA = "argos-openswisshcc-candidate-volume-score-prediction-v16"
PROGRESS_SCHEMA = "argos-openswisshcc-candidate-volume-score-progress-v16"
SUMMARY_SCHEMA = "argos-openswisshcc-candidate-volume-score-summary-v16"
RUN_CONTEXT_SCHEMA = "argos-openswisshcc-candidate-volume-score-run-context-v16"
FRAME_MAP_VERSION = "ordered-role-ranges-v1"
AGGREGATION_METHOD = "maximum_candidate_log_odds_positive_vs_negative_v1"
CASE_TIME_GATE_SECONDS = 180.0
_CANDIDATE_DIR = re.compile(r"^candidate_[0-9]{3}$")
_FRAME_NAME = re.compile(r"^frame_[0-9]{3}_[a-z0-9_]+_z[0-9]{4}\.png$")

INSTRUCTION = (
    "Analise uma pequena pilha 3D multissequencia de RM hepatica centrada em uma regiao "
    "proposta por um localizador automatico. A proposta do localizador nao e evidencia de "
    "doenca e pode ser falso positivo ou fallback. O alvo exclusivo e lesao focal hepatica "
    "suspeita. Compare continuidade entre cortes adjacentes e concordancia entre T1 nativo, "
    "arterial, venoso, tardio, T2, DWI e ADC quando disponiveis. Estrutura vascular tubular "
    "continua, variante anatomica, alteracao perfusional sem massa, volume parcial e artefato "
    "nao devem ser classificados como patologia alvo. Nao presuma diagnostico pela selecao do ROI."
)
QUERY_TEMPLATE = (
    "Regiao {candidate_number}/{candidate_total}. Tipo de selecao: {selection_type}. "
    "Mapa dos frames na ordem recebida: {frame_map}. Classifique como POSITIVA somente se esta "
    "regiao contiver lesao focal hepatica suspeita sustentada pela continuidade ou concordancia "
    "multissequencia; NEGATIVA quando representar parenquima, vaso, variante, pseudolesao ou "
    "artefato sem lesao focal suspeita; INCONCLUSIVA apenas quando a qualidade impedir a separacao. "
    "Complete somente o valor e feche o JSON iniciado."
)


def _load_json(path: Path, description: str) -> dict:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PipelineError(f"{description} ausente ou invalido.") from exc
    if not isinstance(value, dict):
        raise PipelineError(f"{description} deve ser objeto JSON.")
    return value


def _safe_child(root: Path, relative: str) -> Path:
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()):
        raise PipelineError("Caminho v16 escapou da raiz autorizada.")
    return path


def _validate_candidate_stack(candidate_dir: Path, expected: dict) -> tuple[dict, list[bytes]]:
    candidate_dir = Path(candidate_dir).resolve()
    manifest_path = candidate_dir / "manifest.json"
    manifest = _load_json(manifest_path, "Manifesto candidato v16")
    gate = manifest.get("gate", {})
    if (
        manifest.get("schema") != CANDIDATE_SCHEMA
        or manifest.get("contract") != VOLUME_INPUT_CONTRACT
        or manifest.get("candidate_number") != expected.get("candidate_number")
        or manifest.get("frame_count") != expected.get("frame_count")
        or manifest.get("research_only") is not True
        or manifest.get("clinical_use_allowed") is not False
        or manifest.get("requires_human_review") is not True
        or gate.get("passed") is not True
        or gate.get("candidate_contour_rendered") is not False
        or gate.get("ground_truth_read") is not False
        or gate.get("dataset_lesion_mask_used") is not False
        or gate.get("phi_metadata_included") is not False
        or sha256_of(manifest_path) != expected.get("manifest_sha256")
    ):
        raise PipelineError("Stack candidato v16 violou manifesto, hash ou salvaguardas.")
    groups = manifest.get("groups")
    if not isinstance(groups, list) or not groups:
        raise PipelineError("Stack candidato v16 nao possui grupos.")
    frames = [frame for group in groups for frame in group.get("frames", [])]
    if manifest.get("frame_count") != len(frames) or not 5 <= len(frames) <= 29:
        raise PipelineError("Quantidade de frames candidata v16 invalida.")
    payloads, seen = [], set()
    for expected_order, frame in enumerate(frames, 1):
        filename = str(frame.get("filename", ""))
        if frame.get("order") != expected_order or not _FRAME_NAME.fullmatch(filename) or filename in seen:
            raise PipelineError("Ordem ou nome de frame v16 invalido.")
        seen.add(filename)
        path = _safe_child(candidate_dir, filename)
        if not path.is_file() or path.stat().st_size != int(frame.get("bytes", -1)) or sha256_of(path) != frame.get("sha256"):
            raise PipelineError("Frame v16 ausente ou adulterado.")
        with Image.open(path) as image:
            if image.format != "PNG" or image.mode != "RGB" or image.size != (384, 384):
                raise PipelineError("Frame v16 viola formato, modo ou dimensoes congeladas.")
            image.load()
        payloads.append(path.read_bytes())
    return manifest, payloads


def validate_candidate_volume_bundle(bundle_root: Path) -> dict:
    bundle_root = Path(bundle_root).resolve()
    cohort_path = bundle_root / "cohort_manifest.json"
    cohort = _load_json(cohort_path, "Manifesto de coorte v16")
    if (
        cohort.get("schema") != COHORT_SCHEMA
        or cohort.get("contract") != VOLUME_INPUT_CONTRACT
        or cohort.get("ground_truth_read") is not False
        or cohort.get("dataset_lesion_mask_used") is not False
        or cohort.get("holdout_opened") is not False
        or cohort.get("inference_executed") is not False
        or cohort.get("research_only") is not True
        or cohort.get("clinical_use_allowed") is not False
        or cohort.get("requires_human_review") is not True
    ):
        raise PipelineError("Coorte candidata v16 violou schema ou salvaguardas.")
    raw_cases = cohort.get("cases")
    if not isinstance(raw_cases, list) or len(raw_cases) != cohort.get("case_count") or not raw_cases:
        raise PipelineError("Lista de casos candidata v16 inconsistente.")
    cases, case_ids = [], []
    total_stacks = 0
    for record in raw_cases:
        case_id = str(record.get("case_id", ""))
        if not case_id.startswith("anon-") or case_id in case_ids:
            raise PipelineError("case_id candidato v16 invalido ou duplicado.")
        case_ids.append(case_id)
        case_dir = _safe_child(bundle_root, case_id)
        case_manifest_path = case_dir / "case_manifest.json"
        case_manifest = _load_json(case_manifest_path, "Manifesto de caso v16")
        if (
            case_manifest.get("schema") != CASE_SCHEMA
            or case_manifest.get("contract") != VOLUME_INPUT_CONTRACT
            or case_manifest.get("case_id") != case_id
            or case_manifest.get("candidate_stack_count") != record.get("candidate_stack_count")
            or case_manifest.get("gate", {}).get("passed") is not True
            or case_manifest.get("gate", {}).get("ground_truth_read") is not False
            or case_manifest.get("gate", {}).get("dataset_lesion_mask_used") is not False
            or case_manifest.get("gate", {}).get("phi_metadata_included") is not False
            or sha256_of(case_manifest_path) != record.get("case_manifest_sha256")
        ):
            raise PipelineError("Caso candidato v16 violou manifesto, hash ou salvaguardas.")
        stacks = case_manifest.get("candidate_stacks")
        if not isinstance(stacks, list) or not 1 <= len(stacks) <= 5 or len(stacks) != case_manifest["candidate_stack_count"]:
            raise PipelineError("Quantidade de stacks por caso v16 invalida.")
        validated_stacks = []
        for number, stack in enumerate(stacks, 1):
            relative = str(stack.get("relative_directory", ""))
            if stack.get("candidate_number") != number or not _CANDIDATE_DIR.fullmatch(relative):
                raise PipelineError("Diretorio/ordem candidata v16 invalido.")
            candidate_dir = _safe_child(case_dir, relative)
            manifest, _ = _validate_candidate_stack(candidate_dir, stack)
            validated_stacks.append(
                {
                    **stack,
                    "candidate_dir": candidate_dir,
                    "fallback_no_candidate": manifest["fallback_no_candidate"],
                }
            )
        total_stacks += len(validated_stacks)
        cases.append(
            {
                "case_id": case_id,
                "case_dir": case_dir,
                "case_manifest_sha256": record["case_manifest_sha256"],
                "candidate_stack_count": len(validated_stacks),
                "candidate_stacks": validated_stacks,
            }
        )
    if total_stacks != cohort.get("candidate_stack_count"):
        raise PipelineError("Total de stacks candidatos v16 inconsistente.")
    return {
        "root": bundle_root,
        "cohort": cohort,
        "cohort_sha256": sha256_of(cohort_path),
        "case_ids": case_ids,
        "case_count": len(cases),
        "candidate_stack_count": total_stacks,
        "cases": cases,
    }


def validate_candidate_volume_review(review_path: Path, bundle: dict) -> dict:
    review = _load_json(review_path, "Revisao humana v16")
    confirmations = review.get("confirmations")
    if (
        review.get("schema") != REVIEW_SCHEMA
        or review.get("status") != "approved_for_blind_4b_scoring"
        or not isinstance(review.get("reviewer"), str)
        or not review["reviewer"].strip()
        or not isinstance(review.get("reviewed_at_utc"), str)
        or not review["reviewed_at_utc"].strip()
        or not isinstance(confirmations, dict)
        or not confirmations
        or not all(value is True for value in confirmations.values())
        or review.get("cohort_sha256") != bundle["cohort_sha256"]
        or review.get("gallery_signature") != bundle["cohort"].get("gallery_signature")
        or review.get("case_count") != bundle["case_count"]
        or review.get("candidate_stack_count") != bundle["candidate_stack_count"]
        or review.get("ground_truth_read") is not False
        or review.get("dataset_lesion_mask_used") is not False
        or review.get("holdout_opened") is not False
        or review.get("research_only") is not True
        or review.get("clinical_use_allowed") is not False
    ):
        raise PipelineError("Revisao humana v16 ausente, divergente ou incompleta.")
    signature = review.get("review_signature")
    unsigned = dict(review)
    unsigned.pop("review_signature", None)
    if signature != _canonical_hash(unsigned):
        raise PipelineError("Assinatura da revisao humana v16 diverge.")
    return review


def candidate_query(manifest: dict) -> str:
    ranges, expected_start = [], 1
    for group in manifest.get("groups", []):
        frames = group.get("frames", [])
        if not frames or frames[0].get("order") != expected_start:
            raise PipelineError("Mapa de frames v16 nao e contiguo.")
        end = expected_start + len(frames) - 1
        if frames[-1].get("order") != end:
            raise PipelineError("Mapa de frames v16 possui ordem divergente.")
        ranges.append(f'{expected_start}-{end}={group["role"]}')
        expected_start = end + 1
    if expected_start - 1 != manifest.get("frame_count"):
        raise PipelineError("Mapa de frames v16 nao cobre o stack completo.")
    return QUERY_TEMPLATE.format(
        candidate_number=manifest["candidate_number"],
        candidate_total=manifest["candidate_total"],
        selection_type="fallback no centro hepatico" if manifest["fallback_no_candidate"] else "candidato automatico",
        frame_map="; ".join(ranges),
    )


def candidate_log_odds(probabilities: dict[str, float]) -> float:
    positive = float(probabilities["POSITIVA"])
    negative = float(probabilities["NEGATIVA"])
    if not math.isfinite(positive) or not math.isfinite(negative) or positive < 0 or negative < 0:
        raise PipelineError("Probabilidades v16 invalidas para log-odds.")
    return math.log((positive + 1e-8) / (negative + 1e-8))


def aggregate_candidate_scores(candidates: list[dict]) -> dict:
    if not candidates:
        raise PipelineError("Caso v16 sem scores candidatos.")
    best = max(candidates, key=lambda item: (float(item["log_odds_positive_vs_negative"]), -int(item["candidate_number"])))
    return {
        "method": AGGREGATION_METHOD,
        "case_score": float(best["log_odds_positive_vs_negative"]),
        "selected_candidate_number": int(best["candidate_number"]),
        "selected_candidate_classification": best["classification"],
        "selected_candidate_probabilities": best["choice_probabilities"],
    }


def freeze_candidate_volume_score_protocol(*, bundle_root: Path, review_path: Path, config_path: Path, out_path: Path) -> dict:
    bundle = validate_candidate_volume_bundle(bundle_root)
    review = validate_candidate_volume_review(review_path, bundle)
    med = load_screening_config(config_path)["medgemma"]
    base = {
        "schema": PROTOCOL_SCHEMA,
        "status": "frozen_before_blind_scores",
        "bundle_cohort_sha256": bundle["cohort_sha256"],
        "bundle_gallery_signature": bundle["cohort"]["gallery_signature"],
        "review_sha256": sha256_of(Path(review_path).resolve()),
        "review_signature": review["review_signature"],
        "case_ids": bundle["case_ids"],
        "case_count": bundle["case_count"],
        "candidate_stack_count": bundle["candidate_stack_count"],
        "model_id": med["model_id"],
        "model_version": med["model_version"],
        "contract": CONTRACT,
        "endpoint_url": _score_url(str(med["endpoint_url"])),
        "instruction": INSTRUCTION,
        "query_template": QUERY_TEMPLATE,
        "frame_map_version": FRAME_MAP_VERSION,
        "scoring": {
            "response_prefix": RESPONSE_PREFIX,
            "choices": list(CHOICES),
            "method": SCORING_METHOD,
            "requests_per_candidate": 1,
            "automatic_retries": 0,
            "aggregation": AGGREGATION_METHOD,
            "epsilon": 1e-8,
            "probability_tolerance": PROBABILITY_TOLERANCE,
        },
        "case_time_gate_seconds": CASE_TIME_GATE_SECONDS,
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
        existing = _load_json(out_path, "Protocolo score v16")
        if existing != protocol:
            raise PipelineError("Protocolo score v16 existente diverge; sobrescrita recusada.")
        return existing
    _atomic_json(out_path, protocol)
    return protocol


def _load_protocol(path: Path) -> dict:
    protocol = _load_json(path, "Protocolo score v16")
    signature = protocol.pop("protocol_signature", None)
    if signature != _canonical_hash(protocol):
        raise PipelineError("Assinatura do protocolo score v16 diverge.")
    protocol["protocol_signature"] = signature
    scoring = protocol.get("scoring", {})
    if (
        protocol.get("schema") != PROTOCOL_SCHEMA
        or protocol.get("status") != "frozen_before_blind_scores"
        or protocol.get("contract") != CONTRACT
        or protocol.get("frame_map_version") != FRAME_MAP_VERSION
        or protocol.get("instruction") != INSTRUCTION
        or protocol.get("query_template") != QUERY_TEMPLATE
        or scoring.get("method") != SCORING_METHOD
        or scoring.get("choices") != list(CHOICES)
        or scoring.get("requests_per_candidate") != 1
        or scoring.get("automatic_retries") != 0
        or scoring.get("aggregation") != AGGREGATION_METHOD
        or scoring.get("epsilon") != 1e-8
        or protocol.get("case_time_gate_seconds") != CASE_TIME_GATE_SECONDS
        or protocol.get("ground_truth_read") is not False
        or protocol.get("metrics_calculated") is not False
        or protocol.get("holdout_opened") is not False
    ):
        raise PipelineError("Protocolo score v16 nao esta congelado ou viola salvaguardas.")
    return protocol


def _validate_context(bundle_root: Path, review_path: Path, protocol_path: Path, config_path: Path):
    bundle = validate_candidate_volume_bundle(bundle_root)
    review = validate_candidate_volume_review(review_path, bundle)
    protocol = _load_protocol(protocol_path)
    med = load_screening_config(config_path)["medgemma"]
    if (
        protocol["bundle_cohort_sha256"] != bundle["cohort_sha256"]
        or protocol["bundle_gallery_signature"] != bundle["cohort"]["gallery_signature"]
        or protocol["review_sha256"] != sha256_of(Path(review_path).resolve())
        or protocol["review_signature"] != review["review_signature"]
        or protocol["case_ids"] != bundle["case_ids"]
        or protocol["model_id"] != med["model_id"]
        or protocol["model_version"] != med["model_version"]
        or protocol["endpoint_url"] != _score_url(str(med["endpoint_url"]))
    ):
        raise PipelineError("Bundle, revisao, config ou protocolo score v16 divergiram.")
    health = _request_json(Request(str(med["healthcheck_url"]), headers={"Accept": "application/json"}, method="GET"), timeout=15)
    if (
        health.get("status") != "ready"
        or health.get("model_id") != protocol["model_id"]
        or health.get("model_version") != protocol["model_version"]
        or health.get("volume_score_contract") != CONTRACT
        or health.get("volume_score_method") != SCORING_METHOD
        or health.get("volume_score_supported") is not True
    ):
        raise PipelineError("Health nao confirmou o contrato focal v16.")
    return bundle, protocol, health


def _score_case(*, case: dict, protocol: dict, health: dict, prediction_path: Path) -> dict:
    started = time.monotonic()
    candidate_results = []
    for stack in case["candidate_stacks"]:
        manifest, images = _validate_candidate_stack(stack["candidate_dir"], stack)
        remaining = CASE_TIME_GATE_SECONDS - (time.monotonic() - started)
        if remaining <= 0:
            raise PipelineError(f'Caso {case["case_id"]} excedeu 180s antes de concluir os candidatos.')
        query = candidate_query(manifest)
        payload = {
            "contract": CONTRACT,
            "model_id": protocol["model_id"],
            "model_version": protocol["model_version"],
            "instruction": protocol["instruction"],
            "images": [{"mime_type": "image/png", "base64": base64.b64encode(raw).decode("ascii")} for raw in images],
            "query": query,
            "scoring": {"response_prefix": protocol["scoring"]["response_prefix"]},
        }
        request = Request(protocol["endpoint_url"], data=json.dumps(payload).encode("utf-8"), headers={"Content-Type": "application/json", "Accept": "application/json"}, method="POST")
        request_started = time.monotonic()
        response = _request_json(request, timeout=max(0.001, remaining))
        elapsed = time.monotonic() - request_started
        validated = _validate_score_response(response, protocol=protocol, slice_count=len(images))
        candidate_results.append(
            {
                "candidate_number": manifest["candidate_number"],
                "candidate_manifest_sha256": stack["manifest_sha256"],
                "frame_count": len(images),
                "fallback_no_candidate": manifest["fallback_no_candidate"],
                "query_sha256": _canonical_hash({"query": query}),
                "classification": validated["classification"],
                "choice_probabilities": validated["choice_probabilities"],
                "choice_token_metadata": validated["choice_token_metadata"],
                "tie_detected": validated["tie_detected"],
                "log_odds_positive_vs_negative": candidate_log_odds(validated["choice_probabilities"]),
                "request_elapsed_seconds": round(elapsed, 4),
                "gateway_timings_seconds": response.get("timings_seconds"),
            }
        )
    total = time.monotonic() - started
    if total > CASE_TIME_GATE_SECONDS:
        raise PipelineError(f'Caso {case["case_id"]} excedeu o gate temporal v16.')
    aggregation = aggregate_candidate_scores(candidate_results)
    result = {
        "schema": PREDICTION_SCHEMA,
        "status": "technical_passed",
        "case_id": case["case_id"],
        "protocol_signature": protocol["protocol_signature"],
        "case_manifest_sha256": case["case_manifest_sha256"],
        "candidate_stack_count": len(candidate_results),
        "candidate_results": candidate_results,
        "aggregation": aggregation,
        "scoring_elapsed_seconds": round(total, 4),
        "case_time_gate_seconds": CASE_TIME_GATE_SECONDS,
        "time_gate_passed": True,
        "health_model_id": health.get("model_id"),
        "ground_truth_read": False,
        "metrics_calculated": False,
        "holdout_opened": False,
        "research_only": True,
        "clinical_use_allowed": False,
        "requires_human_review": True,
    }
    _atomic_json(prediction_path, result)
    return result


def _validate_existing_prediction(path: Path, case: dict, protocol: dict) -> dict:
    result = _load_json(path, "Predicao focal v16")
    if (
        result.get("schema") != PREDICTION_SCHEMA
        or result.get("status") != "technical_passed"
        or result.get("case_id") != case["case_id"]
        or result.get("protocol_signature") != protocol["protocol_signature"]
        or result.get("case_manifest_sha256") != case["case_manifest_sha256"]
        or result.get("candidate_stack_count") != case["candidate_stack_count"]
        or result.get("time_gate_passed") is not True
        or result.get("scoring_elapsed_seconds", CASE_TIME_GATE_SECONDS + 1) > CASE_TIME_GATE_SECONDS
        or result.get("ground_truth_read") is not False
        or result.get("metrics_calculated") is not False
        or result.get("holdout_opened") is not False
    ):
        raise PipelineError("Predicao focal v16 existente nao e reutilizavel.")
    candidates = result.get("candidate_results")
    if not isinstance(candidates, list) or len(candidates) != case["candidate_stack_count"]:
        raise PipelineError("Predicao focal v16 possui candidatos incompletos.")
    for candidate, stack in zip(candidates, case["candidate_stacks"], strict=True):
        manifest, images = _validate_candidate_stack(stack["candidate_dir"], stack)
        if (
            candidate.get("candidate_number") != manifest["candidate_number"]
            or candidate.get("candidate_manifest_sha256") != stack["manifest_sha256"]
            or candidate.get("frame_count") != len(images)
            or candidate.get("fallback_no_candidate") is not manifest["fallback_no_candidate"]
            or candidate.get("query_sha256") != _canonical_hash({"query": candidate_query(manifest)})
        ):
            raise PipelineError("Predicao focal v16 reutilizada diverge do stack candidato.")
        response = {
            "contract": CONTRACT,
            "model_id": protocol["model_id"],
            "model_version": protocol["model_version"],
            "slice_count": len(images),
            "choice": candidate.get("classification"),
            "choice_probabilities": candidate.get("choice_probabilities"),
            "scoring_method": SCORING_METHOD,
            "choice_token_metadata": candidate.get("choice_token_metadata"),
            "tie_detected": candidate.get("tie_detected"),
            "research_only": True,
            "clinical_use_allowed": False,
            "requires_human_review": True,
        }
        validated = _validate_score_response(response, protocol=protocol, slice_count=len(images))
        expected_log_odds = candidate_log_odds(validated["choice_probabilities"])
        try:
            stored_log_odds = float(candidate["log_odds_positive_vs_negative"])
        except (KeyError, TypeError, ValueError) as exc:
            raise PipelineError("Predicao focal v16 possui log-odds invalido.") from exc
        if not math.isclose(stored_log_odds, expected_log_odds, rel_tol=0.0, abs_tol=1e-12):
            raise PipelineError("Predicao focal v16 possui log-odds adulterado.")
    if result.get("aggregation") != aggregate_candidate_scores(candidates):
        raise PipelineError("Agregacao focal v16 existente diverge dos candidatos.")
    return result


def _ensure_run_context(output_root: Path, protocol: dict, bundle: dict) -> dict:
    context = {
        "schema": RUN_CONTEXT_SCHEMA,
        "protocol_signature": protocol["protocol_signature"],
        "bundle_cohort_sha256": bundle["cohort_sha256"],
        "bundle_gallery_signature": bundle["cohort"]["gallery_signature"],
        "case_ids": bundle["case_ids"],
        "ground_truth_read": False,
        "metrics_calculated": False,
        "holdout_opened": False,
        "research_only": True,
        "clinical_use_allowed": False,
        "requires_human_review": True,
    }
    path = output_root / "run_context.json"
    if path.exists():
        if _load_json(path, "Contexto da execucao focal v16") != context:
            raise PipelineError("Diretorio de saida v16 pertence a outro protocolo ou bundle.")
        return context
    _atomic_json(path, context)
    return context


def _write_progress(output_root: Path, protocol: dict, bundle: dict, predictions: list[dict]) -> dict:
    records = [{
        "case_id": item["case_id"],
        "prediction_sha256": sha256_of(output_root / "predictions" / f'{item["case_id"]}.json'),
        "case_score": item["aggregation"]["case_score"],
        "selected_candidate_number": item["aggregation"]["selected_candidate_number"],
        "scoring_elapsed_seconds": item["scoring_elapsed_seconds"],
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
        timings = [float(item["scoring_elapsed_seconds"]) for item in predictions]
        summary = {
            **progress,
            "schema": SUMMARY_SCHEMA,
            "candidate_request_count": sum(item["candidate_stack_count"] for item in predictions),
            "scoring_timing_seconds": {
                "minimum": min(timings),
                "median": statistics.median(timings),
                "mean": statistics.fmean(timings),
                "maximum": max(timings),
                "all_within_180": all(value <= CASE_TIME_GATE_SECONDS for value in timings),
            },
            "timing_scope": "precomputed_candidate_scoring_only",
            "end_to_end_180_seconds_proven": False,
            "accuracy_claimed": False,
        }
        _atomic_json(output_root / "summary.json", summary)
        return summary
    return progress


def run_candidate_volume_score_blind_batch(*, bundle_root: Path, review_path: Path, protocol_path: Path, config_path: Path, output_root: Path, max_new_cases: int | None = None, progress_callback=None) -> dict:
    if max_new_cases is not None and max_new_cases < 1:
        raise PipelineError("max_new_cases v16 deve ser positivo.")
    bundle, protocol, health = _validate_context(bundle_root, review_path, protocol_path, config_path)
    output_root = Path(output_root).resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    _ensure_run_context(output_root, protocol, bundle)
    predictions_dir = output_root / "predictions"
    predictions_dir.mkdir(parents=True, exist_ok=True)
    predictions, new_count = [], 0
    for index, case in enumerate(bundle["cases"], 1):
        path = predictions_dir / f'{case["case_id"]}.json'
        reused = path.exists()
        if reused:
            result = _validate_existing_prediction(path, case, protocol)
        elif max_new_cases is not None and new_count >= max_new_cases:
            continue
        else:
            result = _score_case(case=case, protocol=protocol, health=health, prediction_path=path)
            new_count += 1
        predictions.append(result)
        _write_progress(output_root, protocol, bundle, predictions)
        if progress_callback:
            progress_callback({
                "index": index,
                "case_count": bundle["case_count"],
                "case_id": case["case_id"],
                "candidate_stack_count": case["candidate_stack_count"],
                "case_score": result["aggregation"]["case_score"],
                "scoring_elapsed_seconds": result["scoring_elapsed_seconds"],
                "reused": reused,
            })
    return _write_progress(output_root, protocol, bundle, predictions)

