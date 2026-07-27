"""Volumetric OpenSwissHCC candidates derived from the reviewed v3 cohort.

The module only reads neutral image inputs, automatic liver masks, approved
alignment outputs and the source candidate metadata. It never reads labels or
lesion annotations. Every rendered panel is hashed and the axial coverage gate
must pass before a candidate can be published.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import uuid
from pathlib import Path, PurePosixPath
from typing import Any, Mapping

from dtwin.benchmark.openswisshcc_alignment import (
    _load_input_records,
    _load_json,
    _publish_directory,
    _resolve_record_files,
    _sha256,
)
from dtwin.benchmark.openswisshcc_candidate import _aligned_outputs
from dtwin.benchmark.openswisshcc_review import _candidate as validate_source_candidate
from dtwin.core import PipelineError, load_profile
from dtwin.medgemma_client import load_screening_config, model_trace
from dtwin.medgemma_panel import generate_liver_panel
from dtwin.medgemma_panel_multiphase import generate_liver_panel_multiphase


VOLUMETRIC_CANDIDATE_VERSION = "openswisshcc-volumetric-choice-pathology-v1"
_ALLOWED_KINDS = {"multiphase_rgb", "venous_single_phase_fallback"}


def _canonical_sha256(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _safe_case(source_root: Path, case_id: str) -> tuple[Path, dict[str, Any]]:
    validate_source_candidate(source_root, case_id)
    root = Path(source_root).resolve()
    case_dir = (root / case_id).resolve()
    manifest = _load_json(case_dir / "candidate_manifest.json")
    kind = str(manifest.get("candidate_kind", "multiphase_rgb"))
    if kind not in _ALLOWED_KINDS:
        raise PipelineError(f"Tipo de candidato fonte nao autorizado: {kind!r}.")
    if manifest.get("case_id") != case_id:
        raise PipelineError("Manifesto fonte pertence a outro caso.")
    if manifest.get("research_only") is not True or manifest.get("clinical_use_allowed") is not False:
        raise PipelineError("Candidato fonte perdeu as salvaguardas de pesquisa.")
    return case_dir, manifest


def _validate_config(path: Path, *, kind: str) -> dict[str, Any]:
    config = load_screening_config(path)
    panel = config.get("panel", {})
    expected_mode = "multiphase_fusion" if kind == "multiphase_rgb" else "single_grayscale"
    if panel.get("mode", "single_grayscale") != expected_mode:
        raise PipelineError("Config volumetrica nao corresponde ao tipo do candidato.")
    if panel.get("strategy") != "volumetric_blocks":
        raise PipelineError("Config deve usar panel.strategy=volumetric_blocks.")
    if int(panel.get("axial_tiles_per_panel", 9)) != 9:
        raise PipelineError("Candidato volumetrico exige ate nove cortes axiais por painel.")
    med = config.get("medgemma", {})
    if med.get("response_mode") != "choice_classification":
        raise PipelineError("Config volumetrica exige choice_classification auditavel.")
    if int(med.get("timeout_seconds", 0)) > 120 or int(med.get("max_retries", 1)) != 0:
        raise PipelineError("Config volumetrica excede timeout/retries congelados.")
    if config.get("rag", {}).get("enabled") is not False:
        raise PipelineError("Candidato volumetrico de calibracao nao permite RAG.")
    return config


def _panel_collection(staging: Path, result: Any) -> tuple[list[dict[str, Any]], str, dict[str, Any]]:
    manifest = _load_json(result.manifest_path)
    if manifest.get("panel_strategy") != "volumetric_blocks":
        raise PipelineError("Manifesto renderizado nao e volumetrico.")
    if manifest.get("lesion_pre_marked") is not False:
        raise PipelineError("Manifesto volumetrico viola lesion_pre_marked=false.")
    coverage = manifest.get("coverage")
    if not isinstance(coverage, dict) or coverage.get("gate_passed") is not True:
        raise PipelineError("Gate de cobertura volumetrica nao passou.")
    total = coverage.get("total_liver_voxels")
    covered = coverage.get("covered_liver_voxels")
    if not isinstance(total, int) or total <= 0 or covered != total:
        raise PipelineError("Cobertura volumetrica nao representa exatamente todos os voxels.")
    if coverage.get("missing_axial_indices") or coverage.get("duplicate_axial_indices"):
        raise PipelineError("Cobertura volumetrica possui indices ausentes ou duplicados.")

    raw_records = manifest.get("panels")
    if not isinstance(raw_records, list) or not raw_records:
        raise PipelineError("Manifesto volumetrico nao contem paineis.")
    records: list[dict[str, Any]] = []
    seen: set[str] = set()
    for expected_number, item in enumerate(raw_records, start=1):
        relative = PurePosixPath(str(item.get("image", "")))
        if relative.is_absolute() or ".." in relative.parts or len(relative.parts) != 1:
            raise PipelineError("Painel volumetrico aponta para caminho inseguro.")
        if relative.name in seen:
            raise PipelineError("Painel volumetrico duplicado.")
        seen.add(relative.name)
        path = (staging / relative.name).resolve()
        if not path.is_relative_to(staging.resolve()) or not path.is_file():
            raise PipelineError("Painel volumetrico ausente.")
        digest = _sha256(path)
        if digest != item.get("sha256"):
            raise PipelineError("Hash de painel volumetrico divergente.")
        if int(item.get("panel_number", expected_number)) != expected_number:
            raise PipelineError("Ordem dos paineis volumetricos e invalida.")
        records.append(
            {
                "panel_number": expected_number,
                "panel_total": len(raw_records),
                "image": relative.name,
                "sha256": digest,
                "bytes": path.stat().st_size,
                "axial_interval": item.get("axial_interval"),
            }
        )
    if len(tuple(result.panel_paths)) != len(records):
        raise PipelineError("PanelResult e manifesto divergem na quantidade de paineis.")
    return records, _canonical_sha256(records), manifest


def _signature(
    *, case_id: str, kind: str, source_signature: str, config_hash: str,
    profile_hash: str, input_hashes: Mapping[str, str], alignment_signature: str | None,
) -> str:
    return _canonical_sha256(
        {
            "candidate_version": VOLUMETRIC_CANDIDATE_VERSION,
            "case_id": case_id,
            "candidate_kind": kind,
            "source_candidate_signature": source_signature,
            "config_sha256": config_hash,
            "profile_sha256": profile_hash,
            "input_hashes": dict(sorted(input_hashes.items())),
            "alignment_signature": alignment_signature,
        }
    )


def _reuse(case_dir: Path, signature: str) -> dict[str, Any]:
    manifest = _load_json(case_dir / "candidate_manifest.json")
    if manifest.get("candidate_signature") != signature:
        raise PipelineError("Candidato volumetrico existe com assinatura incompatível.")
    records = manifest.get("panels")
    if not isinstance(records, list) or not records:
        raise PipelineError("Cache volumetrico nao contem a colecao autoritativa.")
    for item in records:
        relative = PurePosixPath(str(item.get("image", "")))
        path = (case_dir / relative.name).resolve()
        if (
            relative.is_absolute() or ".." in relative.parts or len(relative.parts) != 1
            or not path.is_relative_to(case_dir.resolve()) or not path.is_file()
            or _sha256(path) != item.get("sha256") or path.stat().st_size != item.get("bytes")
        ):
            raise PipelineError("Cache volumetrico possui painel ausente ou divergente.")
    if _canonical_sha256(records) != manifest.get("panel_set_sha256"):
        raise PipelineError("Hash da colecao volumetrica e incompatível.")
    reused = dict(manifest)
    reused["cache_reused"] = True
    return reused


def render_volumetric_candidate(
    *, case_id: str, input_root: Path, alignment_root: Path, source_panel_root: Path,
    output_root: Path, multiphase_config: Path, fallback_config: Path,
    high_contrast_fallback_config: Path, source_high_contrast_config: Path,
    profile_path: Path,
) -> dict[str, Any]:
    """Render one complete candidate while preserving the reviewed v3 source."""
    input_root = Path(input_root).resolve()
    alignment_root = Path(alignment_root).resolve()
    source_panel_root = Path(source_panel_root).resolve()
    output_root = Path(output_root).resolve()
    profile_path = Path(profile_path).resolve()
    _, source = _safe_case(source_panel_root, case_id)
    kind = str(source.get("candidate_kind", "multiphase_rgb"))
    records = _load_input_records(input_root)
    if case_id not in records:
        raise PipelineError(f"case_id ausente no desenvolvimento: {case_id!r}.")
    inputs = _resolve_record_files(records[case_id], base=input_root, prefix="inputs")
    required = {"t1_venous", "liver_mask_venous"}
    if required - set(inputs):
        raise PipelineError("Caso sem fase ou mascara venosa.")

    alignment_signature: str | None = None
    aligned: dict[str, Path] = {}
    if kind == "multiphase_rgb":
        aligned_dir = alignment_root / case_id
        if not aligned_dir.is_dir():
            raise PipelineError("Caso multifasico sem cache de alinhamento aprovado.")
        alignment_manifest = _load_json(aligned_dir / "alignment_manifest.json")
        aligned = _aligned_outputs(aligned_dir, alignment_manifest)
        alignment_signature = str(alignment_manifest.get("cache_signature", ""))
        config_path = Path(multiphase_config).resolve()
        input_hashes = {
            "art": _sha256(aligned["art"]),
            "pv": inputs["t1_venous"][1],
            "del": _sha256(aligned["del"]),
            "liver_mask": inputs["liver_mask_venous"][1],
        }
    else:
        high_contrast = source.get("config_sha256") == _sha256(
            Path(source_high_contrast_config).resolve()
        )
        config_path = Path(
            high_contrast_fallback_config if high_contrast else fallback_config
        ).resolve()
        input_hashes = {
            "pv": inputs["t1_venous"][1],
            "liver_mask": inputs["liver_mask_venous"][1],
        }
    config = _validate_config(config_path, kind=kind)
    signature = _signature(
        case_id=case_id,
        kind=kind,
        source_signature=str(source.get("candidate_signature", "")),
        config_hash=_sha256(config_path),
        profile_hash=_sha256(profile_path),
        input_hashes=input_hashes,
        alignment_signature=alignment_signature,
    )
    case_dir = output_root / case_id
    if case_dir.exists():
        return _reuse(case_dir, signature)

    output_root.mkdir(parents=True, exist_ok=True)
    staging = output_root / f"._vol_{uuid.uuid4().hex[:8]}"
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
        if kind == "multiphase_rgb":
            result = generate_liver_panel_multiphase(
                phase_paths={"art": aligned["art"], "pv": inputs["t1_venous"][0], "del": aligned["del"]},
                liver_mask_path=inputs["liver_mask_venous"][0],
                case_manifest_path=case_manifest,
                organ_profile=load_profile(profile_path),
                screening_config=config,
                output_dir=staging,
                model_trace=model_trace(config),
                visible_phi_confirmed=False,
            )
        else:
            result = generate_liver_panel(
                volume_path=inputs["t1_venous"][0],
                liver_mask_path=inputs["liver_mask_venous"][0],
                case_manifest_path=case_manifest,
                organ_profile=load_profile(profile_path),
                screening_config=config,
                output_dir=staging,
                model_trace=model_trace(config),
                visible_phi_confirmed=False,
            )
        panels, panel_set_sha256, panel_manifest = _panel_collection(staging, result)
        candidate = {
            "schema": "argos-public-liver-mri-volumetric-candidate-v1",
            "candidate_version": VOLUMETRIC_CANDIDATE_VERSION,
            "candidate_kind": kind,
            "candidate_signature": signature,
            "source_candidate_signature": source.get("candidate_signature"),
            "source_candidate_version": source.get("candidate_version"),
            "case_id": case_id,
            "panel_strategy": "volumetric_blocks",
            "panel_filename": panels[0]["image"],
            "panel_sha256": panels[0]["sha256"],
            "panel_bytes": panels[0]["bytes"],
            "panel_manifest_filename": result.manifest_path.name,
            "panel_image_count": len(panels),
            "panels": panels,
            "panel_set_sha256": panel_set_sha256,
            "coverage": panel_manifest["coverage"],
            "config_sha256": _sha256(config_path),
            "source_config_sha256": source.get("config_sha256"),
            "alignment_signature": alignment_signature,
            "visible_phi_confirmed": False,
            "eligible_for_inference": False,
            "cache_reused": False,
            "research_only": True,
            "clinical_use_allowed": False,
            "requires_human_review": True,
            "ground_truth_read": False,
        }
        if kind == "venous_single_phase_fallback":
            candidate["fallback_reason"] = source.get("fallback_reason")
            candidate["source_phase"] = "t1_venous"
        _write_json(staging / "candidate_manifest.json", candidate)
        _publish_directory(staging, case_dir)
        return candidate
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise

