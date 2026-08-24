"""Frozen timing protocol for LLD-MMRI v23 liver-enriched 2/3-panel inference."""
from __future__ import annotations

import copy
import json
import math
import shutil
import time
import uuid
from pathlib import Path
from typing import Any

from dtwin.benchmark.lld_mmri_v23_liver_enriched_review import (
    validate_liver_enriched_review_sources,
    verify_liver_enriched_human_review,
)
from dtwin.benchmark.openswisshcc_alignment import _publish_directory, _sha256
from dtwin.benchmark.openswisshcc_v20_fusion import _canonical_sha
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

PROTOCOL_SCHEMA = "argos-lld-mmri-v23-liver-enriched-timing-protocol-v1"
CASE_SCHEMA = "argos-lld-mmri-v23-liver-enriched-timing-case-v1"
RUN_SCHEMA = "argos-lld-mmri-v23-liver-enriched-timing-run-v1"
AGGREGATION_RULE = "any_positive_else_any_inconclusive_else_all_negative"


def _repo_root_from_config_path(path: Path) -> Path:
    resolved = Path(path).resolve()
    if resolved.parent.name == "configs":
        return resolved.parent.parent
    raise PipelineError("Configuração liver-enriched deve permanecer em configs/.")


def _validate_panel_reuse_config(
    *, cohort: dict[str, Any], config_path: Path, config: dict[str, Any]
) -> tuple[bool, str]:
    """Allow a distinct inference prompt only with the already reviewed panels.

    The panel-rendering configuration remains authoritative for pixels. A second
    configuration may be used solely for inference when it explicitly opts in,
    preserves the liver-enriched layout and uses choice classification.
    """
    source_sha = str(cohort.get("config_sha256") or "")
    inference_sha = _sha256(config_path)
    if inference_sha == source_sha:
        return False, source_sha
    panel = config.get("panel", {})
    if (
        panel.get("reuse_approved_liver_enriched_panels") is not True
        or panel.get("spatial_focus") != "liver_enriched_full_fov"
        or int(panel.get("panel_image_count", 0)) != 3
        or int(panel.get("axial_slices", 0)) != 9
        or config.get("medgemma", {}).get("response_mode") != "choice_classification"
    ):
        raise PipelineError(
            "Configuração de inferência distinta não declarou reutilização compatível dos painéis liver-enriched aprovados."
        )
    return True, source_sha


def _load(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PipelineError(f"{label} ausente ou invalido.") from exc
    if not isinstance(value, dict):
        raise PipelineError(f"{label} deve ser objeto JSON.")
    return value


def _protocol_cases(cohort: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "case_id": case["case_id"],
            "selection_mode": case["selection_mode"],
            "localizer_stable": case["localizer_stable"],
            "panel_image_count": case["panel_image_count"],
            "manifest": case["manifest"],
            "manifest_sha256": case["manifest_sha256"],
            "panels": copy.deepcopy(case["panels"]),
        }
        for case in cohort["cases"]
    ]


def freeze_liver_enriched_timing_protocol(
    *, panel_root: Path, gallery_root: Path, review_path: Path,
    config_path: Path, output_path: Path, maximum_seconds: float = 180.0,
) -> dict[str, Any]:
    if (
        isinstance(maximum_seconds, bool)
        or not isinstance(maximum_seconds, (int, float))
        or not math.isfinite(float(maximum_seconds))
        or float(maximum_seconds) != 180.0
    ):
        raise PipelineError("Protocolo liver-enriched exige teto de 180 segundos.")
    panel_root = Path(panel_root).resolve()
    gallery_root = Path(gallery_root).resolve()
    review_path = Path(review_path).resolve()
    config_path = Path(config_path).resolve()
    cohort, gallery = validate_liver_enriched_review_sources(
        panel_root=panel_root, gallery_root=gallery_root,
    )
    review = verify_liver_enriched_human_review(
        panel_root=panel_root, gallery_root=gallery_root, review_path=review_path,
    )
    config = load_screening_config(config_path)
    reused_panels, panel_source_config_sha256 = _validate_panel_reuse_config(
        cohort=cohort, config_path=config_path, config=config,
    )
    if config.get("medgemma", {}).get("response_mode") != "choice_classification":
        raise PipelineError("Protocolo liver-enriched exige choice_classification.")
    prompt = build_medgemma_prompt(config)
    rag_context = build_rag_context(
        config=config, repo_root=_repo_root_from_config_path(config_path)
    )
    prompt, prompt_audit = append_rag_to_prompt(
        prompt, rag_context,
        max_prompt_chars=int(config["medgemma"].get("max_prompt_chars", 12000)),
    )
    cases = _protocol_cases(cohort)
    protocol_case_count = int(cohort.get("protocol_case_count", cohort["case_count"]))
    technical_failure_ids = list(cohort.get("technical_failure_case_ids", []))
    technical_failure_count = int(cohort.get("technical_failure_case_count", 0))
    if (
        protocol_case_count != cohort["case_count"] + technical_failure_count
        or len(technical_failure_ids) != technical_failure_count
        or len(set(technical_failure_ids)) != technical_failure_count
        or set(technical_failure_ids) & set(cohort["case_ids"])
    ):
        raise PipelineError("Contrato de falhas tecnicas liver-enriched invalido.")
    base = {
        "schema": PROTOCOL_SCHEMA,
        "status": "frozen_before_blind_timing_inference",
        "case_count": cohort["case_count"],
        "protocol_case_count": protocol_case_count,
        "inference_eligible_case_count": cohort["case_count"],
        "technical_failure_case_count": technical_failure_count,
        "technical_failure_case_ids": technical_failure_ids,
        "technical_failures_excluded_from_inference": True,
        "technical_failures_count_as_primary_metric_errors": True,
        "case_ids": list(cohort["case_ids"]),
        "stable_3panel_case_count": cohort["stable_localizer_case_count"],
        "fallback_2panel_case_count": cohort["weak_localizer_fallback_case_count"],
        "total_panel_image_count": cohort["total_panel_image_count"],
        "cases": cases,
        "maximum_seconds_per_case": 180.0,
        "timing_scope": "sequential_2or3_panel_calls_plus_validation_aggregation_and_persistence",
        "full_dicom_end_to_end_gate_claimed": False,
        "aggregation_rule": AGGREGATION_RULE,
        "config_sha256": _sha256(config_path),
        "panel_source_config_sha256": panel_source_config_sha256,
        "reused_approved_panels_for_inference": reused_panels,
        "effective_prompt_sha256": sha256_of_text(prompt),
        "rag_context_sha256": rag_context.get("context_sha256") if rag_context.get("enabled") is True else None,
        "rag_enabled": rag_context.get("enabled") is True,
        "rag_prompt_addendum_sha256": prompt_audit.get("rag_addendum_sha256"),
        "model_id": config["medgemma"]["model_id"],
        "model_version": config["medgemma"]["model_version"],
        "cohort_signature": cohort["cohort_signature"],
        "gallery_signature": gallery["gallery_signature"],
        "review_signature": review["review_signature"],
        "panel_cohort_sha256": _sha256(panel_root / "cohort_manifest.json"),
        "gallery_manifest_sha256": _sha256(gallery_root / "gallery_manifest.json"),
        "review_sha256": _sha256(review_path),
        "organ_masks_rendered": 0,
        "lesion_masks_read": 0,
        "ground_truth_read": False,
        "metrics_calculated": False,
        "research_only": True,
        "clinical_use_allowed": False,
        "requires_human_review": True,
    }
    protocol = {**base, "protocol_signature": _canonical_sha(base)}
    output_path = Path(output_path).resolve()
    if output_path.exists():
        raise PipelineError("Protocolo temporal liver-enriched existente; sobrescrita recusada.")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    _write_json_atomic(output_path, protocol)
    return protocol


