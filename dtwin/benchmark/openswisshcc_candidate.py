"""Adapter do candidato multifásico OpenSwissHCC para o renderizador ARGOS."""
from __future__ import annotations

import hashlib
import json
import os
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
from dtwin.medgemma_panel_multiphase import generate_liver_panel_multiphase


CANDIDATE_VERSION = "openswisshcc-multiphase-fast-pathology-v1"


def _aligned_outputs(case_dir: Path, manifest: dict[str, Any]) -> dict[str, Path]:
    if manifest.get("case_id") != case_dir.name:
        raise PipelineError("Manifesto de alinhamento pertence a outro caso.")
    outputs: dict[str, Path] = {}
    root = case_dir.resolve()
    for item in manifest.get("outputs", []):
        phase = str(item.get("phase", ""))
        relative = PurePosixPath(str(item.get("filename", "")))
        if phase not in {"art", "del"} or phase in outputs:
            raise PipelineError("Fase alinhada inválida ou duplicada.")
        if relative.is_absolute() or ".." in relative.parts or len(relative.parts) != 1:
            raise PipelineError("Caminho de fase alinhada inseguro.")
        path = (root / relative.name).resolve()
        if not path.is_relative_to(root) or not path.is_file():
            raise PipelineError("Fase alinhada ausente ou fora do caso.")
        if _sha256(path) != item.get("sha256"):
            raise PipelineError("Hash de fase alinhada incompatível.")
        outputs[phase] = path
    if set(outputs) != {"art", "del"}:
        raise PipelineError("Cache de alinhamento não contém arterial e tardia.")
    return outputs


def _signature(
    *, case_id: str, config_hash: str, profile_hash: str,
    alignment_signature: str, venous_hash: str, mask_hash: str
) -> str:
    payload = {
        "candidate": CANDIDATE_VERSION,
        "case_id": case_id,
        "config_sha256": config_hash,
        "profile_sha256": profile_hash,
        "alignment_signature": alignment_signature,
        "venous_sha256": venous_hash,
        "liver_mask_sha256": mask_hash,
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _write_json(path: Path, payload: object) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _reuse_panel(case_dir: Path, signature: str) -> dict[str, Any]:
    manifest = _load_json(case_dir / "candidate_manifest.json")
    if manifest.get("candidate_signature") != signature:
        raise PipelineError("Painel candidato existe com assinatura incompatível.")
    panel = (case_dir / str(manifest.get("panel_filename", ""))).resolve()
    if not panel.is_relative_to(case_dir.resolve()) or not panel.is_file():
        raise PipelineError("Cache de painel aponta para caminho inseguro ou ausente.")
    if _sha256(panel) != manifest.get("panel_sha256"):
        raise PipelineError("Hash do painel candidato incompatível.")
    reused = dict(manifest)
    reused["cache_reused"] = True
    return reused


def render_aligned_multiphase_candidate(
    *, case_id: str, input_root: Path, alignment_root: Path, output_root: Path,
    config_path: Path, profile_path: Path, visible_phi_confirmed: bool = False
) -> dict[str, Any]:
    """Renderize um único painel RGB, preservando o gate visual antes da inferência."""
    input_root = Path(input_root).resolve()
    alignment_root = Path(alignment_root).resolve()
    output_root = Path(output_root).resolve()
    config_path = Path(config_path).resolve()
    profile_path = Path(profile_path).resolve()
    records = _load_input_records(input_root)
    if case_id not in records:
        raise PipelineError(f"case_id ausente no desenvolvimento: {case_id!r}.")
    input_files = _resolve_record_files(records[case_id], base=input_root, prefix="inputs")
    required = {"t1_venous", "liver_mask_venous"}
    if required - set(input_files):
        raise PipelineError("Caso sem fase ou máscara venosa.")

    aligned_dir = alignment_root / case_id
    if not aligned_dir.is_dir():
        raise PipelineError("Caso não possui cache de alinhamento aprovado.")
    alignment_manifest = _load_json(aligned_dir / "alignment_manifest.json")
    aligned = _aligned_outputs(aligned_dir, alignment_manifest)

    config = load_screening_config(config_path)
    if config.get("panel", {}).get("mode") != "multiphase_fusion":
        raise PipelineError("Candidato exige panel.mode=multiphase_fusion.")
    if config.get("panel", {}).get("strategy") != "uniform_9":
        raise PipelineError("Candidato rápido exige um único painel uniform_9.")
    med = config.get("medgemma", {})
    if int(med.get("timeout_seconds", 0)) > 120 or int(med.get("max_retries", 1)) != 0:
        raise PipelineError("Candidato rápido excede timeout/retries congelados.")

    signature = _signature(
        case_id=case_id,
        config_hash=_sha256(config_path),
        profile_hash=_sha256(profile_path),
        alignment_signature=str(alignment_manifest.get("cache_signature", "")),
        venous_hash=input_files["t1_venous"][1],
        mask_hash=input_files["liver_mask_venous"][1],
    )
    case_dir = output_root / case_id
    if case_dir.exists():
        return _reuse_panel(case_dir, signature)

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
        result = generate_liver_panel_multiphase(
            phase_paths={
                "art": aligned["art"],
                "pv": input_files["t1_venous"][0],
                "del": aligned["del"],
            },
            liver_mask_path=input_files["liver_mask_venous"][0],
            case_manifest_path=case_manifest,
            organ_profile=load_profile(profile_path),
            screening_config=config,
            output_dir=staging,
            model_trace=model_trace(config),
            visible_phi_confirmed=bool(visible_phi_confirmed),
        )
        panel_sha = _sha256(result.panel_path)
        candidate = {
            "schema": "argos-public-liver-mri-candidate-v1",
            "candidate_version": CANDIDATE_VERSION,
            "candidate_signature": signature,
            "case_id": case_id,
            "panel_filename": result.panel_path.name,
            "panel_sha256": panel_sha,
            "panel_bytes": result.panel_path.stat().st_size,
            "panel_manifest_filename": result.manifest_path.name,
            "config_sha256": _sha256(config_path),
            "alignment_signature": alignment_manifest.get("cache_signature"),
            "visible_phi_confirmed": bool(visible_phi_confirmed),
            "eligible_for_inference": bool(visible_phi_confirmed),
            "cache_reused": False,
            "research_only": True,
            "clinical_use_allowed": False,
            "requires_human_review": True,
        }
        _write_json(staging / "candidate_manifest.json", candidate)
        _publish_directory(staging, case_dir)
        return candidate
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise



