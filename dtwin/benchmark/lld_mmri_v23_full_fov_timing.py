"""Frozen, label-blind MedGemma timing pilot for LLD-MMRI full-FOV 3x9 panels."""
from __future__ import annotations

import copy
import json
import math
import shutil
import time
import uuid
from pathlib import Path
from typing import Any

from dtwin.benchmark.lld_mmri_v23_full_fov_review import (
    validate_full_fov_review_sources,
    verify_full_fov_human_review,
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


PROTOCOL_SCHEMA = "argos-lld-mmri-v23-full-fov-3x9-timing-protocol-v1"
CASE_SCHEMA = "argos-lld-mmri-v23-full-fov-3x9-timing-case-v1"
RUN_SCHEMA = "argos-lld-mmri-v23-full-fov-3x9-timing-run-v1"
AGGREGATION_RULE = "any_positive_else_any_inconclusive_else_all_negative"


def _load(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PipelineError(f"{label} ausente ou invalido.") from exc
    if not isinstance(value, dict):
        raise PipelineError(f"{label} deve ser objeto JSON.")
    return value


def freeze_full_fov_timing_protocol(
    *, panel_root: Path, gallery_root: Path, review_path: Path,
    config_path: Path, output_path: Path, maximum_seconds: float = 180.0,
) -> dict[str, Any]:
    if (
        isinstance(maximum_seconds, bool)
        or not isinstance(maximum_seconds, (int, float))
        or not math.isfinite(float(maximum_seconds))
        or float(maximum_seconds) != 180.0
    ):
        raise PipelineError("Piloto temporal full-FOV exige teto congelado de 180 segundos.")
    panel_root = Path(panel_root).resolve()
    gallery_root = Path(gallery_root).resolve()
    review_path = Path(review_path).resolve()
    config_path = Path(config_path).resolve()
    cohort, gallery = validate_full_fov_review_sources(
        panel_root=panel_root, gallery_root=gallery_root,
    )
    review = verify_full_fov_human_review(
        panel_root=panel_root, gallery_root=gallery_root, review_path=review_path,
    )
    if _sha256(config_path) != cohort.get("config_sha256"):
        raise PipelineError("Config full-FOV divergiu dos paineis revisados.")
    config = load_screening_config(config_path)
    if config.get("medgemma", {}).get("response_mode") != "choice_classification":
        raise PipelineError("Piloto temporal exige choice_classification.")
    prompt = build_medgemma_prompt(config)
    cases = [
        {
            "case_id": case["case_id"],
            "manifest": case["manifest"],
            "manifest_sha256": case["manifest_sha256"],
            "panels": copy.deepcopy(case["panels"]),
        }
        for case in cohort["cases"]
    ]
    base = {
        "schema": PROTOCOL_SCHEMA,
        "status": "frozen_before_blind_timing_inference",
        "case_count": cohort["case_count"],
        "case_ids": list(cohort["case_ids"]),
        "panel_image_count_per_case": 3,
        "total_panel_image_count": cohort["total_panel_image_count"],
        "cases": cases,
        "maximum_seconds_per_case": 180.0,
        "timing_scope": "three_sequential_panel_calls_plus_validation_aggregation_and_persistence",
        "full_dicom_end_to_end_gate_claimed": False,
        "aggregation_rule": AGGREGATION_RULE,
        "config_sha256": _sha256(config_path),
        "effective_prompt_sha256": sha256_of_text(prompt),
        "model_id": config["medgemma"]["model_id"],
        "model_version": config["medgemma"]["model_version"],
        "cohort_signature": cohort["cohort_signature"],
        "gallery_signature": gallery["gallery_signature"],
        "review_signature": review["review_signature"],
        "panel_cohort_sha256": _sha256(panel_root / "cohort_manifest.json"),
        "gallery_manifest_sha256": _sha256(gallery_root / "gallery_manifest.json"),
        "review_sha256": _sha256(review_path),
        "organ_masks_read": 0,
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
        raise PipelineError("Protocolo temporal full-FOV existente; sobrescrita recusada.")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    _write_json_atomic(output_path, protocol)
    return protocol


def verify_full_fov_timing_protocol(
    *, panel_root: Path, gallery_root: Path, review_path: Path,
    config_path: Path, protocol_path: Path,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    panel_root = Path(panel_root).resolve()
    gallery_root = Path(gallery_root).resolve()
    review_path = Path(review_path).resolve()
    config_path = Path(config_path).resolve()
    cohort, gallery = validate_full_fov_review_sources(
        panel_root=panel_root, gallery_root=gallery_root,
    )
    review = verify_full_fov_human_review(
        panel_root=panel_root, gallery_root=gallery_root, review_path=review_path,
    )
    protocol = _load(Path(protocol_path).resolve(), "Protocolo temporal full-FOV")
    unsigned = dict(protocol)
    signature = unsigned.pop("protocol_signature", None)
    config = load_screening_config(config_path)
    prompt = build_medgemma_prompt(config)
    if (
        protocol.get("schema") != PROTOCOL_SCHEMA
        or protocol.get("status") != "frozen_before_blind_timing_inference"
        or signature != _canonical_sha(unsigned)
        or protocol.get("case_count") != cohort["case_count"]
        or protocol.get("case_ids") != cohort["case_ids"]
        or protocol.get("panel_image_count_per_case") != 3
        or protocol.get("total_panel_image_count") != cohort["total_panel_image_count"]
        or protocol.get("maximum_seconds_per_case") != 180.0
        or protocol.get("aggregation_rule") != AGGREGATION_RULE
        or protocol.get("config_sha256") != _sha256(config_path)
        or protocol.get("config_sha256") != cohort["config_sha256"]
        or protocol.get("effective_prompt_sha256") != sha256_of_text(prompt)
        or protocol.get("cohort_signature") != cohort["cohort_signature"]
        or protocol.get("gallery_signature") != gallery["gallery_signature"]
        or protocol.get("review_signature") != review["review_signature"]
        or protocol.get("panel_cohort_sha256") != _sha256(panel_root / "cohort_manifest.json")
        or protocol.get("gallery_manifest_sha256") != _sha256(gallery_root / "gallery_manifest.json")
        or protocol.get("review_sha256") != _sha256(review_path)
        or protocol.get("organ_masks_read") != 0
        or protocol.get("lesion_masks_read") != 0
        or protocol.get("ground_truth_read") is not False
        or protocol.get("metrics_calculated") is not False
        or protocol.get("full_dicom_end_to_end_gate_claimed") is not False
    ):
        raise PipelineError("Protocolo temporal full-FOV invalido ou adulterado.")
    expected_cases = [
        {
            "case_id": case["case_id"],
            "manifest": case["manifest"],
            "manifest_sha256": case["manifest_sha256"],
            "panels": case["panels"],
        }
        for case in cohort["cases"]
    ]
    if protocol.get("cases") != expected_cases:
        raise PipelineError("Painel do protocolo temporal divergiu da coorte revisada.")
    return protocol, cohort, config


def _remaining_timeout(client: Any, original: int, remaining: float) -> None:
    med = getattr(client, "med", None)
    if isinstance(med, dict):
        med["timeout_seconds"] = max(1, min(original, int(math.floor(remaining))))


def _existing_case_result(
    *, output_root: Path, case: dict[str, Any], protocol: dict[str, Any],
) -> dict[str, Any] | None:
    case_id = str(case["case_id"])
    case_dir = output_root / case_id
    if not case_dir.exists():
        return None
    timing_path = case_dir / "timing_manifest.json"
    report_path = case_dir / "medgemma_report.json"
    if not timing_path.is_file() or not report_path.is_file():
        raise PipelineError(f"Saida temporal parcial/invalida existente: {case_id}.")
    result = _load(timing_path, "Manifesto temporal full-FOV")
    unsigned = dict(result)
    signature = unsigned.pop("case_signature", None)
    elapsed = result.get("elapsed_seconds")
    report = _load(report_path, "Relatorio MedGemma full-FOV")
    qualification = report.get("qualification")
    input_panels = report.get("input_panels")
    expected_inputs = [
        {"image": item["panel"], "sha256": item["panel_sha256"]}
        for item in case["panels"]
    ]
    if (
        result.get("schema") != CASE_SCHEMA
        or result.get("case_id") != case_id
        or result.get("status") != "success_pending_human_review"
        or signature != _canonical_sha(unsigned)
        or result.get("panel_image_count") != 3
        or not isinstance(result.get("panel_seconds"), list)
        or len(result["panel_seconds"]) != 3
        or isinstance(elapsed, bool)
        or not isinstance(elapsed, (int, float))
        or not math.isfinite(float(elapsed))
        or float(elapsed) < 0
        or result.get("maximum_seconds") != 180.0
        or result.get("within_time_limit") is not (float(elapsed) <= 180.0)
        or result.get("report_sha256") != _sha256(report_path)
        or result.get("protocol_signature") != protocol["protocol_signature"]
        or result.get("review_signature") != protocol["review_signature"]
        or result.get("full_dicom_end_to_end_gate_claimed") is not False
        or result.get("ground_truth_read") is not False
        or result.get("metrics_calculated") is not False
        or report.get("case_id") != case_id
        or input_panels != expected_inputs
        or not isinstance(report.get("panel_reports"), list)
        or len(report["panel_reports"]) != 3
        or not isinstance(qualification, dict)
        or qualification.get("protocol_signature") != protocol["protocol_signature"]
        or qualification.get("review_signature") != protocol["review_signature"]
        or qualification.get("organ_masks_read") != 0
        or qualification.get("lesion_masks_read") != 0
        or qualification.get("ground_truth_read") is not False
    ):
        raise PipelineError(f"Saida temporal existente divergiu do protocolo: {case_id}.")
    return result


def _write_jsonl_atomic(path: Path, rows: list[dict[str, Any]]) -> None:
    temporary = path.with_name(f".{path.name}.tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as stream:
        for row in rows:
            stream.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
        stream.flush()
    temporary.replace(path)


def run_full_fov_timing_pilot(
    *, panel_root: Path, gallery_root: Path, review_path: Path,
    config_path: Path, protocol_path: Path, output_root: Path,
    client: Any | None = None,
) -> dict[str, Any]:
    """Measure the frozen three-call path; this is not the raw-DICOM end-to-end gate."""
    protocol, _cohort, config = verify_full_fov_timing_protocol(
        panel_root=panel_root,
        gallery_root=gallery_root,
        review_path=review_path,
        config_path=config_path,
        protocol_path=protocol_path,
    )
    panel_root = Path(panel_root).resolve()
    output_root = Path(output_root).resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    model_client = client
    base_prompt = build_medgemma_prompt(config)
    max_prompt_chars = int(config["medgemma"].get("max_prompt_chars", 12000))
    original_timeout = int(config["medgemma"]["timeout_seconds"])
    case_results: list[dict[str, Any]] = []
    run_started = time.monotonic()
    for case in protocol["cases"]:
        case_id = str(case["case_id"])
        existing = _existing_case_result(
            output_root=output_root, case=case, protocol=protocol,
        )
        if existing is not None:
            case_results.append(existing)
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
        try:
            manifest_path = (panel_root / case["manifest"]).resolve()
            manifest = _load(manifest_path, "Manifesto de painel full-FOV")
            if _sha256(manifest_path) != case["manifest_sha256"]:
                raise PipelineError("Manifesto full-FOV divergiu do protocolo.")
            manifest_panels = manifest.get("panels")
            if not isinstance(manifest_panels, list) or len(manifest_panels) != 3:
                raise PipelineError("Manifesto full-FOV nao possui tres paineis.")
            for source, rendered in zip(case["panels"], manifest_panels, strict=True):
                if model_client is None:
                    model_client = create_medgemma_client(config)
                remaining = 180.0 - (time.monotonic() - started)
                if remaining <= 1.0:
                    raise PipelineError("Teto de 180 segundos esgotado antes do proximo painel.")
                _remaining_timeout(model_client, original_timeout, remaining)
                panel_number = int(source["panel_number"])
                panel_path = (panel_root / source["panel"]).resolve()
                if (
                    not panel_path.is_relative_to(panel_root)
                    or _sha256(panel_path) != source["panel_sha256"]
                    or rendered.get("panel_sha256") != source["panel_sha256"]
                ):
                    raise PipelineError("Painel full-FOV divergiu do protocolo congelado.")
                record = {
                    "panel_number": panel_number,
                    "panel_total": 3,
                    "image": panel_path.name,
                    "sha256": source["panel_sha256"],
                    "axial_interval": rendered.get("axial_range"),
                }
                prompt = _partial_prompt(base_prompt, record)
                if len(prompt) > max_prompt_chars:
                    raise PipelineError("Prompt parcial full-FOV excede o limite.")
                panel_started = time.monotonic()
                raw = model_client.generate(panel_path, prompt)
                validated = validate_configured_medgemma_report(raw, config)
                panel_seconds = time.monotonic() - panel_started
                if time.monotonic() - started > 180.0:
                    raise PipelineError("Piloto temporal full-FOV excedeu 180 segundos.")
                entry = {**record, "prompt_sha256": sha256_of_text(prompt), "report": validated}
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
            aggregated = _aggregate_panel_reports(reports)
            elapsed = time.monotonic() - started
            if elapsed > 180.0:
                raise PipelineError("Agregacao full-FOV ultrapassou 180 segundos.")
            aggregated = validate_configured_medgemma_report(aggregated, config)
            input_panels = [
                {"image": source["panel"], "sha256": source["panel_sha256"]}
                for source in case["panels"]
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
                "input_liver_mask_sha256": None,
                "organ_mask_used": False,
                "screening_config_sha256": protocol["config_sha256"],
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
                "coverage": {
                    "policy": manifest["spatial_policy"],
                    "total_distinct_axial_indices": manifest["views"]["total_distinct_axial_indices"],
                    "complete_voxel_coverage_claimed": False,
                },
            }
            envelope["qualification"] = {
                "schema": "argos-lld-mmri-v23-full-fov-3x9-trace-v1",
                "protocol_signature": protocol["protocol_signature"],
                "review_signature": protocol["review_signature"],
                "timing_scope": protocol["timing_scope"],
                "full_dicom_end_to_end_gate_claimed": False,
                "organ_masks_read": 0,
                "lesion_masks_read": 0,
                "ground_truth_read": False,
            }
            report_path = staging / "medgemma_report.json"
            _write_json_atomic(report_path, envelope)
            base = {
                "schema": CASE_SCHEMA,
                "case_id": case_id,
                "status": "success_pending_human_review",
                "prediction": aggregated["resultado_hipotese"],
                "panel_image_count": 3,
                "panel_seconds": timings,
                "elapsed_seconds": round(elapsed, 4),
                "maximum_seconds": 180.0,
                "within_time_limit": elapsed <= 180.0,
                "report_sha256": _sha256(report_path),
                "protocol_signature": protocol["protocol_signature"],
                "review_signature": protocol["review_signature"],
                "full_dicom_end_to_end_gate_claimed": False,
                "ground_truth_read": False,
                "metrics_calculated": False,
                "research_only": True,
                "clinical_use_allowed": False,
                "requires_human_review": True,
            }
            result = {**base, "case_signature": _canonical_sha(base)}
            _write_json_atomic(staging / "timing_manifest.json", result)
            _publish_directory(staging, final_dir)
            case_results.append(result)
        except Exception:
            shutil.rmtree(staging, ignore_errors=True)
            raise
    elapsed_values = [float(item["elapsed_seconds"]) for item in case_results]
    cases_path = output_root / "cases.jsonl"
    _write_jsonl_atomic(cases_path, case_results)
    base = {
        "schema": RUN_SCHEMA,
        "status": "complete_pending_analysis",
        "case_count": len(case_results),
        "panel_image_count": len(case_results) * 3,
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
        "organ_masks_read": 0,
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
        existing_summary = _load(summary_path, "Resumo temporal full-FOV")
        existing_unsigned = dict(existing_summary)
        existing_signature = existing_unsigned.pop("run_signature", None)
        comparable_existing = dict(existing_unsigned)
        comparable_current = dict(base)
        comparable_existing.pop("total_wall_seconds", None)
        comparable_current.pop("total_wall_seconds", None)
        if (
            existing_signature != _canonical_sha(existing_unsigned)
            or comparable_existing != comparable_current
        ):
            raise PipelineError("Resumo temporal existente divergiu dos casos persistidos.")
        return existing_summary
    _write_json_atomic(summary_path, summary)
    return summary


__all__ = [
    "AGGREGATION_RULE",
    "CASE_SCHEMA",
    "PROTOCOL_SCHEMA",
    "RUN_SCHEMA",
    "freeze_full_fov_timing_protocol",
    "run_full_fov_timing_pilot",
    "verify_full_fov_timing_protocol",
]
