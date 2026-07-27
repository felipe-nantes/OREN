"""Frozen, resumable OpenSwissHCC v24 liver-enriched 4B inference."""
from __future__ import annotations

import copy
import json
import math
import shutil
import time
import uuid
from pathlib import Path
from typing import Any

from dtwin.benchmark.openswisshcc_alignment import _publish_directory
from dtwin.benchmark.openswisshcc_v20_fusion import _canonical_sha
from dtwin.benchmark.v24_liver_enriched_openswisshcc import (
    _load,
    _sha256,
    verify_v24_liver_enriched_full_cohort,
)
from dtwin.core import PipelineError
from dtwin.medgemma_client import (
    build_medgemma_prompt,
    create_medgemma_client,
    load_screening_config,
    model_trace,
    validate_configured_medgemma_report,
)
from dtwin.medgemma_screening import (
    _aggregate_panel_reports,
    _partial_prompt,
    _write_json_atomic,
    sha256_of_text,
)
from dtwin.rag import append_rag_to_prompt, build_rag_context, persist_rag_context


PROTOCOL_SCHEMA = "argos-openswisshcc-v24-liver-enriched-inference-protocol-v1"
CASE_SCHEMA = "argos-openswisshcc-v24-liver-enriched-inference-case-v1"
RUN_SCHEMA = "argos-openswisshcc-v24-liver-enriched-inference-run-v1"
VERIFICATION_SCHEMA = "argos-openswisshcc-v24-liver-enriched-inference-verification-v1"
AGGREGATION_RULE = "any_positive_else_any_inconclusive_else_all_negative"
SIGNAL_RULE = "maximum_panel_choice_probability_positiva_v1"


def _validate_candidate_config(
    config: dict[str, Any], *, candidate_id: str, reused_panels: bool
) -> str:
    prompt = build_medgemma_prompt(config)
    expects_rag = "plus_text_rag" in candidate_id
    if (
        config.get("medgemma", {}).get("response_mode") != "choice_classification"
        or config.get("rag", {}).get("enabled") is not expects_rag
        or config.get("panel", {}).get("spatial_focus")
        != "liver_enriched_full_fov"
        or (
            reused_panels
            and config.get("panel", {}).get(
                "reuse_approved_liver_enriched_panels"
            )
            is not True
        )
    ):
        raise PipelineError("Config de inferência liver-enriched inválida.")
    if "pathology_target" in candidate_id and (
        '"alvo_da_triagem"' not in prompt
        or '"ha_lesao_focal_suspeita"' not in prompt
        or "variante anatômica" not in prompt.lower()
    ):
        raise PipelineError("Candidato pathology-target sem schema clínico v2.")
    return prompt


def _repo_root_from_config(path: Path) -> Path:
    resolved = Path(path).resolve()
    if resolved.parent.name != "configs":
        raise PipelineError("Config liver-enriched deve permanecer em configs/.")
    return resolved.parent.parent


def _prompt_with_frozen_rag(
    *, config: dict[str, Any], config_path: Path, candidate_id: str
) -> tuple[str, dict[str, Any], dict[str, Any]]:
    prompt = build_medgemma_prompt(config)
    context = build_rag_context(
        config=config, repo_root=_repo_root_from_config(config_path)
    )
    prompt, audit = append_rag_to_prompt(
        prompt,
        context,
        max_prompt_chars=int(config["medgemma"].get("max_prompt_chars", 12000)),
    )
    expects_rag = "plus_text_rag" in candidate_id
    if (context.get("enabled") is True) is not expects_rag:
        raise PipelineError("Estado RAG divergiu do candidato predeclarado.")
    if expects_rag and (
        not context.get("context_sha256")
        or not audit.get("rag_addendum_sha256")
        or context.get("source_count", 0) < 1
    ):
        raise PipelineError("Candidato text-RAG sem contexto recuperado verificável.")
    return prompt, context, audit


