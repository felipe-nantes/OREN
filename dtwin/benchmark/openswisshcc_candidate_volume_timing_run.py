"""Fail-closed v16 timing pilot for the reviewed four-case candidate bundle."""
from __future__ import annotations

import json
import shutil
import statistics
import tempfile
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dtwin.benchmark.openswisshcc_alignment import _publish_directory, _sha256
from dtwin.benchmark.openswisshcc_candidate_volume import (
    _input_index,
    _original_dynamic_inputs,
    _registered_or_none,
    build_candidate_volume_case,
)
from dtwin.benchmark.openswisshcc_candidate_volume_fallback import _validate_timing_plan
from dtwin.benchmark.openswisshcc_candidate_volume_score import (
    CASE_TIME_GATE_SECONDS,
    _load_protocol,
    _score_case,
    _score_url,
    _validate_candidate_stack,
    _validate_context,
    validate_candidate_volume_bundle,
    validate_candidate_volume_review,
)
from dtwin.benchmark.openswisshcc_candidate_volume_timing_bundle import _selected_timing_cases
from dtwin.benchmark.openswisshcc_highdimensional_inference import _atomic_json
from dtwin.core import PipelineError, sha256_of
from dtwin.medgemma_client import load_screening_config


PREFLIGHT_SCHEMA = "argos-openswisshcc-candidate-volume-timing-preflight-v16"
RUN_SCHEMA = "argos-openswisshcc-candidate-volume-timing-run-v16"


def _load_static_context(bundle_root: Path, review_path: Path, protocol_path: Path, config_path: Path):
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
        raise PipelineError("Contexto estatico do piloto temporal v16 divergiu.")
    return bundle, review, protocol


def _validate_plan_bundle_binding(bundle: dict, plan_path: Path, plan: dict) -> list[dict[str, Any]]:
    selected = _selected_timing_cases(plan)
    cohort = bundle["cohort"]
    if (
        cohort.get("source_timing_plan_sha256") != _sha256(plan_path)
        or cohort.get("source_timing_plan_signature") != plan["plan_signature"]
        or cohort.get("protocol", {}).get("case_time_gate_seconds") != CASE_TIME_GATE_SECONDS
        or cohort.get("timing_execution_started") is not False
        or [item["case_id"] for item in selected] != bundle["case_ids"]
        or [item["candidate_stack_count"] for item in selected]
        != [item["candidate_stack_count"] for item in bundle["cases"]]
    ):
        raise PipelineError("Bundle temporal v16 divergiu do plano assinado.")
    return selected


def projected_pipeline_seconds(known_preprocessing_seconds: float, fresh_reader_seconds: float) -> float:
    values = (float(known_preprocessing_seconds), float(fresh_reader_seconds))
    if any(value < 0 or not value < float("inf") for value in values):
        raise PipelineError("Tempo invalido no piloto temporal v16.")
    return values[0] + values[1]


def _fresh_case_descriptor(case_dir: Path, case_manifest: dict, reviewed_case: dict) -> dict[str, Any]:
    manifest_path = case_dir / "case_manifest.json"
    if sha256_of(manifest_path) != reviewed_case["case_manifest_sha256"]:
        raise PipelineError("Caso regenerado v16 divergiu do manifesto revisado.")
    stacks = case_manifest.get("candidate_stacks")
    if not isinstance(stacks, list) or len(stacks) != reviewed_case["candidate_stack_count"]:
        raise PipelineError("Stacks regenerados v16 divergiram do bundle revisado.")
    validated = []
    for expected, reviewed in zip(stacks, reviewed_case["candidate_stacks"], strict=True):
        if expected != {key: reviewed[key] for key in expected}:
            raise PipelineError("Registro de stack regenerado v16 divergiu do revisado.")
        candidate_dir = case_dir / expected["relative_directory"]
        _validate_candidate_stack(candidate_dir, expected)
        validated.append({**expected, "candidate_dir": candidate_dir})
    return {
        "case_id": reviewed_case["case_id"],
        "case_dir": case_dir,
        "case_manifest_sha256": reviewed_case["case_manifest_sha256"],
        "candidate_stack_count": len(validated),
        "candidate_stacks": validated,
    }


