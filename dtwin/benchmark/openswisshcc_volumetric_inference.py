"""Fail-closed MedGemma 4B inference over a frozen volumetric OpenSwissHCC set."""
from __future__ import annotations

import copy
import math
import shutil
import time
import uuid
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from dtwin.benchmark.openswisshcc_alignment import (
    _load_json,
    _publish_directory,
    _sha256,
)
from dtwin.benchmark.openswisshcc_volumetric_gate import (
    AGGREGATION_RULE,
    validate_volumetric_candidate,
    verify_volumetric_freeze,
)
from dtwin.core import PipelineError
from dtwin.medgemma_client import (
    build_medgemma_prompt,
    create_medgemma_client,
    load_screening_config,
    validate_configured_medgemma_report,
)
from dtwin.medgemma_screening import (
    PANEL_REPORTS_FILENAME,
    _aggregate_panel_reports,
    _partial_prompt,
    _write_json_atomic,
    build_report_envelope,
    sha256_of_text,
)

INFERENCE_SCHEMA = "argos-openswisshcc-volumetric-inference-case-v1"
RUN_SCHEMA = "argos-openswisshcc-volumetric-inference-run-v1"
FAILURE_SCHEMA = "argos-openswisshcc-volumetric-inference-failure-v1"


def _config_map(config_paths: Mapping[str, Path]) -> dict[str, Path]:
    return {str(key): Path(path).resolve() for key, path in config_paths.items()}


def _candidate_from_freeze(freeze: dict[str, Any], case_id: str) -> dict[str, Any]:
    matches = [item for item in freeze["candidates"] if item.get("case_id") == case_id]
    if len(matches) != 1:
        raise PipelineError("Caso nao possui exatamente um registro no freeze volumetrico.")
    return matches[0]


def _current_case(
    *, panel_root: Path, freeze: dict[str, Any], case_id: str,
) -> tuple[Path, dict[str, Any], dict[str, Any], dict[str, Any]]:
    current = validate_volumetric_candidate(panel_root, case_id)
    frozen = _candidate_from_freeze(freeze, case_id)
    expected = {key: frozen[key] for key in current}
    if current != expected:
        raise PipelineError("Candidato volumetrico mudou em relacao ao freeze.")
    case_dir = Path(panel_root).resolve() / case_id
    candidate = _load_json(case_dir / "candidate_manifest.json")
    manifest = _load_json(case_dir / str(current["panel_manifest_filename"]))
    return case_dir, candidate, manifest, frozen


def _failure_payload(
    *, case_id: str, freeze: dict[str, Any], candidate: dict[str, Any],
    completed: list[dict[str, Any]], failed_panel: dict[str, Any] | None,
    error: Exception, elapsed: float,
) -> dict[str, Any]:
    return {
        "schema": FAILURE_SCHEMA,
        "case_id": case_id,
        "status": "technical_failure_no_final_report",
        "failure_stage": "panel_inference" if failed_panel else "aggregation_or_persistence",
        "error": {"type": type(error).__name__, "message": str(error)[:1000]},
        "completed_panel_count": len(completed),
        "expected_panel_count": candidate.get("panel_image_count"),
        "failed_panel": (
            {key: failed_panel.get(key) for key in (
                "panel_number", "panel_total", "image", "sha256", "axial_interval"
            )}
            if failed_panel else None
        ),
        "elapsed_seconds": round(float(elapsed), 4),
        "experiment_signature": freeze["experiment_signature"],
        "candidate_signature": candidate["candidate_signature"],
        "panel_set_sha256": candidate["panel_set_sha256"],
        "research_only": True,
        "clinical_use_allowed": False,
        "requires_human_review": True,
        "ground_truth_read": False,
        "metrics_calculated": False,
    }


def _set_remaining_timeout(client: Any, original: int, remaining: float) -> None:
    """Bound the next HTTP call by the remaining case deadline when supported."""
    med = getattr(client, "med", None)
    if isinstance(med, dict):
        med["timeout_seconds"] = max(1, min(int(original), int(math.floor(remaining))))


def infer_frozen_volumetric_case(
    *, case_id: str, panel_root: Path, review_path: Path, freeze_path: Path,
    config_paths: Mapping[str, Path], output_root: Path, expected_case_count: int = 88,
    client: Any | None = None, verified_freeze: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Infer one complete case atomically; never emit a partial final report."""
    paths = _config_map(config_paths)
    freeze = verified_freeze or verify_volumetric_freeze(
        freeze_path=freeze_path,
        panel_root=panel_root,
        review_path=review_path,
        config_paths=paths,
        expected_case_count=expected_case_count,
    )
    max_case_seconds = float(freeze["max_case_seconds"])
    case_dir, candidate, panel_manifest, frozen = _current_case(
        panel_root=panel_root, freeze=freeze, case_id=case_id
    )
    config_key = str(frozen["config_key"])
    if config_key not in paths:
        raise PipelineError("Freeze referencia configuracao nao fornecida.")
    config = load_screening_config(paths[config_key])
    if _sha256(paths[config_key]) != candidate.get("config_sha256"):
        raise PipelineError("Config atual nao corresponde ao candidato renderizado.")
    if config["medgemma"].get("response_mode") != "choice_classification":
        raise PipelineError("Executor volumetrico exige choice_classification.")
    base_prompt = build_medgemma_prompt(config)
    if candidate.get("candidate_kind") == "venous_single_phase_fallback":
        base_prompt += (
            "\n\nCONTEXTO TECNICO: este caso usa somente a fase venosa porque a "
            "representacao multifasica nao passou pelo gate tecnico/visual. Nao presuma "
            "realce arterial, washout ou informacao tardia ausente."
        )
    max_prompt_chars = int(config["medgemma"].get("max_prompt_chars", 12000))
    if len(base_prompt) > max_prompt_chars:
        raise PipelineError("Prompt base excede max_prompt_chars.")

    output_root = Path(output_root).resolve()
    final_dir = output_root / case_id
    if final_dir.exists():
        raise PipelineError("Saida do caso ja existe; nao sera sobrescrita.")
    output_root.mkdir(parents=True, exist_ok=True)
    staging = output_root / f".{case_id}.staging.{uuid.uuid4().hex}"
    staging.mkdir()
    started = time.monotonic()
    reports: list[dict[str, Any]] = []
    timings: list[dict[str, Any]] = []
    failed_record: dict[str, Any] | None = None
    model_client = client if client is not None else create_medgemma_client(config)
    original_timeout = int(config["medgemma"]["timeout_seconds"])
    try:
        for record in frozen["panels"]:
            failed_record = record
            elapsed_before = time.monotonic() - started
            remaining = max_case_seconds - elapsed_before
            if remaining <= 1:
                raise PipelineError("Teto de 180 segundos esgotado antes do proximo painel.")
            _set_remaining_timeout(model_client, original_timeout, remaining)
            panel_prompt = _partial_prompt(base_prompt, record)
            if len(panel_prompt) > max_prompt_chars:
                raise PipelineError("Prompt parcial excede max_prompt_chars.")
            panel_path = case_dir / str(record["image"])
            panel_started = time.monotonic()
            raw_report = model_client.generate(panel_path, panel_prompt)
            validated = validate_configured_medgemma_report(raw_report, config)
            panel_elapsed = time.monotonic() - panel_started
            total_elapsed = time.monotonic() - started
            if total_elapsed > max_case_seconds:
                raise PipelineError(
                    f"Caso excedeu o teto operacional: {total_elapsed:.3f}s > {max_case_seconds:.3f}s."
                )
            entry = {
                "panel_number": record["panel_number"],
                "panel_total": record["panel_total"],
                "image": record["image"],
                "sha256": record["sha256"],
                "axial_interval": record.get("axial_interval"),
                "prompt_sha256": sha256_of_text(panel_prompt),
                "report": validated,
            }
            audit = getattr(model_client, "last_response_audit", None)
            if isinstance(audit, dict) and audit:
                entry["response_validation_audit"] = copy.deepcopy(audit)
            reports.append(entry)
            timings.append({
                "panel_number": record["panel_number"],
                "seconds": round(panel_elapsed, 4),
                **copy.deepcopy(dict(getattr(model_client, "last_timings", {}) or {})),
            })
            _write_json_atomic(staging / PANEL_REPORTS_FILENAME, reports)
            failed_record = None

        aggregated = _aggregate_panel_reports(reports)
        elapsed = time.monotonic() - started
        if elapsed > max_case_seconds:
            raise PipelineError("Agregacao ultrapassou o teto operacional por caso.")
        envelope = build_report_envelope(
            case_id=case_id,
            config=config,
            panel_filename=frozen["panels"][0]["image"],
            panel_manifest_filename=frozen["panel_manifest_filename"],
            panel_manifest=panel_manifest,
            screening_config_sha256=frozen["config_effective_sha256"],
            report=aggregated,
            durations_seconds={
                "panel_generation": 0.0,
                "panel_inference": timings,
                "medgemma_inference": round(sum(item["seconds"] for item in timings), 4),
                "screening_total": round(elapsed, 4),
            },
            panel_reports=reports,
            aggregation_rule=AGGREGATION_RULE,
        )
        envelope["qualification"] = {
            "schema": "argos-openswisshcc-volumetric-qualification-trace-v1",
            "experiment_signature": freeze["experiment_signature"],
            "review_signature": freeze["review_signature"],
            "candidate_signature": frozen["candidate_signature"],
            "candidate_version": frozen["candidate_version"],
            "candidate_kind": frozen["candidate_kind"],
            "panel_set_sha256": frozen["panel_set_sha256"],
            "panel_image_count": frozen["panel_image_count"],
            "coverage_sha256": frozen["coverage_sha256"],
            "effective_config_sha256": frozen["config_effective_sha256"],
            "base_prompt_sha256": sha256_of_text(base_prompt),
            "aggregation_rule": AGGREGATION_RULE,
            "max_case_seconds": max_case_seconds,
            "ground_truth_read": False,
            "metrics_calculated": False,
        }
        report_path = staging / "medgemma_report.json"
        _write_json_atomic(report_path, envelope)
        inference_manifest = {
            "schema": INFERENCE_SCHEMA,
            "case_id": case_id,
            "status": "success_pending_human_review",
            "prediction": envelope["report"]["resultado_hipotese"],
            "panel_image_count": frozen["panel_image_count"],
            "panel_set_sha256": frozen["panel_set_sha256"],
            "report_sha256": _sha256(report_path),
            "review_signature": freeze["review_signature"],
            "experiment_signature": freeze["experiment_signature"],
            "candidate_signature": frozen["candidate_signature"],
            "effective_config_sha256": frozen["config_effective_sha256"],
            "elapsed_seconds": round(elapsed, 4),
            "max_case_seconds": max_case_seconds,
            "within_time_limit": True,
            "research_only": True,
            "clinical_use_allowed": False,
            "requires_human_review": True,
            "ground_truth_read": False,
            "metrics_calculated": False,
        }
        _write_json_atomic(staging / "inference_manifest.json", inference_manifest)
        _publish_directory(staging, final_dir)
        return inference_manifest
    except Exception as exc:
        elapsed = time.monotonic() - started
        failure = _failure_payload(
            case_id=case_id,
            freeze=freeze,
            candidate=candidate,
            completed=reports,
            failed_panel=failed_record,
            error=exc,
            elapsed=elapsed,
        )
        try:
            _write_json_atomic(staging / "inference_failure.json", failure)
            _publish_directory(staging, final_dir)
        except Exception:
            shutil.rmtree(staging, ignore_errors=True)
        raise


def _existing_case(output_root: Path, frozen: dict[str, Any], freeze: dict[str, Any]) -> dict[str, Any]:
    case_dir = Path(output_root).resolve() / str(frozen["case_id"])
    manifest_path = case_dir / "inference_manifest.json"
    if not manifest_path.is_file():
        failure_path = case_dir / "inference_failure.json"
        if failure_path.is_file():
            return _load_json(failure_path)
        raise PipelineError(f"Saida parcial/invalida existente para {frozen['case_id']}.")
    manifest = _load_json(manifest_path)
    report_path = case_dir / "medgemma_report.json"
    if (
        manifest.get("schema") != INFERENCE_SCHEMA
        or manifest.get("status") != "success_pending_human_review"
        or manifest.get("experiment_signature") != freeze["experiment_signature"]
        or manifest.get("candidate_signature") != frozen["candidate_signature"]
        or manifest.get("panel_set_sha256") != frozen["panel_set_sha256"]
        or not report_path.is_file()
        or _sha256(report_path) != manifest.get("report_sha256")
    ):
        raise PipelineError(f"Saida existente divergiu do freeze: {frozen['case_id']}.")
    return manifest


def run_frozen_volumetric_inference(
    *, panel_root: Path, review_path: Path, freeze_path: Path,
    config_paths: Mapping[str, Path], output_root: Path, expected_case_count: int = 88,
    progress: Callable[[dict[str, Any]], None] | None = None,
    client_factory: Callable[[dict[str, Any]], Any] = create_medgemma_client,
) -> dict[str, Any]:
    """Run/resume the complete frozen cohort without ever opening labels."""
    paths = _config_map(config_paths)
    freeze = verify_volumetric_freeze(
        freeze_path=freeze_path,
        panel_root=panel_root,
        review_path=review_path,
        config_paths=paths,
        expected_case_count=expected_case_count,
    )
    output_root = Path(output_root).resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    summary_path = output_root / "inference_summary.json"
    if summary_path.exists():
        summary = _load_json(summary_path)
        if summary.get("experiment_signature") != freeze["experiment_signature"]:
            raise PipelineError("Resumo existente pertence a outro experimento.")
        for frozen in freeze["candidates"]:
            _existing_case(output_root, frozen, freeze)
        return summary

    clients: dict[str, Any] = {}
    results: list[dict[str, Any]] = []
    run_started = time.monotonic()
    for sequence, frozen in enumerate(freeze["candidates"], start=1):
        case_id = str(frozen["case_id"])
        if (output_root / case_id).exists():
            result = _existing_case(output_root, frozen, freeze)
            result = {**result, "cache_reused": True}
        else:
            key = str(frozen["config_key"])
            if key not in clients:
                clients[key] = client_factory(load_screening_config(paths[key]))
            try:
                result = infer_frozen_volumetric_case(
                    case_id=case_id,
                    panel_root=panel_root,
                    review_path=review_path,
                    freeze_path=freeze_path,
                    config_paths=paths,
                    output_root=output_root,
                    expected_case_count=expected_case_count,
                    client=clients[key],
                    verified_freeze=freeze,
                )
            except Exception as exc:
                result = _load_json(output_root / case_id / "inference_failure.json")
                result["raised_error"] = {"type": type(exc).__name__, "message": str(exc)[:500]}
        results.append(result)
        if progress is not None:
            progress({
                "sequence": sequence,
                "case_count": freeze["case_count"],
                "case_id": case_id,
                "status": result.get("status"),
                "elapsed_seconds": result.get("elapsed_seconds"),
            })

    successes = [item for item in results if item.get("status") == "success_pending_human_review"]
    failures = [item for item in results if item.get("status") != "success_pending_human_review"]
    elapsed_values = [float(item["elapsed_seconds"]) for item in successes]
    summary = {
        "schema": RUN_SCHEMA,
        "status": "complete" if not failures and len(successes) == freeze["case_count"] else "technical_failure",
        "case_count": freeze["case_count"],
        "panel_image_count": freeze["panel_image_count"],
        "success_count": len(successes),
        "failure_count": len(failures),
        "failed_case_ids": [str(item.get("case_id")) for item in failures],
        "experiment_signature": freeze["experiment_signature"],
        "review_signature": freeze["review_signature"],
        "aggregation_rule": freeze["aggregation_rule"],
        "max_case_seconds": freeze["max_case_seconds"],
        "observed_max_case_seconds": round(max(elapsed_values), 4) if elapsed_values else None,
        "observed_mean_case_seconds": round(sum(elapsed_values) / len(elapsed_values), 4) if elapsed_values else None,
        "total_wall_seconds": round(time.monotonic() - run_started, 4),
        "all_cases_within_time_limit": bool(successes) and not failures and all(
            bool(item.get("within_time_limit")) for item in successes
        ),
        "research_only": True,
        "clinical_use_allowed": False,
        "requires_human_review": True,
        "ground_truth_read": False,
        "metrics_calculated": False,
    }
    _write_json_atomic(summary_path, summary)
    return summary
