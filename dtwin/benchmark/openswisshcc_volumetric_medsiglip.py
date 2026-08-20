"""Blinded MedSigLIP scoring of every panel in a frozen volumetric cohort."""
from __future__ import annotations

import hashlib
import json
import shutil
import statistics
import time
import uuid
from collections.abc import Callable, Mapping
from dataclasses import replace
from pathlib import Path
from typing import Any

from dtwin.benchmark.openswisshcc_alignment import (
    _load_json,
    _publish_directory,
    _sha256,
)
from dtwin.benchmark.openswisshcc_volumetric_gate import verify_volumetric_freeze
from dtwin.core import PipelineError
from dtwin.medsiglip_zero_shot import MedSigLIPScorer, load_medsiglip_config

CASE_SCHEMA = "argos-openswisshcc-volumetric-medsiglip-case-v1"
RUN_SCHEMA = "argos-openswisshcc-volumetric-medsiglip-run-v1"


def _prompt_bank_sha256(config: Any) -> str:
    payload = {
        "positive": list(config.positive_prompts),
        "negative": list(config.negative_prompts),
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _atomic_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def _verify_existing(
    *, case_dir: Path, frozen: dict[str, Any], experiment_signature: str,
    prompt_bank_sha256: str,
) -> dict[str, Any]:
    manifest_path = case_dir / "medsiglip_manifest.json"
    scores_path = case_dir / "medsiglip_panel_scores.json"
    if not manifest_path.is_file() or not scores_path.is_file():
        raise PipelineError(f"Cache MedSigLIP parcial: {frozen['case_id']}.")
    manifest = _load_json(manifest_path)
    if (
        manifest.get("schema") != CASE_SCHEMA
        or manifest.get("status") != "scores_only_no_decision"
        or manifest.get("experiment_signature") != experiment_signature
        or manifest.get("candidate_signature") != frozen["candidate_signature"]
        or manifest.get("panel_set_sha256") != frozen["panel_set_sha256"]
        or manifest.get("prompt_bank_sha256") != prompt_bank_sha256
        or _sha256(scores_path) != manifest.get("scores_sha256")
        or manifest.get("ground_truth_read") is not False
        or manifest.get("metrics_calculated") is not False
    ):
        raise PipelineError(f"Cache MedSigLIP divergiu: {frozen['case_id']}.")
    return manifest


def run_volumetric_medsiglip_scores(
    *, panel_root: Path, review_path: Path, freeze_path: Path,
    medgemma_config_paths: Mapping[str, Path], medsiglip_config_path: Path,
    local_model_path: Path, output_root: Path, expected_case_count: int = 88,
    device: str = "cuda", progress: Callable[[dict[str, Any]], None] | None = None,
    scorer_factory: Callable[..., Any] = MedSigLIPScorer,
) -> dict[str, Any]:
    """Score or resume all panels; never attach labels or emit a diagnosis."""
    freeze = verify_volumetric_freeze(
        freeze_path=freeze_path, panel_root=panel_root, review_path=review_path,
        config_paths=medgemma_config_paths, expected_case_count=expected_case_count,
    )
    config_path = Path(medsiglip_config_path).resolve()
    local_model = Path(local_model_path).resolve()
    if not local_model.is_dir() or not (local_model / "model.safetensors").is_file():
        raise PipelineError("Snapshot local MedSigLIP esta ausente ou incompleto.")
    config = replace(load_medsiglip_config(config_path), model_id=str(local_model))
    if config.decision_enabled:
        raise PipelineError("MedSigLIP deve permanecer sem decisao final.")
    prompt_hash = _prompt_bank_sha256(config)
    config_hash = _sha256(config_path)
    model_hash = _sha256(local_model / "model.safetensors")
    output_root = Path(output_root).resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    summary_path = output_root / "summary.json"
    if summary_path.exists():
        summary = _load_json(summary_path)
        if (
            summary.get("schema") != RUN_SCHEMA
            or summary.get("experiment_signature") != freeze["experiment_signature"]
            or summary.get("prompt_bank_sha256") != prompt_hash
            or summary.get("model_safetensors_sha256") != model_hash
        ):
            raise PipelineError("Resumo MedSigLIP existente pertence a outro experimento.")
        for frozen in freeze["candidates"]:
            _verify_existing(
                case_dir=output_root / str(frozen["case_id"]), frozen=frozen,
                experiment_signature=freeze["experiment_signature"],
                prompt_bank_sha256=prompt_hash,
            )
        return summary

    scorer = scorer_factory(config, local_files_only=True, device=device)
    run_started = time.monotonic()
    manifests: list[dict[str, Any]] = []
    failures: list[str] = []
    for sequence, frozen in enumerate(freeze["candidates"], start=1):
        case_id = str(frozen["case_id"])
        final_dir = output_root / case_id
        if final_dir.exists():
            manifest = _verify_existing(
                case_dir=final_dir, frozen=frozen,
                experiment_signature=freeze["experiment_signature"],
                prompt_bank_sha256=prompt_hash,
            )
        else:
            staging = output_root / f".{case_id}.staging.{uuid.uuid4().hex}"
            staging.mkdir()
            case_started = time.monotonic()
            panel_results: list[dict[str, Any]] = []
            try:
                panel_manifest = _load_json(
                    Path(panel_root).resolve() / case_id / str(frozen["panel_manifest_filename"])
                )
                source_panels = panel_manifest.get("panels")
                if not isinstance(source_panels, list) or len(source_panels) != frozen["panel_image_count"]:
                    raise PipelineError("Manifesto volumetrico nao contem todos os paineis.")
                for record, source in zip(frozen["panels"], source_panels, strict=True):
                    panel_started = time.monotonic()
                    score = scorer.score_panel(Path(panel_root).resolve() / case_id / str(record["image"]))
                    if score.get("panel_sha256") != record["sha256"] or score.get("final_decision") is not None:
                        raise PipelineError("Score MedSigLIP violou hash ou emitiu decisao final.")
                    axial_indices = source.get("axial_indices")
                    if not isinstance(axial_indices, list):
                        axial_interval = source.get("axial_interval")
                        if (
                            isinstance(axial_interval, list)
                            and len(axial_interval) == 2
                            and all(isinstance(value, int) for value in axial_interval)
                            and axial_interval[0] <= axial_interval[1]
                        ):
                            axial_indices = list(range(axial_interval[0], axial_interval[1] + 1))
                    if not isinstance(axial_indices, list) or not 1 <= len(axial_indices) <= 9:
                        raise PipelineError("Painel nao informa tiles axiais reais.")
                    panel_results.append({
                        "panel_number": record["panel_number"],
                        "panel_total": record["panel_total"],
                        "image": record["image"],
                        "sha256": record["sha256"],
                        "axial_indices": axial_indices,
                        "real_axial_tile_count": len(axial_indices),
                        "elapsed_seconds": round(time.monotonic() - panel_started, 4),
                        "score": score,
                    })
                    _atomic_json(staging / "medsiglip_panel_scores.json", panel_results)
                elapsed = time.monotonic() - case_started
                scores_path = staging / "medsiglip_panel_scores.json"
                manifest = {
                    "schema": CASE_SCHEMA,
                    "case_id": case_id,
                    "status": "scores_only_no_decision",
                    "candidate_signature": frozen["candidate_signature"],
                    "panel_set_sha256": frozen["panel_set_sha256"],
                    "panel_image_count": frozen["panel_image_count"],
                    "scores_sha256": _sha256(scores_path),
                    "experiment_signature": freeze["experiment_signature"],
                    "review_signature": freeze["review_signature"],
                    "medsiglip_config_sha256": config_hash,
                    "prompt_bank_sha256": prompt_hash,
                    "model_safetensors_sha256": model_hash,
                    "elapsed_seconds": round(elapsed, 4),
                    "final_decision": None,
                    "research_only": True,
                    "clinical_use_allowed": False,
                    "requires_human_review": True,
                    "ground_truth_read": False,
                    "metrics_calculated": False,
                }
                _atomic_json(staging / "medsiglip_manifest.json", manifest)
                _publish_directory(staging, final_dir)
            except Exception:
                shutil.rmtree(staging, ignore_errors=True)
                failures.append(case_id)
                raise
        manifests.append(manifest)
        if progress:
            progress({
                "sequence": sequence, "case_count": freeze["case_count"],
                "case_id": case_id, "elapsed_seconds": manifest["elapsed_seconds"],
                "status": manifest["status"],
            })

    elapsed_values = [float(item["elapsed_seconds"]) for item in manifests]
    summary = {
        "schema": RUN_SCHEMA,
        "status": "complete" if not failures and len(manifests) == freeze["case_count"] else "technical_failure",
        "case_count": freeze["case_count"],
        "panel_image_count": freeze["panel_image_count"],
        "success_count": len(manifests),
        "failure_count": len(failures),
        "failed_case_ids": failures,
        "experiment_signature": freeze["experiment_signature"],
        "review_signature": freeze["review_signature"],
        "medsiglip_config_sha256": config_hash,
        "prompt_bank_sha256": prompt_hash,
        "model_safetensors_sha256": model_hash,
        "mean_case_seconds": statistics.fmean(elapsed_values),
        "max_case_seconds": max(elapsed_values),
        "total_wall_seconds": round(time.monotonic() - run_started, 4),
        "final_decision": None,
        "research_only": True,
        "clinical_use_allowed": False,
        "requires_human_review": True,
        "ground_truth_read": False,
        "metrics_calculated": False,
    }
    _atomic_json(summary_path, summary)
    return summary