def _prepare_sources(
    *,
    plan: dict,
    bundle: dict,
    input_manifest: Path,
    input_root: Path,
    registration_root: Path,
    localizer_run: Path,
    expected_source_case_count: int,
) -> tuple[list[dict[str, Any]], dict, dict]:
    selected = _validate_plan_bundle_binding(bundle, Path(plan["_path"]), plan)
    morphology = _input_index(input_manifest, input_root)
    dynamic = _original_dynamic_inputs(input_manifest, input_root)
    if len(morphology) != expected_source_case_count or set(morphology) != set(dynamic):
        raise PipelineError("Coorte fonte do runner temporal v16 inesperada.")
    localizer_summary_path = Path(localizer_run).resolve() / "summary.json"
    if bundle["cohort"].get("source_localizer_summary_sha256") != _sha256(localizer_summary_path):
        raise PipelineError("Resumo do localizador mudou desde a revisao temporal v16.")
    if bundle["cohort"].get("input_manifest_sha256") != _sha256(Path(input_manifest).resolve()):
        raise PipelineError("Manifesto de inputs mudou desde a revisao temporal v16.")
    return selected, morphology, dynamic


def run_candidate_volume_timing_pilot(
    *,
    bundle_root: Path,
    review_path: Path,
    protocol_path: Path,
    config_path: Path,
    timing_plan_path: Path,
    localizer_run: Path,
    input_manifest: Path,
    input_root: Path,
    registration_root: Path,
    output_root: Path,
    work_root: Path,
    expected_source_case_count: int = 88,
    preflight_only: bool = False,
) -> dict[str, Any]:
    output_root = Path(output_root).resolve()
    if output_root.exists():
        raise PipelineError("Destino do piloto temporal v16 ja existe; sobrescrita recusada.")
    bundle, review, protocol = _load_static_context(bundle_root, review_path, protocol_path, config_path)
    timing_plan_path = Path(timing_plan_path).resolve()
    plan = _validate_timing_plan(timing_plan_path)
    plan["_path"] = timing_plan_path
    selected, morphology, dynamic = _prepare_sources(
        plan=plan,
        bundle=bundle,
        input_manifest=input_manifest,
        input_root=input_root,
        registration_root=registration_root,
        localizer_run=localizer_run,
        expected_source_case_count=expected_source_case_count,
    )
    health = None
    if not preflight_only:
        checked_bundle, checked_protocol, health = _validate_context(bundle_root, review_path, protocol_path, config_path)
        if checked_bundle["cohort_sha256"] != bundle["cohort_sha256"] or checked_protocol != protocol:
            raise PipelineError("Contexto ativo do backend divergiu do preflight temporal v16.")

    work_root = Path(work_root).resolve()
    work_root.mkdir(parents=True, exist_ok=True)
    output_root.parent.mkdir(parents=True, exist_ok=True)
    staging = output_root.parent / f"._v16timingrun_{uuid.uuid4().hex[:8]}"
    staging.mkdir()
    if not preflight_only:
        (staging / "predictions").mkdir()
    records = []
    pilot_started = time.monotonic()
    try:
        for selection, reviewed_case in zip(selected, bundle["cases"], strict=True):
            case_id = selection["case_id"]
            temporary = Path(tempfile.mkdtemp(prefix=f"v16_{case_id[-8:]}_", dir=work_root))
            try:
                registered = _registered_or_none(case_id, registration_root)
                if registered is None:
                    raise PipelineError("Caso do piloto temporal perdeu o registro publicado.")
                case_started = time.monotonic()
                render_started = time.monotonic()
                case_manifest = build_candidate_volume_case(
                    case_id=case_id,
                    morphology_source=morphology[case_id],
                    dynamic_source=dynamic[case_id],
                    registered_source=registered,
                    localizer_dir=Path(localizer_run).resolve() / case_id,
                    destination=temporary / case_id,
                )
                fresh_case = _fresh_case_descriptor(temporary / case_id, case_manifest, reviewed_case)
                rendering_seconds = time.monotonic() - render_started
                record = {
                    "scenario": selection["scenario"],
                    "case_id": case_id,
                    "candidate_stack_count": selection["candidate_stack_count"],
                    "reviewed_case_manifest_sha256": reviewed_case["case_manifest_sha256"],
                    "fresh_case_manifest_sha256": sha256_of(temporary / case_id / "case_manifest.json"),
                    "fresh_hash_match": True,
                    "rendering_elapsed_seconds": round(rendering_seconds, 4),
                    "known_alignment_localizer_seconds": selection["known_preprocessing_seconds"],
                }
                if preflight_only:
                    record.update(
                        {
                            "status": "preflight_passed_no_inference",
                            "candidate_scoring_elapsed_seconds": None,
                            "fresh_reader_wall_seconds": round(time.monotonic() - case_started, 4),
                            "projected_pipeline_seconds": None,
                            "projected_time_gate_passed": None,
                            "prediction_published": False,
                        }
                    )
                else:
                    prediction_path = staging / "predictions" / f"{case_id}.json"
                    scoring_started = time.monotonic()
                    prediction = _score_case(
                        case=fresh_case,
                        protocol=protocol,
                        health=health or {},
                        prediction_path=prediction_path,
                    )
                    scoring_seconds = time.monotonic() - scoring_started
                    fresh_wall = time.monotonic() - case_started
                    projected = projected_pipeline_seconds(selection["known_preprocessing_seconds"], fresh_wall)
                    gate_passed = projected <= CASE_TIME_GATE_SECONDS
                    if not gate_passed:
                        prediction_path.unlink(missing_ok=True)
                    record.update(
                        {
                            "status": "timing_passed" if gate_passed else "projected_time_gate_failed",
                            "candidate_scoring_elapsed_seconds": round(scoring_seconds, 4),
                            "reported_scoring_elapsed_seconds": prediction["scoring_elapsed_seconds"],
                            "fresh_reader_wall_seconds": round(fresh_wall, 4),
                            "projected_pipeline_seconds": round(projected, 4),
                            "projected_time_gate_passed": gate_passed,
                            "prediction_published": gate_passed,
                            "prediction_sha256": sha256_of(prediction_path) if gate_passed else None,
                        }
                    )
                records.append(record)
            finally:
                shutil.rmtree(temporary, ignore_errors=True)
        total_wall = time.monotonic() - pilot_started
        passed = preflight_only or all(item["projected_time_gate_passed"] is True for item in records)
        schema = PREFLIGHT_SCHEMA if preflight_only else RUN_SCHEMA
        result = {
            "schema": schema,
            "status": "preflight_complete_no_inference" if preflight_only else ("timing_gate_passed" if passed else "timing_gate_failed"),
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "protocol_signature": protocol["protocol_signature"],
            "review_signature": review["review_signature"],
            "timing_plan_signature": plan["plan_signature"],
            "bundle_cohort_sha256": bundle["cohort_sha256"],
            "model_id": protocol["model_id"],
            "model_version": protocol["model_version"],
            "case_time_gate_seconds": CASE_TIME_GATE_SECONDS,
            "case_count": len(records),
            "candidate_request_count": sum(item["candidate_stack_count"] for item in records),
            "cases": records,
            "pilot_wall_seconds": round(total_wall, 4),
            "timing_interpretation": {
                "fresh_measured": ["candidate_volume_rendering", "candidate_scoring", "fresh_reader_wall"],
                "historical_measured": ["alignment", "localizer"],
                "gate_formula": "known_alignment_localizer_seconds + fresh_reader_wall_seconds <= 180",
                "fresh_raw_dicom_end_to_end_measured": False,
                "full_pipeline_180_seconds_proven": False,
                "projected_pipeline_180_seconds_passed": None if preflight_only else passed,
            },
            "summary_seconds": None if preflight_only else {
                "maximum_projected_pipeline": max(item["projected_pipeline_seconds"] for item in records),
                "median_projected_pipeline": statistics.median(item["projected_pipeline_seconds"] for item in records),
                "maximum_fresh_reader_wall": max(item["fresh_reader_wall_seconds"] for item in records),
            },
            "full87_authorized_by_timing": False if preflight_only else passed,
            "inference_executed": not preflight_only,
            "ground_truth_read": False,
            "metrics_calculated": False,
            "holdout_opened": False,
            "accuracy_claimed": False,
            "research_only": True,
            "clinical_use_allowed": False,
            "requires_human_review": True,
        }
        _atomic_json(staging / ("preflight.json" if preflight_only else "timing_report.json"), result)
        _publish_directory(staging, output_root)
        return result
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