def verify_liver_enriched_timing_protocol(
    *, panel_root: Path, gallery_root: Path, review_path: Path,
    config_path: Path, protocol_path: Path,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    panel_root = Path(panel_root).resolve()
    gallery_root = Path(gallery_root).resolve()
    review_path = Path(review_path).resolve()
    config_path = Path(config_path).resolve()
    cohort, gallery = validate_liver_enriched_review_sources(
        panel_root=panel_root, gallery_root=gallery_root,
    )
    review = verify_liver_enriched_human_review(
        panel_root=panel_root, gallery_root=gallery_root, review_path=review_path,
    )
    protocol = _load(Path(protocol_path).resolve(), "Protocolo temporal liver-enriched")
    unsigned = dict(protocol)
    signature = unsigned.pop("protocol_signature", None)
    config = load_screening_config(config_path)
    reused_panels, panel_source_config_sha256 = _validate_panel_reuse_config(
        cohort=cohort, config_path=config_path, config=config,
    )
    prompt = build_medgemma_prompt(config)
    rag_context = build_rag_context(
        config=config, repo_root=_repo_root_from_config_path(config_path)
    )
    prompt, prompt_audit = append_rag_to_prompt(
        prompt, rag_context,
        max_prompt_chars=int(config["medgemma"].get("max_prompt_chars", 12000)),
    )
    if (
        protocol.get("schema") != PROTOCOL_SCHEMA
        or protocol.get("status") != "frozen_before_blind_timing_inference"
        or signature != _canonical_sha(unsigned)
        or protocol.get("case_count") != cohort["case_count"]
        or protocol.get("protocol_case_count")
        != cohort.get("protocol_case_count", cohort["case_count"])
        or protocol.get("inference_eligible_case_count") != cohort["case_count"]
        or protocol.get("technical_failure_case_count")
        != cohort.get("technical_failure_case_count", 0)
        or protocol.get("technical_failure_case_ids")
        != cohort.get("technical_failure_case_ids", [])
        or protocol.get("technical_failures_excluded_from_inference") is not True
        or protocol.get("technical_failures_count_as_primary_metric_errors") is not True
        or protocol.get("case_ids") != cohort["case_ids"]
        or protocol.get("stable_3panel_case_count") != cohort["stable_localizer_case_count"]
        or protocol.get("fallback_2panel_case_count") != cohort["weak_localizer_fallback_case_count"]
        or protocol.get("total_panel_image_count") != cohort["total_panel_image_count"]
        or protocol.get("cases") != _protocol_cases(cohort)
        or protocol.get("maximum_seconds_per_case") != 180.0
        or protocol.get("aggregation_rule") != AGGREGATION_RULE
        or protocol.get("config_sha256") != _sha256(config_path)
        or protocol.get("panel_source_config_sha256") != panel_source_config_sha256
        or protocol.get("reused_approved_panels_for_inference") is not reused_panels
        or protocol.get("effective_prompt_sha256") != sha256_of_text(prompt)
        or protocol.get("rag_context_sha256") != (rag_context.get("context_sha256") if rag_context.get("enabled") is True else None)
        or protocol.get("rag_enabled") is not (rag_context.get("enabled") is True)
        or protocol.get("rag_prompt_addendum_sha256") != prompt_audit.get("rag_addendum_sha256")
        or protocol.get("cohort_signature") != cohort["cohort_signature"]
        or protocol.get("gallery_signature") != gallery["gallery_signature"]
        or protocol.get("review_signature") != review["review_signature"]
        or protocol.get("panel_cohort_sha256") != _sha256(panel_root / "cohort_manifest.json")
        or protocol.get("gallery_manifest_sha256") != _sha256(gallery_root / "gallery_manifest.json")
        or protocol.get("review_sha256") != _sha256(review_path)
        or protocol.get("organ_masks_rendered") != 0
        or protocol.get("lesion_masks_read") != 0
        or protocol.get("ground_truth_read") is not False
        or protocol.get("metrics_calculated") is not False
        or protocol.get("full_dicom_end_to_end_gate_claimed") is not False
    ):
        raise PipelineError("Protocolo temporal liver-enriched invalido ou adulterado.")
    return protocol, cohort, config


def _set_remaining_timeout(client: Any, original: int, remaining: float) -> None:
    med = getattr(client, "med", None)
    if isinstance(med, dict):
        med["timeout_seconds"] = max(1, min(original, int(math.floor(remaining))))


def _existing_case(
    *, output_root: Path, case: dict[str, Any], protocol: dict[str, Any],
) -> dict[str, Any] | None:
    case_id = str(case["case_id"])
    case_dir = output_root / case_id
    if not case_dir.exists():
        return None
    failure = case_dir / "timing_failure.json"
    if failure.is_file():
        raise PipelineError(f"Falha temporal liver-enriched preservada: {case_id}.")
    timing_path = case_dir / "timing_manifest.json"
    report_path = case_dir / "medgemma_report.json"
    if not timing_path.is_file() or not report_path.is_file():
        raise PipelineError(f"Saida temporal liver-enriched parcial: {case_id}.")
    result = _load(timing_path, "Manifesto temporal liver-enriched")
    unsigned = dict(result)
    signature = unsigned.pop("case_signature", None)
    report = _load(report_path, "Relatorio MedGemma liver-enriched")
    expected_count = int(case["panel_image_count"])
    elapsed = result.get("elapsed_seconds")
    qualification = report.get("qualification")
    expected_inputs = [
        {"image": panel["panel"], "sha256": panel["panel_sha256"]}
        for panel in case["panels"]
    ]
    if (
        result.get("schema") != CASE_SCHEMA
        or result.get("case_id") != case_id
        or result.get("status") != "success_pending_human_review"
        or signature != _canonical_sha(unsigned)
        or result.get("panel_image_count") != expected_count
        or not isinstance(result.get("panel_seconds"), list)
        or len(result["panel_seconds"]) != expected_count
        or isinstance(elapsed, bool)
        or not isinstance(elapsed, (int, float))
        or not math.isfinite(float(elapsed))
        or float(elapsed) < 0
        or result.get("maximum_seconds") != 180.0
        or result.get("within_time_limit") is not (float(elapsed) <= 180.0)
        or result.get("report_sha256") != _sha256(report_path)
        or result.get("protocol_signature") != protocol["protocol_signature"]
        or result.get("review_signature") != protocol["review_signature"]
        or result.get("ground_truth_read") is not False
        or report.get("case_id") != case_id
        or report.get("input_panels") != expected_inputs
        or len(report.get("panel_reports", [])) != expected_count
        or not isinstance(qualification, dict)
        or qualification.get("protocol_signature") != protocol["protocol_signature"]
        or qualification.get("review_signature") != protocol["review_signature"]
        or qualification.get("organ_mask_sent_to_model") is not False
        or qualification.get("lesion_masks_read") != 0
        or qualification.get("ground_truth_read") is not False
    ):
        raise PipelineError(f"Saida temporal liver-enriched divergiu: {case_id}.")
    return result


def _write_jsonl_atomic(path: Path, rows: list[dict[str, Any]]) -> None:
    temporary = path.with_name(f".{path.name}.tmp")
    try:
        with temporary.open("w", encoding="utf-8", newline="\n") as stream:
            for row in rows:
                stream.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
            stream.flush()
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def run_liver_enriched_timing_pilot(
    *, panel_root: Path, gallery_root: Path, review_path: Path,
    config_path: Path, protocol_path: Path, output_root: Path,
    client: Any | None = None,
) -> dict[str, Any]:
    """Run/resume frozen 2/3-panel inference timing; no labels are opened."""
    protocol, _cohort, config = verify_liver_enriched_timing_protocol(
        panel_root=panel_root, gallery_root=gallery_root,
        review_path=review_path, config_path=config_path,
        protocol_path=protocol_path,
    )
    panel_root = Path(panel_root).resolve()
    output_root = Path(output_root).resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    base_prompt = build_medgemma_prompt(config)
    rag_context = build_rag_context(
        config=config, repo_root=_repo_root_from_config_path(Path(config_path))
    )
    base_prompt, prompt_audit = append_rag_to_prompt(
        base_prompt, rag_context,
        max_prompt_chars=int(config["medgemma"].get("max_prompt_chars", 12000)),
    )
    if protocol.get("rag_context_sha256") != (
        rag_context.get("context_sha256") if rag_context.get("enabled") is True else None
    ) or protocol.get("rag_prompt_addendum_sha256") != prompt_audit.get("rag_addendum_sha256"):
        raise PipelineError("Contexto RAG divergiu do protocolo liver-enriched congelado.")
    if rag_context.get("enabled") is True:
        persist_rag_context(output_root / "rag_context.json", rag_context)
    max_prompt_chars = int(config["medgemma"].get("max_prompt_chars", 12000))
    original_timeout = int(config["medgemma"]["timeout_seconds"])
    model_client = client
    results: list[dict[str, Any]] = []
    run_started = time.monotonic()
    for case in protocol["cases"]:
        case_id = str(case["case_id"])
        existing = _existing_case(output_root=output_root, case=case, protocol=protocol)
        if existing is not None:
            results.append(existing)
            continue
        for stale in output_root.glob(f".{case_id}.staging.*"):
            if stale.is_dir():
                shutil.rmtree(stale)
        staging = output_root / f".{case_id}.staging.{uuid.uuid4().hex}"
        final_dir = output_root / case_id
        staging.mkdir()
        started = time.monotonic()
        reports: list[dict[str, Any]] = []
        timings: list[dict[str, Any]] = []
        active_panel: dict[str, Any] | None = None
        try:
            manifest_path = (panel_root / case["manifest"]).resolve()
            manifest = _load(manifest_path, "Manifesto liver-enriched")
            if _sha256(manifest_path) != case["manifest_sha256"]:
                raise PipelineError("Manifesto liver-enriched divergiu do protocolo.")
            manifest_panels = manifest.get("panels")
            expected_count = int(case["panel_image_count"])
            if not isinstance(manifest_panels, list) or len(manifest_panels) != expected_count:
                raise PipelineError("Quantidade de paineis liver-enriched divergiu.")
            for source, rendered in zip(case["panels"], manifest_panels, strict=True):
                active_panel = source
                remaining = 180.0 - (time.monotonic() - started)
                if remaining <= 1.0:
                    raise PipelineError("Teto de 180 segundos esgotado antes do proximo painel.")
                if model_client is None:
                    model_client = create_medgemma_client(config)
                _set_remaining_timeout(model_client, original_timeout, remaining)
                panel_number = int(source["panel_number"])
                panel_path = (panel_root / source["panel"]).resolve()
                if (
                    not panel_path.is_relative_to(panel_root)
                    or _sha256(panel_path) != source["panel_sha256"]
                    or rendered.get("sha256") != source["panel_sha256"]
                ):
                    raise PipelineError("Painel liver-enriched divergiu do protocolo.")
                record = {
                    "panel_number": panel_number,
                    "panel_total": expected_count,
                    "image": panel_path.name,
                    "sha256": source["panel_sha256"],
                    "axial_interval": rendered.get("axial_interval"),
                }
                prompt = _partial_prompt(base_prompt, record)
                if len(prompt) > max_prompt_chars:
                    raise PipelineError("Prompt liver-enriched excede o limite.")
                panel_started = time.monotonic()
                raw = model_client.generate(panel_path, prompt)
                validated = validate_configured_medgemma_report(raw, config)
                panel_seconds = time.monotonic() - panel_started
                if time.monotonic() - started > 180.0:
                    raise PipelineError("Caso liver-enriched excedeu 180 segundos.")
                entry = {
                    **record,
                    "prompt_sha256": sha256_of_text(prompt),
                    "rag_context_sha256": rag_context.get("context_sha256") if rag_context.get("enabled") is True else None,
                    "report": validated,
                }
                audit = getattr(model_client, "last_response_audit", None)
                if isinstance(audit, dict) and audit:
                    entry["response_validation_audit"] = copy.deepcopy(audit)
                reports.append(entry)
                timings.append({
                    "panel_number": panel_number,
                    "seconds": round(panel_seconds, 4),
                    **copy.deepcopy(dict(getattr(model_client, "last_timings", {}) or {})),
                })
                _write_json_atomic(staging / "medgemma_panel_reports.json", reports)
                active_panel = None
            aggregated = validate_configured_medgemma_report(
                _aggregate_panel_reports(reports), config,
            )
            elapsed = time.monotonic() - started
            if elapsed > 180.0:
                raise PipelineError("Agregacao liver-enriched ultrapassou 180 segundos.")
            input_panels = [
                {"image": panel["panel"], "sha256": panel["panel_sha256"]}
                for panel in case["panels"]
            ]
            envelope = {
                "case_id": case_id,
                "status": "pending_review",
                "regulatory_mode": "RESEARCH",
                **model_trace(config),
                "input_panel": input_panels[0]["image"],
                "input_panel_sha256": input_panels[0]["sha256"],
                "input_panels": input_panels,
                "input_panel_set_sha256": sha256_of_text(
                    "\n".join(f"{item['image']}:{item['sha256']}" for item in input_panels)
                ),
                "input_volume_sha256": manifest["input_volume_sha256"],
                "input_liver_mask_sha256": manifest["coarse_liver_mask_sha256"],
                "organ_mask_sent_to_model": False,
                "screening_config_sha256": protocol["config_sha256"],
                "panel_source_config_sha256": protocol["panel_source_config_sha256"],
                "reused_approved_panels_for_inference": protocol["reused_approved_panels_for_inference"],
                "panel_manifest": case["manifest"],
                "lesion_pre_marked": False,
                "report": aggregated,
                "requires_human_review": True,
                "disclaimer": config["report"]["disclaimer"],
                "durations_seconds": {
                    "panel_generation": 0.0,
                    "panel_inference": timings,
                    "medgemma_inference": round(sum(item["seconds"] for item in timings), 4),
                    "screening_total": round(elapsed, 4),
                },
                "panel_reports": reports,
                "aggregation_rule": AGGREGATION_RULE,
                "rag": {
                    **rag_context,
                    "context_file": "rag_context.json" if rag_context.get("enabled") is True else None,
                    "prompt_audit": prompt_audit,
                },
                "coverage": {
                    "policy": manifest["spatial_policy"],
                    "selection_mode": case["selection_mode"],
                    "total_distinct_axial_indices": manifest["views"]["total_distinct_axial_indices"],
                    "complete_voxel_coverage_claimed": False,
                },
                "qualification": {
                    "schema": "argos-lld-mmri-v23-liver-enriched-trace-v1",
                    "protocol_signature": protocol["protocol_signature"],
                    "review_signature": protocol["review_signature"],
                    "timing_scope": protocol["timing_scope"],
                    "full_dicom_end_to_end_gate_claimed": False,
                    "organ_mask_sent_to_model": False,
                    "lesion_masks_read": 0,
                    "ground_truth_read": False,
                },
            }
            report_path = staging / "medgemma_report.json"
            _write_json_atomic(report_path, envelope)
            base = {
                "schema": CASE_SCHEMA,
                "case_id": case_id,
                "status": "success_pending_human_review",
                "prediction": aggregated["resultado_hipotese"],
                "panel_image_count": expected_count,
                "selection_mode": case["selection_mode"],
                "panel_seconds": timings,
                "elapsed_seconds": round(elapsed, 4),
                "maximum_seconds": 180.0,
                "within_time_limit": elapsed <= 180.0,
                "report_sha256": _sha256(report_path),
                "protocol_signature": protocol["protocol_signature"],
                "review_signature": protocol["review_signature"],
                "ground_truth_read": False,
                "metrics_calculated": False,
                "research_only": True,
                "clinical_use_allowed": False,
                "requires_human_review": True,
            }
            result = {**base, "case_signature": _canonical_sha(base)}
            _write_json_atomic(staging / "timing_manifest.json", result)
            _publish_directory(staging, final_dir)
            results.append(result)
        except Exception as exc:
            failure = {
                "schema": "argos-lld-mmri-v23-liver-enriched-timing-failure-v1",
                "case_id": case_id,
                "status": "technical_failure_no_final_report",
                "completed_panel_count": len(reports),
                "expected_panel_count": case["panel_image_count"],
                "failed_panel_number": active_panel.get("panel_number") if active_panel else None,
                "elapsed_seconds": round(time.monotonic() - started, 4),
                "error_type": type(exc).__name__,
                "error": str(exc)[:1000],
                "protocol_signature": protocol["protocol_signature"],
                "ground_truth_read": False,
                "lesion_masks_read": 0,
            }
            _write_json_atomic(staging / "timing_failure.json", failure)
            _publish_directory(staging, final_dir)
            raise
    cases_path = output_root / "cases.jsonl"
    _write_jsonl_atomic(cases_path, results)
    elapsed_values = [float(item["elapsed_seconds"]) for item in results]
    base = {
        "schema": RUN_SCHEMA,
        "status": "complete_pending_analysis",
        "case_count": len(results),
        "protocol_case_count": protocol["protocol_case_count"],
        "inference_eligible_case_count": protocol["inference_eligible_case_count"],
        "technical_failure_case_count": protocol["technical_failure_case_count"],
        "technical_failure_case_ids": protocol["technical_failure_case_ids"],
        "technical_failures_excluded_from_inference": True,
        "technical_failures_count_as_primary_metric_errors": True,
        "stable_3panel_case_count": protocol["stable_3panel_case_count"],
        "fallback_2panel_case_count": protocol["fallback_2panel_case_count"],
        "panel_image_count": protocol["total_panel_image_count"],
        "protocol_signature": protocol["protocol_signature"],
        "review_signature": protocol["review_signature"],
        "cases_sha256": _sha256(cases_path),
        "maximum_allowed_seconds": 180.0,
        "max_panel_set_inference_seconds": round(max(elapsed_values), 4),
        "mean_panel_set_inference_seconds": round(sum(elapsed_values) / len(elapsed_values), 4),
        "all_cases_within_panel_set_time_limit": all(value <= 180.0 for value in elapsed_values),
        "timing_scope": protocol["timing_scope"],
        "full_dicom_end_to_end_gate_claimed": False,
        "total_wall_seconds": round(time.monotonic() - run_started, 4),
        "organ_mask_sent_to_model": False,
        "lesion_masks_read": 0,
        "ground_truth_read": False,
        "metrics_calculated": False,
        "research_only": True,
        "clinical_use_allowed": False,
        "requires_human_review": True,
    }
    summary = {**base, "run_signature": _canonical_sha(base)}
    summary_path = output_root / "summary.json"
    if summary_path.exists():
        prior = _load(summary_path, "Resumo temporal liver-enriched")
        prior_unsigned = dict(prior)
        prior_signature = prior_unsigned.pop("run_signature", None)
        current_compare = dict(base)
        prior_compare = dict(prior_unsigned)
        current_compare.pop("total_wall_seconds", None)
        prior_compare.pop("total_wall_seconds", None)
        if prior_signature != _canonical_sha(prior_unsigned) or prior_compare != current_compare:
            raise PipelineError("Resumo temporal liver-enriched divergiu dos casos.")
        return prior
    _write_json_atomic(summary_path, summary)
    return summary


def verify_liver_enriched_timing_run(
    *, panel_root: Path, gallery_root: Path, review_path: Path,
    config_path: Path, protocol_path: Path, output_root: Path,
) -> dict[str, Any]:
    """Independently validate a completed run without contacting the model."""
    protocol, _cohort, _config = verify_liver_enriched_timing_protocol(
        panel_root=panel_root, gallery_root=gallery_root,
        review_path=review_path, config_path=config_path,
        protocol_path=protocol_path,
    )
    output_root = Path(output_root).resolve()
    summary_path = output_root / "summary.json"
    cases_path = output_root / "cases.jsonl"
    summary = _load(summary_path, "Resumo temporal liver-enriched")
    unsigned = dict(summary)
    signature = unsigned.pop("run_signature", None)
    if signature != _canonical_sha(unsigned):
        raise PipelineError("Assinatura do resumo temporal liver-enriched invalida.")
    try:
        rows = [
            json.loads(line)
            for line in cases_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    except (OSError, json.JSONDecodeError) as exc:
        raise PipelineError("cases.jsonl temporal liver-enriched invalido.") from exc
    if not all(isinstance(row, dict) for row in rows):
        raise PipelineError("cases.jsonl temporal liver-enriched deve conter objetos.")
    validated = [
        _existing_case(output_root=output_root, case=case, protocol=protocol)
        for case in protocol["cases"]
    ]
    if any(item is None for item in validated) or rows != validated:
        raise PipelineError("Casos temporais liver-enriched divergem do protocolo.")
    elapsed = [float(row["elapsed_seconds"]) for row in rows]
    predictions: dict[str, int] = {}
    for row in rows:
        key = str(row["prediction"])
        predictions[key] = predictions.get(key, 0) + 1
    unexpected_dirs = sorted(
        path.name for path in output_root.iterdir()
        if path.is_dir() and path.name.startswith(".")
    )
    failures = sorted(output_root.rglob("timing_failure.json"))
    expected = {
        "schema": RUN_SCHEMA,
        "status": "complete_pending_analysis",
        "case_count": len(rows),
        "protocol_case_count": protocol["protocol_case_count"],
        "inference_eligible_case_count": protocol["inference_eligible_case_count"],
        "technical_failure_case_count": protocol["technical_failure_case_count"],
        "technical_failure_case_ids": protocol["technical_failure_case_ids"],
        "technical_failures_excluded_from_inference": True,
        "technical_failures_count_as_primary_metric_errors": True,
        "stable_3panel_case_count": protocol["stable_3panel_case_count"],
        "fallback_2panel_case_count": protocol["fallback_2panel_case_count"],
        "panel_image_count": protocol["total_panel_image_count"],
        "protocol_signature": protocol["protocol_signature"],
        "review_signature": protocol["review_signature"],
        "cases_sha256": _sha256(cases_path),
        "maximum_allowed_seconds": 180.0,
        "max_panel_set_inference_seconds": round(max(elapsed), 4),
        "mean_panel_set_inference_seconds": round(sum(elapsed) / len(elapsed), 4),
        "all_cases_within_panel_set_time_limit": all(value <= 180.0 for value in elapsed),
        "timing_scope": protocol["timing_scope"],
        "full_dicom_end_to_end_gate_claimed": False,
        "organ_mask_sent_to_model": False,
        "lesion_masks_read": 0,
        "ground_truth_read": False,
        "metrics_calculated": False,
        "research_only": True,
        "clinical_use_allowed": False,
        "requires_human_review": True,
    }
    for key, value in expected.items():
        if summary.get(key) != value:
            raise PipelineError(f"Resumo temporal liver-enriched divergiu em {key}.")
    if unexpected_dirs or failures:
        raise PipelineError("Execucao temporal liver-enriched contem staging ou falha residual.")
    return {
        "status": "verified_complete_label_blind",
        "case_count": len(rows),
        "protocol_case_count": protocol["protocol_case_count"],
        "technical_failure_case_count": protocol["technical_failure_case_count"],
        "technical_failures_count_as_primary_metric_errors": True,
        "panel_image_count": sum(int(row["panel_image_count"]) for row in rows),
        "prediction_counts": dict(sorted(predictions.items())),
        "maximum_seconds": max(elapsed),
        "mean_seconds": sum(elapsed) / len(elapsed),
        "all_within_180_seconds": all(value <= 180.0 for value in elapsed),
        "protocol_signature": protocol["protocol_signature"],
        "review_signature": protocol["review_signature"],
        "run_signature": summary["run_signature"],
        "ground_truth_read": False,
        "lesion_masks_read": 0,
    }


__all__ = [
    "AGGREGATION_RULE", "CASE_SCHEMA", "PROTOCOL_SCHEMA", "RUN_SCHEMA",
    "freeze_liver_enriched_timing_protocol", "run_liver_enriched_timing_pilot",
    "verify_liver_enriched_timing_protocol", "verify_liver_enriched_timing_run",
]
