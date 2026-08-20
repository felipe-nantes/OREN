"""Fallback venoso pré-declarado para candidatos OpenSwissHCC."""
from __future__ import annotations

import hashlib
import json
import shutil
import uuid
from pathlib import Path, PurePosixPath
from typing import Any

from dtwin.benchmark.openswisshcc_alignment import (
    _load_input_records,
    _load_json,
    _publish_directory,
    _resolve_record_files,
    _sha256,
)
from dtwin.core import PipelineError, load_profile
from dtwin.medgemma_client import load_screening_config, model_trace
from dtwin.medgemma_panel import generate_liver_panel

FALLBACK_VERSION = "openswisshcc-venous-fast-pathology-fallback-v1"
FALLBACK_REASON = "multiphase_alignment_gate_failure"
REVIEW_FALLBACK_VERSION = "openswisshcc-venous-review-remediation-v1"
REVIEW_FALLBACK_REASON = "human_review_alignment_or_framing_failure"
ALLOWED_FALLBACK_REASONS = frozenset({FALLBACK_REASON, REVIEW_FALLBACK_REASON})


def _signature(
    *,
    case_id: str,
    config_hash: str,
    profile_hash: str,
    venous_hash: str,
    mask_hash: str,
    candidate_version: str,
    fallback_reason: str,
) -> str:
    payload = {
        "candidate": candidate_version,
        "case_id": case_id,
        "config_sha256": config_hash,
        "profile_sha256": profile_hash,
        "venous_sha256": venous_hash,
        "liver_mask_sha256": mask_hash,
        "fallback_reason": fallback_reason,
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _write_json(path: Path, payload: object) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _reuse(
    case_dir: Path,
    signature: str,
    *,
    candidate_version: str,
    fallback_reason: str,
) -> dict[str, Any]:
    manifest = _load_json(case_dir / "candidate_manifest.json")
    if manifest.get("candidate_signature") != signature:
        raise PipelineError("Fallback existe com assinatura incompatível.")
    if manifest.get("candidate_kind") != "venous_single_phase_fallback":
        raise PipelineError("Destino existente não é o fallback venoso autorizado.")
    if manifest.get("candidate_version") != candidate_version:
        raise PipelineError("Versão do fallback existente é incompatível.")
    if manifest.get("fallback_reason") != fallback_reason:
        raise PipelineError("Motivo do fallback existente é incompatível.")
    relative = PurePosixPath(str(manifest.get("panel_filename", "")))
    panel = (case_dir / relative.name).resolve()
    if (
        relative.is_absolute()
        or ".." in relative.parts
        or len(relative.parts) != 1
        or not panel.is_relative_to(case_dir.resolve())
        or not panel.is_file()
    ):
        raise PipelineError("Cache do fallback aponta para painel inseguro ou ausente.")
    if _sha256(panel) != manifest.get("panel_sha256"):
        raise PipelineError("Hash do painel fallback é incompatível.")
    reused = dict(manifest)
    reused["cache_reused"] = True
    return reused


def render_venous_fallback_candidate(
    *,
    case_id: str,
    input_root: Path,
    output_root: Path,
    config_path: Path,
    profile_path: Path,
    fallback_reason: str = FALLBACK_REASON,
) -> dict[str, Any]:
    """Renderize um painel venoso sem acessar alinhamento, lesão ou ground truth."""
    input_root = Path(input_root).resolve()
    output_root = Path(output_root).resolve()
    config_path = Path(config_path).resolve()
    profile_path = Path(profile_path).resolve()
    if fallback_reason not in ALLOWED_FALLBACK_REASONS:
        raise PipelineError(f"Motivo de fallback não autorizado: {fallback_reason!r}.")
    candidate_version = (
        FALLBACK_VERSION
        if fallback_reason == FALLBACK_REASON
        else REVIEW_FALLBACK_VERSION
    )

    records = _load_input_records(input_root)
    if case_id not in records:
        raise PipelineError(f"case_id ausente no desenvolvimento: {case_id!r}.")
    input_files = _resolve_record_files(records[case_id], base=input_root, prefix="inputs")
    required = {"t1_venous", "liver_mask_venous"}
    if required - set(input_files):
        raise PipelineError("Caso sem fase ou máscara venosa para fallback.")

    config = load_screening_config(config_path)
    panel_config = config.get("panel", {})
    if panel_config.get("mode", "single_grayscale") != "single_grayscale":
        raise PipelineError("Fallback exige panel.mode=single_grayscale.")
    if (
        panel_config.get("strategy") != "uniform_9"
        or int(panel_config.get("axial_slices", 0)) != 9
    ):
        raise PipelineError("Fallback exige um único painel uniform_9 com nove cortes.")
    med = config.get("medgemma", {})
    if int(med.get("timeout_seconds", 0)) > 120 or int(med.get("max_retries", 1)) != 0:
        raise PipelineError("Fallback excede timeout/retries congelados.")
    if config.get("rag", {}).get("enabled") is not False:
        raise PipelineError("Fallback rápido não permite RAG.")

    volume_path, volume_hash = input_files["t1_venous"]
    mask_path, mask_hash = input_files["liver_mask_venous"]
    signature = _signature(
        case_id=case_id,
        config_hash=_sha256(config_path),
        profile_hash=_sha256(profile_path),
        venous_hash=volume_hash,
        mask_hash=mask_hash,
        candidate_version=candidate_version,
        fallback_reason=fallback_reason,
    )
    case_dir = output_root / case_id
    if case_dir.exists():
        return _reuse(
            case_dir,
            signature,
            candidate_version=candidate_version,
            fallback_reason=fallback_reason,
        )

    output_root.mkdir(parents=True, exist_ok=True)
    staging = output_root / f".{case_id}.staging.{uuid.uuid4().hex}"
    staging.mkdir()
    try:
        case_manifest = staging / "case_manifest.json"
        _write_json(
            case_manifest,
            {
                "case_id": case_id,
                "policy": "anonymize",
                "regulatory_state": "PESQUISA",
                "modality": "MRI",
            },
        )
        result = generate_liver_panel(
            volume_path=volume_path,
            liver_mask_path=mask_path,
            case_manifest_path=case_manifest,
            organ_profile=load_profile(profile_path),
            screening_config=config,
            output_dir=staging,
            model_trace=model_trace(config),
            visible_phi_confirmed=False,
        )
        candidate = {
            "schema": "argos-public-liver-mri-candidate-v1",
            "candidate_version": candidate_version,
            "candidate_kind": "venous_single_phase_fallback",
            "candidate_signature": signature,
            "fallback_reason": fallback_reason,
            "source_phase": "t1_venous",
            "case_id": case_id,
            "panel_filename": result.panel_path.name,
            "panel_sha256": _sha256(result.panel_path),
            "panel_bytes": result.panel_path.stat().st_size,
            "panel_manifest_filename": result.manifest_path.name,
            "config_sha256": _sha256(config_path),
            "visible_phi_confirmed": False,
            "eligible_for_inference": False,
            "cache_reused": False,
            "research_only": True,
            "clinical_use_allowed": False,
            "requires_human_review": True,
            "ground_truth_read": False,
        }
        _write_json(staging / "candidate_manifest.json", candidate)
        _publish_directory(staging, case_dir)
        return candidate
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