def _protocol_cases(cohort: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "case_id": row["case_id"],
            "input_mode": row["input_mode"],
            "selection_mode": row["selection_mode"],
            "panel_count": row["panel_count"],
            "manifest": row["manifest"],
            "manifest_sha256": row["manifest_sha256"],
            "panels": copy.deepcopy(row["panels"]),
        }
        for row in cohort["cases"]
    ]


def _validate_probabilities(value: Any) -> dict[str, float]:
    if not isinstance(value, dict) or set(value) != {
        "POSITIVA",
        "NEGATIVA",
        "INCONCLUSIVA",
    }:
        raise PipelineError("Probabilidades choice v24 ausentes ou incompletas.")
    result: dict[str, float] = {}
    for label in ("POSITIVA", "NEGATIVA", "INCONCLUSIVA"):
        item = value[label]
        if (
            isinstance(item, bool)
            or not isinstance(item, (int, float))
            or not math.isfinite(float(item))
            or not 0.0 <= float(item) <= 1.0
        ):
            raise PipelineError("Probabilidade choice v24 inválida.")
        result[label] = float(item)
    if not math.isclose(sum(result.values()), 1.0, abs_tol=1e-5):
        raise PipelineError("Probabilidades choice v24 não somam 1.")
    return result


def freeze_v24_liver_enriched_inference_protocol(
    *,
    source_protocol_path: Path,
    review_path: Path,
    gallery_root: Path,
    config_path: Path,
    panel_root: Path,
    full_verification_path: Path,
    output_path: Path,
    panel_config_path: Path | None = None,
    candidate_id: str = "v24_candidate_1_v23_plus_liver_enriched",
    predecessor_evaluation_path: Path | None = None,
) -> dict[str, Any]:
    effective_panel_config = (
        Path(panel_config_path) if panel_config_path is not None else Path(config_path)
    )
    verification = verify_v24_liver_enriched_full_cohort(
        protocol_path=source_protocol_path,
        review_path=review_path,
        gallery_root=gallery_root,
        config_path=effective_panel_config,
        panel_root=panel_root,
    )
    persisted_verification = _load(
        full_verification_path, "Verificação da coorte v24"
    )
    if persisted_verification != verification:
        raise PipelineError("Verificação persistida da coorte v24 divergiu.")
    cohort = _load(
        Path(panel_root).resolve() / "cohort_manifest.json", "Coorte v24"
    )
    config = load_screening_config(config_path)
    reused_panels = _sha256(Path(config_path)) != _sha256(effective_panel_config)
    _validate_candidate_config(
        config, candidate_id=candidate_id, reused_panels=reused_panels
    )
    prompt, rag_context, prompt_audit = _prompt_with_frozen_rag(
        config=config, config_path=Path(config_path), candidate_id=candidate_id
    )
    predecessor: dict[str, Any] | None = None
    if "pathology_target" in candidate_id:
        if predecessor_evaluation_path is None:
            raise PipelineError(
                "Candidato pathology-target exige avaliação congelada do predecessor."
            )
        predecessor = _load(
            predecessor_evaluation_path, "Avaliação predecessora liver-enriched"
        )
        unsigned_predecessor = dict(predecessor)
        predecessor_signature = unsigned_predecessor.pop(
            "evaluation_signature", None
        )
        if (
            predecessor.get("schema")
            != "argos-openswisshcc-v24-liver-enriched-evaluation-v1"
            or predecessor.get("status") != "v24_candidate_failed"
            or predecessor_signature != _canonical_sha(unsigned_predecessor)
        ):
            raise PipelineError("Avaliação predecessora não autoriza o candidato 2.")
    cases = _protocol_cases(cohort)
    body = {
        "schema": PROTOCOL_SCHEMA,
        "status": "frozen_before_label_blind_4b_inference",
        "candidate_id": candidate_id,
        "case_count": len(cases),
        "protocol_case_count": 132,
        "technical_failure_case_count": 2,
        "technical_failures_excluded_from_inference": True,
        "technical_failures_count_as_primary_metric_errors": True,
        "case_ids": [row["case_id"] for row in cases],
        "total_panel_count": sum(row["panel_count"] for row in cases),
        "cases": cases,
        "maximum_seconds_per_case": 180.0,
        "timing_scope": "sequential_panel_calls_validation_aggregation_persistence",
        "aggregation_rule": AGGREGATION_RULE,
        "signal_rule": SIGNAL_RULE,
        "config_sha256": _sha256(Path(config_path)),
        "panel_config_sha256": _sha256(effective_panel_config),
        "reused_verified_panels_for_inference": reused_panels,
        "effective_prompt_sha256": sha256_of_text(prompt),
        "rag_enabled": rag_context.get("enabled") is True,
        "rag_context_sha256": (
            rag_context.get("context_sha256")
            if rag_context.get("enabled") is True
            else None
        ),
        "rag_prompt_addendum_sha256": prompt_audit.get("rag_addendum_sha256"),
        "predecessor_evaluation_sha256": (
            _sha256(Path(predecessor_evaluation_path))
            if predecessor_evaluation_path is not None
            else None
        ),
        "predecessor_evaluation_signature": (
            predecessor.get("evaluation_signature")
            if predecessor is not None
            else None
        ),
        "model_id": config["medgemma"]["model_id"],
        "model_version": config["medgemma"]["model_version"],
        "source_v24_protocol_signature": verification["protocol_signature"],
        "review_signature": verification["review_signature"],
        "cohort_signature": verification["cohort_signature"],
        "full_verification_signature": verification["verification_signature"],
        "panel_cohort_sha256": verification["cohort_manifest_sha256"],
        "organ_mask_sent_to_model": False,
        "labels_read": False,
        "lesion_masks_read": 0,
        "metrics_calculated": False,
        "research_only": True,
        "clinical_use_allowed": False,
        "requires_human_review": True,
    }
    protocol = {**body, "protocol_signature": _canonical_sha(body)}
    output = Path(output_path).resolve()
    if output.exists():
        raise PipelineError("Protocolo de inferência v24 já existe.")
    _write_json_atomic(output, protocol)
    return protocol


def verify_v24_liver_enriched_inference_protocol(
    *,
    source_protocol_path: Path,
    review_path: Path,
    gallery_root: Path,
    config_path: Path,
    panel_root: Path,
    full_verification_path: Path,
    inference_protocol_path: Path,
    panel_config_path: Path | None = None,
    candidate_id: str | None = None,
    predecessor_evaluation_path: Path | None = None,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    effective_panel_config = (
        Path(panel_config_path) if panel_config_path is not None else Path(config_path)
    )
    verification = verify_v24_liver_enriched_full_cohort(
        protocol_path=source_protocol_path,
        review_path=review_path,
        gallery_root=gallery_root,
        config_path=effective_panel_config,
        panel_root=panel_root,
    )
    if _load(full_verification_path, "Verificação da coorte v24") != verification:
        raise PipelineError("Verificação persistida da coorte v24 divergiu.")
    cohort = _load(Path(panel_root) / "cohort_manifest.json", "Coorte v24")
    protocol = _load(inference_protocol_path, "Protocolo de inferência v24")
    unsigned = dict(protocol)
    signature = unsigned.pop("protocol_signature", None)
    config = load_screening_config(config_path)
    reused_panels = _sha256(Path(config_path)) != _sha256(effective_panel_config)
    effective_candidate_id = str(protocol.get("candidate_id") or "")
    _validate_candidate_config(
        config,
        candidate_id=effective_candidate_id,
        reused_panels=reused_panels,
    )
    prompt, rag_context, prompt_audit = _prompt_with_frozen_rag(
        config=config,
        config_path=Path(config_path),
        candidate_id=effective_candidate_id,
    )
    if "pathology_target" in effective_candidate_id:
        if (
            predecessor_evaluation_path is None
            or protocol.get("predecessor_evaluation_sha256")
            != _sha256(Path(predecessor_evaluation_path))
        ):
            raise PipelineError("Predecessor do candidato pathology-target divergiu.")
    expected_cases = _protocol_cases(cohort)
    if (
        protocol.get("schema") != PROTOCOL_SCHEMA
        or protocol.get("status") != "frozen_before_label_blind_4b_inference"
        or signature != _canonical_sha(unsigned)
        or protocol.get("case_count") != 130
        or protocol.get("protocol_case_count") != 132
        or protocol.get("technical_failure_case_count") != 2
        or protocol.get("case_ids") != cohort["case_ids"]
        or protocol.get("cases") != expected_cases
        or protocol.get("total_panel_count") != 390
        or protocol.get("maximum_seconds_per_case") != 180.0
        or protocol.get("aggregation_rule") != AGGREGATION_RULE
        or protocol.get("signal_rule") != SIGNAL_RULE
        or protocol.get("config_sha256") != _sha256(Path(config_path))
        or (
            "panel_config_sha256" in protocol
            and protocol.get("panel_config_sha256")
            != _sha256(effective_panel_config)
        )
        or (
            "reused_verified_panels_for_inference" in protocol
            and protocol.get("reused_verified_panels_for_inference")
            is not reused_panels
        )
        or (candidate_id is not None and protocol.get("candidate_id") != candidate_id)
        or protocol.get("effective_prompt_sha256")
        != sha256_of_text(prompt)
        or protocol.get("rag_enabled") is not (rag_context.get("enabled") is True)
        or protocol.get("rag_context_sha256")
        != (
            rag_context.get("context_sha256")
            if rag_context.get("enabled") is True
            else None
        )
        or protocol.get("rag_prompt_addendum_sha256")
        != prompt_audit.get("rag_addendum_sha256")
        or protocol.get("cohort_signature") != verification["cohort_signature"]
        or protocol.get("full_verification_signature")
        != verification["verification_signature"]
        or protocol.get("panel_cohort_sha256")
        != verification["cohort_manifest_sha256"]
        or protocol.get("organ_mask_sent_to_model") is not False
        or protocol.get("labels_read") is not False
        or protocol.get("lesion_masks_read") != 0
        or protocol.get("metrics_calculated") is not False
    ):
        raise PipelineError("Protocolo de inferência v24 inválido ou adulterado.")
    return protocol, cohort, config


def _write_jsonl_atomic(path: Path, rows: list[dict[str, Any]]) -> None:
    temporary = path.with_name(f".{path.name}.tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as stream:
        for row in rows:
            stream.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
        stream.flush()
    temporary.replace(path)


def _set_remaining_timeout(client: Any, original: int, remaining: float) -> None:
    med = getattr(client, "med", None)
    if isinstance(med, dict):
        med["timeout_seconds"] = max(1, min(original, int(math.floor(remaining))))


def _existing_case(
    *,
    output_root: Path,
    case: dict[str, Any],
    protocol: dict[str, Any],
) -> dict[str, Any] | None:
    case_dir = output_root / case["case_id"]
    if not case_dir.exists():
        return None
    if (case_dir / "inference_failure.json").exists():
        raise PipelineError(f"Falha v24 preservada: {case['case_id']}.")
    manifest_path = case_dir / "inference_manifest.json"
    report_path = case_dir / "medgemma_report.json"
    if not manifest_path.is_file() or not report_path.is_file():
        raise PipelineError(f"Saída v24 parcial: {case['case_id']}.")
    result = _load(manifest_path, "Manifesto de inferência v24")
    unsigned = dict(result)
    signature = unsigned.pop("case_signature", None)
    expected_inputs = [
        {"image": panel["relative_path"], "sha256": panel["sha256"]}
        for panel in case["panels"]
    ]
    report = _load(report_path, "Relatório MedGemma v24")
    if (
        result.get("schema") != CASE_SCHEMA
        or result.get("case_id") != case["case_id"]
        or result.get("status") != "success_pending_analysis"
        or signature != _canonical_sha(unsigned)
        or result.get("panel_count") != case["panel_count"]
        or result.get("protocol_signature") != protocol["protocol_signature"]
        or result.get("report_sha256") != _sha256(report_path)
        or result.get("within_time_limit") is not True
        or result.get("labels_read") is not False
        or result.get("lesion_masks_read") != 0
        or report.get("case_id") != case["case_id"]
        or report.get("input_panels") != expected_inputs
        or len(report.get("panel_reports", [])) != case["panel_count"]
    ):
        raise PipelineError(f"Saída v24 divergiu: {case['case_id']}.")
    for panel_report in report["panel_reports"]:
        _validate_probabilities(panel_report.get("choice_probabilities"))
    for key in (
        "max_positive_probability",
        "max_negative_probability",
        "max_inconclusive_probability",
    ):
        value = result.get(key)
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(float(value))
            or not 0.0 <= float(value) <= 1.0
        ):
            raise PipelineError(f"Sinal contínuo v24 inválido: {key}.")
    return result


def run_v24_liver_enriched_inference(
    *,
    source_protocol_path: Path,
    review_path: Path,
    gallery_root: Path,
    config_path: Path,
    panel_root: Path,
    full_verification_path: Path,
    inference_protocol_path: Path,
    output_root: Path,
    client: Any | None = None,
    panel_config_path: Path | None = None,
    candidate_id: str | None = None,
    predecessor_evaluation_path: Path | None = None,
) -> dict[str, Any]:
    protocol, _cohort, config = verify_v24_liver_enriched_inference_protocol(
        source_protocol_path=source_protocol_path,
        review_path=review_path,
        gallery_root=gallery_root,
        config_path=config_path,
        panel_root=panel_root,
        full_verification_path=full_verification_path,
        inference_protocol_path=inference_protocol_path,
        panel_config_path=panel_config_path,
        candidate_id=candidate_id,
        predecessor_evaluation_path=predecessor_evaluation_path,
    )
    panel_root = Path(panel_root).resolve()
    output_root = Path(output_root).resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    base_prompt, rag_context, prompt_audit = _prompt_with_frozen_rag(
        config=config,
        config_path=Path(config_path),
        candidate_id=str(protocol["candidate_id"]),
    )
    if (
        protocol.get("rag_context_sha256")
        != (
            rag_context.get("context_sha256")
            if rag_context.get("enabled") is True
            else None
        )
        or protocol.get("rag_prompt_addendum_sha256")
        != prompt_audit.get("rag_addendum_sha256")
    ):
        raise PipelineError("Contexto RAG mudou após o congelamento.")
    if rag_context.get("enabled") is True:
        persist_rag_context(output_root / "rag_context.json", rag_context)
    max_prompt_chars = int(config["medgemma"].get("max_prompt_chars", 12000))
    original_timeout = int(config["medgemma"]["timeout_seconds"])
    model_client = client
    results: list[dict[str, Any]] = []
    run_started = time.monotonic()
    for case in protocol["cases"]:
        existing = _existing_case(
            output_root=output_root, case=case, protocol=protocol
        )
        if existing is not None:
            results.append(existing)
            continue
        case_id = case["case_id"]
        for stale in output_root.glob(f".{case_id}.staging.*"):
            if stale.is_dir():
                shutil.rmtree(stale)
        staging = output_root / f".{case_id}.staging.{uuid.uuid4().hex}"
        staging.mkdir()
        final_dir = output_root / case_id
        started = time.monotonic()
        reports: list[dict[str, Any]] = []
        timings: list[dict[str, Any]] = []
        active_panel: dict[str, Any] | None = None
        try:
            panel_manifest_path = (panel_root / case["manifest"]).resolve()
            panel_manifest = _load(panel_manifest_path, "Manifesto visual v24")
            if _sha256(panel_manifest_path) != case["manifest_sha256"]:
                raise PipelineError("Manifesto visual v24 divergiu.")
            rendered_panels = panel_manifest.get("panels")
            if not isinstance(rendered_panels, list) or len(rendered_panels) != case["panel_count"]:
                raise PipelineError("Quantidade de painéis v24 divergiu.")
            for source, rendered in zip(case["panels"], rendered_panels, strict=True):
                active_panel = source
                remaining = 180.0 - (time.monotonic() - started)
                if remaining <= 1.0:
                    raise PipelineError("Teto v24 de 180 segundos esgotado.")
                if model_client is None:
                    model_client = create_medgemma_client(config)
                _set_remaining_timeout(model_client, original_timeout, remaining)
                panel_path = (panel_root / source["relative_path"]).resolve()
                if (
                    not panel_path.is_relative_to(panel_root)
                    or _sha256(panel_path) != source["sha256"]
                    or rendered.get("sha256") != source["sha256"]
                ):
                    raise PipelineError("Painel v24 divergiu do protocolo.")
                panel_record = {
                    "panel_number": source["panel_number"],
                    "panel_total": case["panel_count"],
                    "image": panel_path.name,
                    "sha256": source["sha256"],
                    "axial_interval": rendered.get("axial_interval"),
                }
                prompt = _partial_prompt(base_prompt, panel_record)
                if len(prompt) > max_prompt_chars:
                    raise PipelineError("Prompt v24 excede o limite.")
                panel_started = time.monotonic()
                raw = model_client.generate(panel_path, prompt)
                validated = validate_configured_medgemma_report(raw, config)
                panel_seconds = time.monotonic() - panel_started
                audit = copy.deepcopy(
                    dict(getattr(model_client, "last_response_audit", {}) or {})
                )
                probabilities = _validate_probabilities(
                    audit.get("choice_probabilities")
                )
                reports.append(
                    {
                        **panel_record,
                        "prompt_sha256": sha256_of_text(prompt),
                        "rag_context_sha256": protocol.get("rag_context_sha256"),
                        "report": validated,
                        "response_validation_audit": audit,
                        "choice_probabilities": probabilities,
                    }
                )
                timings.append(
                    {
                        "panel_number": source["panel_number"],
                        "seconds": round(panel_seconds, 4),
                        **copy.deepcopy(
                            dict(getattr(model_client, "last_timings", {}) or {})
                        ),
                    }
                )
                _write_json_atomic(
                    staging / "medgemma_panel_reports.json", reports
                )
                if time.monotonic() - started > 180.0:
                    raise PipelineError("Caso v24 excedeu 180 segundos.")
                active_panel = None
            aggregated = validate_configured_medgemma_report(
                _aggregate_panel_reports(reports), config
            )
            elapsed = time.monotonic() - started
            if elapsed > 180.0:
                raise PipelineError("Agregação v24 excedeu 180 segundos.")
            input_panels = [
                {"image": row["relative_path"], "sha256": row["sha256"]}
                for row in case["panels"]
            ]
            maxima = {
                label: max(row["choice_probabilities"][label] for row in reports)
                for label in ("POSITIVA", "NEGATIVA", "INCONCLUSIVA")
            }
            envelope = {
                "case_id": case_id,
                "status": "pending_review",
                "regulatory_mode": "RESEARCH",
                **model_trace(config),
                "input_panels": input_panels,
                "input_panel_set_sha256": sha256_of_text(
                    "\n".join(
                        f"{row['image']}:{row['sha256']}" for row in input_panels
                    )
                ),
                "organ_mask_sent_to_model": False,
                "lesion_pre_marked": False,
                "screening_config_sha256": protocol["config_sha256"],
                "panel_manifest": case["manifest"],
                "report": aggregated,
                "panel_reports": reports,
                "aggregation_rule": AGGREGATION_RULE,
                "signal_rule": SIGNAL_RULE,
                "rag": {
                    **rag_context,
                    "context_file": (
                        "rag_context.json"
                        if rag_context.get("enabled") is True
                        else None
                    ),
                    "prompt_audit": prompt_audit,
                },
                "liver_enriched_max_positive_probability": maxima["POSITIVA"],
                "requires_human_review": True,
                "disclaimer": config["report"]["disclaimer"],
                "durations_seconds": {
                    "panel_inference": timings,
                    "screening_total": round(elapsed, 4),
                },
                "qualification": {
                    "schema": "argos-openswisshcc-v24-liver-enriched-trace-v1",
                    "protocol_signature": protocol["protocol_signature"],
                    "organ_mask_sent_to_model": False,
                    "labels_read": False,
                    "lesion_masks_read": 0,
                },
            }
            report_path = staging / "medgemma_report.json"
            _write_json_atomic(report_path, envelope)
            body = {
                "schema": CASE_SCHEMA,
                "case_id": case_id,
                "status": "success_pending_analysis",
                "prediction": aggregated["resultado_hipotese"],
                "panel_count": case["panel_count"],
                "panel_seconds": timings,
                "elapsed_seconds": round(elapsed, 4),
                "maximum_seconds": 180.0,
                "within_time_limit": True,
                "max_positive_probability": maxima["POSITIVA"],
                "max_negative_probability": maxima["NEGATIVA"],
                "max_inconclusive_probability": maxima["INCONCLUSIVA"],
                "signal_rule": SIGNAL_RULE,
                "report_sha256": _sha256(report_path),
                "protocol_signature": protocol["protocol_signature"],
                "labels_read": False,
                "lesion_masks_read": 0,
                "metrics_calculated": False,
            }
            result = {**body, "case_signature": _canonical_sha(body)}
            _write_json_atomic(staging / "inference_manifest.json", result)
            _publish_directory(staging, final_dir)
            results.append(result)
            _write_jsonl_atomic(output_root / "cases.checkpoint.jsonl", results)
        except Exception as exc:
            failure = {
                "schema": "argos-openswisshcc-v24-liver-enriched-inference-failure-v1",
                "case_id": case_id,
                "status": "technical_failure_no_final_report",
                "completed_panel_count": len(reports),
                "expected_panel_count": case["panel_count"],
                "failed_panel_number": (
                    active_panel.get("panel_number") if active_panel else None
                ),
                "elapsed_seconds": round(time.monotonic() - started, 4),
                "error_type": type(exc).__name__,
                "error": str(exc)[:1000],
                "protocol_signature": protocol["protocol_signature"],
                "labels_read": False,
                "lesion_masks_read": 0,
            }
            _write_json_atomic(staging / "inference_failure.json", failure)
            _publish_directory(staging, final_dir)
            raise
    cases_path = output_root / "cases.jsonl"
    _write_jsonl_atomic(cases_path, results)
    elapsed = [float(row["elapsed_seconds"]) for row in results]
    body = {
        "schema": RUN_SCHEMA,
        "status": "complete_predictions_frozen_pending_label_evaluation",
        "case_count": len(results),
        "protocol_case_count": 132,
        "technical_failure_case_count": 2,
        "technical_failures_count_as_primary_metric_errors": True,
        "panel_call_count": sum(row["panel_count"] for row in results),
        "protocol_signature": protocol["protocol_signature"],
        "cases_sha256": _sha256(cases_path),
        "maximum_allowed_seconds": 180.0,
        "maximum_case_seconds": round(max(elapsed), 4),
        "mean_case_seconds": round(sum(elapsed) / len(elapsed), 4),
        "all_cases_within_180_seconds": all(value <= 180.0 for value in elapsed),
        "total_wall_seconds": round(time.monotonic() - run_started, 4),
        "labels_read": False,
        "lesion_masks_read": 0,
        "metrics_calculated": False,
    }
    summary = {**body, "run_signature": _canonical_sha(body)}
    _write_json_atomic(output_root / "summary.json", summary)
    (output_root / "cases.checkpoint.jsonl").unlink(missing_ok=True)
    return summary


def verify_v24_liver_enriched_inference_run(
    *,
    source_protocol_path: Path,
    review_path: Path,
    gallery_root: Path,
    config_path: Path,
    panel_root: Path,
    full_verification_path: Path,
    inference_protocol_path: Path,
    output_root: Path,
    verification_output_path: Path | None = None,
    panel_config_path: Path | None = None,
    candidate_id: str | None = None,
    predecessor_evaluation_path: Path | None = None,
) -> dict[str, Any]:
    protocol, _cohort, _config = verify_v24_liver_enriched_inference_protocol(
        source_protocol_path=source_protocol_path,
        review_path=review_path,
        gallery_root=gallery_root,
        config_path=config_path,
        panel_root=panel_root,
        full_verification_path=full_verification_path,
        inference_protocol_path=inference_protocol_path,
        panel_config_path=panel_config_path,
        candidate_id=candidate_id,
        predecessor_evaluation_path=predecessor_evaluation_path,
    )
    root = Path(output_root).resolve()
    summary = _load(root / "summary.json", "Resumo de inferência v24")
    unsigned = dict(summary)
    signature = unsigned.pop("run_signature", None)
    if signature != _canonical_sha(unsigned):
        raise PipelineError("Assinatura da execução v24 inválida.")
    try:
        rows = [
            json.loads(line)
            for line in (root / "cases.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    except (OSError, json.JSONDecodeError) as exc:
        raise PipelineError("Casos da inferência v24 inválidos.") from exc
    validated = [
        _existing_case(output_root=root, case=case, protocol=protocol)
        for case in protocol["cases"]
    ]
    if rows != validated or len(rows) != 130:
        raise PipelineError("Casos da inferência v24 divergem do protocolo.")
    elapsed = [float(row["elapsed_seconds"]) for row in rows]
    if (
        summary.get("schema") != RUN_SCHEMA
        or summary.get("status")
        != "complete_predictions_frozen_pending_label_evaluation"
        or summary.get("case_count") != 130
        or summary.get("panel_call_count") != 390
        or summary.get("protocol_signature") != protocol["protocol_signature"]
        or summary.get("cases_sha256") != _sha256(root / "cases.jsonl")
        or summary.get("all_cases_within_180_seconds") is not True
        or max(elapsed) > 180.0
        or list(root.rglob("inference_failure.json"))
        or list(root.glob(".*.staging.*"))
    ):
        raise PipelineError("Execução v24 não passou na verificação independente.")
    predictions: dict[str, int] = {}
    for row in rows:
        key = str(row["prediction"])
        predictions[key] = predictions.get(key, 0) + 1
    body = {
        "schema": VERIFICATION_SCHEMA,
        "status": "verified_predictions_frozen_safe_to_evaluate",
        "case_count": 130,
        "protocol_case_count": 132,
        "technical_failure_case_count": 2,
        "panel_call_count": 390,
        "prediction_counts": dict(sorted(predictions.items())),
        "maximum_case_seconds": max(elapsed),
        "mean_case_seconds": sum(elapsed) / len(elapsed),
        "all_cases_within_180_seconds": True,
        "protocol_signature": protocol["protocol_signature"],
        "run_signature": summary["run_signature"],
        "labels_read": False,
        "lesion_masks_read": 0,
        "metrics_calculated": False,
    }
    verification = {**body, "verification_signature": _canonical_sha(body)}
    if verification_output_path is not None:
        output = Path(verification_output_path).resolve()
        if output.exists():
            raise PipelineError("Verificação da inferência v24 já existe.")
        _write_json_atomic(output, verification)
    return verification


__all__ = [
    "freeze_v24_liver_enriched_inference_protocol",
    "run_v24_liver_enriched_inference",
    "verify_v24_liver_enriched_inference_protocol",
    "verify_v24_liver_enriched_inference_run",
]
