"""Immutable MedGemma 1.5 4B scoring freeze for paired v10 ROI galleries."""
from __future__ import annotations

import hashlib
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dtwin.benchmark.openswisshcc_alignment import _sha256
from dtwin.benchmark.openswisshcc_localizer_roi_gate import verify_paired_review
from dtwin.core import PipelineError
from dtwin.medgemma_client import effective_config_sha256, load_screening_config

FREEZE_SCHEMA = "argos-openswisshcc-localizer-roi-medgemma-freeze-v1"
QUESTION_BANK = (
    {"question_id": "morphology_mass_vs_mimic", "representation": "morphology", "question": "Does the visible evidence support a discrete focal hepatic lesion rather than a vessel, benign anatomical variant, artifact, or partial-volume effect?", "positive_semantics": "focal lesion supported", "negative_semantics": "mimic or no focal lesion supported"},
    {"question_id": "morphology_cross_sequence", "representation": "morphology", "question": "Is there a concordant focal abnormality at this location on at least two available sequences among T1 venous, T2, DWI TRACE, and ADC?", "positive_semantics": "cross-sequence focal abnormality supported", "negative_semantics": "cross-sequence focal abnormality not supported"},
    {"question_id": "dynamic_mass_vs_vessel", "representation": "enhancement", "question": "Across the available dynamic phases, does this location behave as a focal lesion rather than a continuous vascular structure or transient perfusion change?", "positive_semantics": "focal lesion behavior supported", "negative_semantics": "vascular or perfusion mimic supported"},
    {"question_id": "dynamic_enhancement_support", "representation": "enhancement", "question": "Do the available native, arterial, venous, and delayed images show focal enhancement evolution or washout that supports a hepatic lesion?", "positive_semantics": "lesion-supporting enhancement evolution", "negative_semantics": "lesion-supporting enhancement evolution absent"},
)
SCORING_PROTOCOL = {
    "method": "single_token_mirrored_ab_semantic_probability_v1",
    "authorized_tokens": ["A", "B"],
    "mappings": [
        {"mapping_id": "ab", "A": "positive", "B": "negative"},
        {"mapping_id": "ba", "A": "negative", "B": "positive"},
    ],
    "semantic_probability": "mean(P(A|ab), P(B|ba))",
    "panel_aggregation": "scores_only_no_decision",
    "case_aggregation": "deferred_until_all_blind_scores_are_persisted",
}
SIGNED_FIELDS = (
    "schema",
    "experiment_version",
    "review_signature",
    "morphology_gallery",
    "enhancement_gallery",
    "case_count",
    "panel_pairs",
    "config",
    "question_bank",
    "question_bank_sha256",
    "scoring_protocol",
    "max_end_to_end_seconds",
    "max_upstream_seconds",
    "max_scoring_seconds",
    "research_only",
    "clinical_use_allowed",
    "ground_truth_read",
    "lesion_mask_used",
    "inference_executed",
)


def _canonical(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def _signature(payload: dict[str, Any]) -> str:
    return _canonical({key: payload.get(key) for key in SIGNED_FIELDS})


def _load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PipelineError(f"Freeze ROI v10 invalido: {path}") from exc
    if not isinstance(value, dict):
        raise PipelineError("Freeze ROI v10 deve ser objeto.")
    return value


def _config(path: Path) -> dict[str, Any]:
    path = Path(path).resolve()
    config = load_screening_config(path)
    med = config["medgemma"]
    record = {
        "filename": path.name,
        "raw_sha256": _sha256(path),
        "effective_sha256": effective_config_sha256(config),
        "model_id": med.get("model_id"),
        "model_version": med.get("model_version"),
        "model_parameter_scale": med.get("model_parameter_scale"),
        "response_mode": med.get("response_mode"),
        "timeout_seconds": med.get("timeout_seconds"),
        "max_retries": med.get("max_retries"),
        "response_validation_max_retries": med.get("response_validation_max_retries"),
        "max_output_tokens": med.get("max_output_tokens"),
        "rag_enabled": config.get("rag", {}).get("enabled", False),
    }
    if record["model_id"] != "google/medgemma-1.5-4b-it" or record["model_parameter_scale"] != "4B":
        raise PipelineError("Freeze ROI v10 exige exatamente MedGemma 1.5 4B.")
    if record["response_mode"] != "choice_classification" or record["rag_enabled"] is not False:
        raise PipelineError("Freeze ROI v10 exige choice_classification sem RAG.")
    if not 1 <= int(record["timeout_seconds"]) <= 45 or int(record["max_retries"]) != 0 or int(record["response_validation_max_retries"]) != 0 or int(record["max_output_tokens"]) > 64:
        raise PipelineError("Config ROI v10 excede timeout, tokens ou permite retry.")
    return record


def create_roi_freeze(*, morphology_root: Path, enhancement_root: Path, review_path: Path, config_path: Path, output_path: Path, experiment_version: str, expected_case_count: int = 10, max_end_to_end_seconds: float = 180.0, max_upstream_seconds: float = 90.0, max_scoring_seconds: float = 90.0) -> dict[str, Any]:
    values = [float(max_end_to_end_seconds), float(max_upstream_seconds), float(max_scoring_seconds)]
    if values[0] != 180.0 or min(values[1:]) <= 0 or values[1] + values[2] > values[0]:
        raise PipelineError("Orcamento de tempo ROI v10 invalido.")
    review = verify_paired_review(morphology_root=morphology_root, enhancement_root=enhancement_root, review_path=review_path, expected_case_count=expected_case_count)
    version = str(experiment_version).strip()
    if not version or len(version) > 120:
        raise PipelineError("experiment_version ROI v10 invalida.")
    payload = {
        "schema": FREEZE_SCHEMA,
        "experiment_version": version,
        "review_signature": review["review_signature"],
        "morphology_gallery": review["morphology_gallery"],
        "enhancement_gallery": review["enhancement_gallery"],
        "case_count": review["case_count"],
        "panel_pairs": review["panel_pairs"],
        "config": _config(config_path),
        "question_bank": list(QUESTION_BANK),
        "question_bank_sha256": _canonical(QUESTION_BANK),
        "scoring_protocol": SCORING_PROTOCOL,
        "max_end_to_end_seconds": values[0],
        "max_upstream_seconds": values[1],
        "max_scoring_seconds": values[2],
        "research_only": True,
        "clinical_use_allowed": False,
        "ground_truth_read": False,
        "lesion_mask_used": False,
        "inference_executed": False,
    }
    payload["experiment_signature"] = _signature(payload)
    payload["created_at_utc"] = datetime.now(timezone.utc).isoformat()
    output = Path(output_path).resolve()
    if output.exists():
        raise PipelineError("Freeze ROI v10 ja existe e nao sera sobrescrito.")
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(f".{output.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(temporary, output)
    finally:
        temporary.unlink(missing_ok=True)
    return payload


def verify_roi_freeze(*, morphology_root: Path, enhancement_root: Path, review_path: Path, config_path: Path, freeze_path: Path, expected_case_count: int = 10) -> dict[str, Any]:
    freeze = _load(Path(freeze_path).resolve())
    if set(freeze) != set(SIGNED_FIELDS) | {"experiment_signature", "created_at_utc"} or freeze.get("schema") != FREEZE_SCHEMA or freeze.get("experiment_signature") != _signature(freeze):
        raise PipelineError("Campos ou assinatura do freeze ROI v10 invalidos.")
    review = verify_paired_review(morphology_root=morphology_root, enhancement_root=enhancement_root, review_path=review_path, expected_case_count=expected_case_count)
    if freeze["review_signature"] != review["review_signature"] or freeze["morphology_gallery"] != review["morphology_gallery"] or freeze["enhancement_gallery"] != review["enhancement_gallery"] or freeze["case_count"] != review["case_count"] or freeze["panel_pairs"] != review["panel_pairs"] or freeze["config"] != _config(config_path):
        raise PipelineError("Freeze ROI v10 divergiu da revisao, galerias ou config.")
    if freeze["question_bank"] != list(QUESTION_BANK) or freeze["question_bank_sha256"] != _canonical(QUESTION_BANK) or freeze["scoring_protocol"] != SCORING_PROTOCOL:
        raise PipelineError("Banco de perguntas ou protocolo ROI v10 divergiu.")
    return freeze
