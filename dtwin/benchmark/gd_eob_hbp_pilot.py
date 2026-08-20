"""Deterministic label-blind HBP compatibility pilot for frozen ARGOS v23."""
from __future__ import annotations

import hashlib
import html
import json
import shutil
import time
import uuid
from collections.abc import Callable
from pathlib import Path, PurePosixPath
from typing import Any

import numpy as np
import SimpleITK as sitk
from PIL import Image

from dtwin.benchmark.gd_eob_hcc_external import (
    DATASET_ID,
    IMAGE_CASE_SCHEMA,
    _jsonl,
    _sha256,
    verify_label_blind_readiness,
)
from dtwin.benchmark.lld_mmri_v23_preparation import (
    _load_jsonl_checkpoint,
    _write_jsonl_checkpoint_atomic,
    isolated_total_mr_liver_segmenter,
)
from dtwin.benchmark.openswisshcc_alignment import _publish_directory
from dtwin.benchmark.openswisshcc_v20_fusion import _canonical_sha
from dtwin.core import PipelineError
from dtwin.medgemma_client import load_screening_config, model_trace
from dtwin.medgemma_panel import PANEL_MANIFEST_FILENAME
from dtwin.medgemma_panel_liver_enriched import (
    LIVER_ENRICHED_POLICY,
    generate_liver_enriched_panel_set_multiphase,
)
from dtwin.medgemma_screening import _write_json_atomic

PROTOCOL_SCHEMA = "argos-gd-eob-hbp-label-blind-pilot-protocol-v1"
RUN_SCHEMA = "argos-gd-eob-hbp-label-blind-pilot-run-v1"
CASE_SCHEMA = "argos-gd-eob-hbp-label-blind-pilot-case-v1"
GALLERY_SCHEMA = "argos-gd-eob-hbp-label-blind-pilot-gallery-v1"
PILOT_CASES_PER_CENTER = 3
PILOT_CASE_COUNT = 9
SELECTION_SEED = "argos-gd-eob-hbp-technical-pilot-v1"


def _load_json(path: Path, description: str) -> dict[str, Any]:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PipelineError(f"{description} ausente ou inválido.") from exc
    if not isinstance(value, dict):
        raise PipelineError(f"{description} deve ser objeto JSON.")
    return value


def _image_rows(image_root: Path) -> list[dict[str, Any]]:
    rows = _jsonl(image_root / "image_cases.jsonl", "Casos image-only Gd-EOB")
    if any(
        row.get("schema") != IMAGE_CASE_SCHEMA
        or row.get("ground_truth_read") is not False
        or row.get("lesion_masks_read") is not False
        or row.get("anatomical_annotations_used") is not False
        for row in rows
    ):
        raise PipelineError("Casos Gd-EOB perderam isolamento label-blind.")
    return rows


def select_pilot_cases(rows: list[dict[str, Any]]) -> list[str]:
    """Select three cases per center using case IDs only, never image contents."""

    selected: list[str] = []
    for center in ("center-1", "center-2", "center-3"):
        candidates = [
            str(row["case_id"])
            for row in rows
            if row.get("center_pseudonym") == center
        ]
        ranked = sorted(
            candidates,
            key=lambda case_id: hashlib.sha256(
                f"{SELECTION_SEED}:{case_id}".encode("utf-8")
            ).hexdigest(),
        )
        if len(ranked) < PILOT_CASES_PER_CENTER:
            raise PipelineError(f"Centro insuficiente para piloto HBP: {center}.")
        selected.extend(ranked[:PILOT_CASES_PER_CENTER])
    if len(selected) != PILOT_CASE_COUNT or len(set(selected)) != PILOT_CASE_COUNT:
        raise PipelineError("Seleção determinística do piloto HBP divergiu.")
    return selected


def _static_signal_compatibility(workspace_root: Path) -> dict[str, Any]:
    root = Path(workspace_root).resolve()
    requirements = {
        "medgemma_v4_uncertainty_margin": {
            "input_available": True,
            "frozen_semantics_preserved": False,
            "reason": "frozen reader used a different multiphase representation",
        },
        "medsiglip_v5_inverse_sagittal": {
            "input_available": True,
            "frozen_semantics_preserved": False,
            "reason": "HBP-only sagittal pixels are outside the frozen panel domain",
        },
        "localizer_v10_log_volume": {
            "input_available": True,
            "frozen_semantics_preserved": False,
            "reason": "HBP is not the frozen venous localizer input",
        },
        "candidate_weighted_linearity": {
            "input_available": False,
            "frozen_semantics_preserved": False,
            "reason": (
                "deterministic enhancement candidate requires native, arterial, "
                "venous and delayed phases"
            ),
        },
    }
    evidence_files = (
        "dtwin/benchmark/openswisshcc_v11_fusion.py",
        "dtwin/benchmark/openswisshcc_candidate_shape.py",
        "dtwin/benchmark/openswisshcc_enhancement_maps.py",
        "dtwin/benchmark/lld_mmri_v23_shape.py",
    )
    evidence = {}
    for relative in evidence_files:
        path = (root / relative).resolve()
        if not path.is_file() or not path.is_relative_to(root):
            raise PipelineError("Implementação necessária à auditoria v23 está ausente.")
        evidence[relative] = _sha256(path)
    return {
        "required_signals": requirements,
        "exact_v23_raw_signals_available": False,
        "exact_v23_score_computable": False,
        "direct_external_validation_of_frozen_v23_allowed": False,
        "reason": "HBP-only cannot reproduce the frozen dynamic-enhancement shape signal",
        "implementation_evidence_sha256": evidence,
    }


def freeze_hbp_pilot_protocol(
    *,
    readiness_path: Path,
    image_root: Path,
    contract_path: Path,
    baseline_lock_path: Path,
    workspace_root: Path,
    config_path: Path,
    output_path: Path,
) -> dict[str, Any]:
    readiness = verify_label_blind_readiness(
        readiness_path=readiness_path,
        image_root=image_root,
        contract_path=contract_path,
        baseline_lock_path=baseline_lock_path,
        workspace_root=workspace_root,
    )
    rows = _image_rows(Path(image_root).resolve())
    case_ids = select_pilot_cases(rows)
    config = load_screening_config(Path(config_path).resolve())
    channel_map = config.get("panel", {}).get("fusion", {}).get("channel_map")
    if (
        config.get("panel", {}).get("spatial_focus") != "liver_enriched_full_fov"
        or channel_map != {"red": "hbp", "green": "hbp", "blue": "hbp"}
        or config.get("rag", {}).get("enabled") is not False
    ):
        raise PipelineError("Config HBP do piloto não representa grayscale single-phase.")
    base = {
        "schema": PROTOCOL_SCHEMA,
        "status": "frozen_before_automatic_segmentation_or_model_inference",
        "dataset_id": DATASET_ID,
        "readiness_signature": readiness["readiness_signature"],
        "collection_signature": readiness["collection_signature"],
        "contract_signature": readiness["contract_signature"],
        "selection_seed": SELECTION_SEED,
        "selection_uses_labels": False,
        "selection_uses_image_content": False,
        "cases_per_center": PILOT_CASES_PER_CENTER,
        "case_count": len(case_ids),
        "case_ids": case_ids,
        "config_sha256": _sha256(Path(config_path).resolve()),
        "segmentation": {
            "engine": "TotalSegmentator",
            "task": "total_mr",
            "roi_subset": ["liver"],
            "fast": True,
            "device": "gpu",
            "timeout_seconds": 90,
            "public_anatomical_masks_allowed": False,
        },
        "panel": {
            "spatial_policy": LIVER_ENRICHED_POLICY,
            "source_phase": "hbp",
            "rgb_channels": {"red": "hbp", "green": "hbp", "blue": "hbp"},
            "synthetic_phase_differences_created": False,
            "organ_mask_rendered": False,
            "crop_to_liver": False,
        },
        "signal_compatibility_predeclared": _static_signal_compatibility(
            workspace_root
        ),
        "model_inference_authorized": False,
        "labels_read": False,
        "lesion_masks_read": False,
        "research_only": True,
        "clinical_use_allowed": False,
    }
    protocol = {**base, "protocol_signature": _canonical_sha(base)}
    destination = Path(output_path).resolve()
    if destination.exists():
        existing = _load_json(destination, "Protocolo piloto HBP existente")
        if existing != protocol:
            raise PipelineError("Protocolo piloto HBP existente diverge.")
        return existing
    destination.parent.mkdir(parents=True, exist_ok=True)
    _write_json_atomic(destination, protocol)
    return protocol


def verify_hbp_pilot_protocol(
    *,
    protocol_path: Path,
    readiness_path: Path,
    image_root: Path,
    contract_path: Path,
    baseline_lock_path: Path,
    workspace_root: Path,
    config_path: Path,
) -> tuple[dict[str, Any], dict[str, dict[str, Any]], dict[str, Any]]:
    readiness = verify_label_blind_readiness(
        readiness_path=readiness_path,
        image_root=image_root,
        contract_path=contract_path,
        baseline_lock_path=baseline_lock_path,
        workspace_root=workspace_root,
    )
    protocol = _load_json(protocol_path, "Protocolo piloto HBP")
    signature = protocol.get("protocol_signature")
    unsigned = dict(protocol)
    unsigned.pop("protocol_signature", None)
    rows = _image_rows(Path(image_root).resolve())
    indexed = {str(row["case_id"]): row for row in rows}
    config = load_screening_config(Path(config_path).resolve())
    if (
        protocol.get("schema") != PROTOCOL_SCHEMA
        or protocol.get("status")
        != "frozen_before_automatic_segmentation_or_model_inference"
        or signature != _canonical_sha(unsigned)
        or protocol.get("readiness_signature") != readiness["readiness_signature"]
        or protocol.get("case_ids") != select_pilot_cases(rows)
        or protocol.get("config_sha256") != _sha256(Path(config_path).resolve())
        or protocol.get("model_inference_authorized") is not False
        or protocol.get("labels_read") is not False
        or protocol.get("lesion_masks_read") is not False
        or protocol.get("signal_compatibility_predeclared")
        != _static_signal_compatibility(workspace_root)
    ):
        raise PipelineError("Protocolo piloto HBP adulterado ou inseguro.")
    return protocol, indexed, config


def _safe_image(image_root: Path, row: dict[str, Any]) -> Path:
    relative = PurePosixPath(str(row.get("image", {}).get("relative_path", "")))
    path = (image_root / Path(*relative.parts)).resolve()
    if (
        relative.is_absolute()
        or ".." in relative.parts
        or not path.is_relative_to(image_root)
        or not path.is_file()
        or path.stat().st_size != row.get("image", {}).get("bytes")
        or _sha256(path) != row.get("image", {}).get("sha256")
    ):
        raise PipelineError("Imagem HBP do piloto ausente ou adulterada.")
    return path


def _validate_mask(source: Path, mask_path: Path) -> int:
    try:
        source_image = sitk.ReadImage(str(source))
        mask_image = sitk.ReadImage(str(mask_path))
        mask = sitk.GetArrayFromImage(mask_image) > 0
    except RuntimeError as exc:
        raise PipelineError("Máscara automática HBP inválida.") from exc
    if (
        source_image.GetSize() != mask_image.GetSize()
        or not np.allclose(source_image.GetSpacing(), mask_image.GetSpacing(), atol=1e-5)
        or not np.allclose(source_image.GetOrigin(), mask_image.GetOrigin(), atol=1e-4)
        or not np.allclose(source_image.GetDirection(), mask_image.GetDirection(), atol=1e-6)
        or int(mask.sum()) < 100
    ):
        raise PipelineError("Máscara automática HBP vazia ou fora da grade.")
    return int(mask.sum())


def _validate_case_record(root: Path, record: dict[str, Any]) -> None:
    if record.get("status") == "technical_failure":
        return
    case_dir = root / str(record.get("case_id", ""))
    manifest = case_dir / PANEL_MANIFEST_FILENAME
    mask = case_dir / "automatic_liver_mask.nii.gz"
    panels = record.get("panels")
    if (
        record.get("status") != "complete_label_blind_panel"
        or not manifest.is_file()
        or _sha256(manifest) != record.get("panel_manifest_sha256")
        or not mask.is_file()
        or _sha256(mask) != record.get("automatic_liver_mask_sha256")
        or not isinstance(panels, list)
        or len(panels) not in {2, 3}
    ):
        raise PipelineError("Checkpoint do piloto HBP possui caso inválido.")
    for panel in panels:
        path = case_dir / str(panel.get("name", ""))
        if not path.is_file() or _sha256(path) != panel.get("sha256"):
            raise PipelineError("Painel do piloto HBP ausente ou adulterado.")


def run_hbp_pilot(
    *,
    protocol_path: Path,
    readiness_path: Path,
    image_root: Path,
    contract_path: Path,
    baseline_lock_path: Path,
    workspace_root: Path,
    config_path: Path,
    output_root: Path,
    progress: Callable[[int, int, str], None] | None = None,
) -> dict[str, Any]:
    protocol, indexed, config = verify_hbp_pilot_protocol(
        protocol_path=protocol_path,
        readiness_path=readiness_path,
        image_root=image_root,
        contract_path=contract_path,
        baseline_lock_path=baseline_lock_path,
        workspace_root=workspace_root,
        config_path=config_path,
    )
    image_root = Path(image_root).resolve()
    output = Path(output_root).resolve()
    if output.exists():
        raise PipelineError("Piloto HBP já publicado; sobrescrita recusada.")
    staging = output.with_name(f".{output.name}.incomplete")
    checkpoint = staging / "checkpoint_cases.jsonl"
    context = {
        "protocol_signature": protocol["protocol_signature"],
        "case_ids": protocol["case_ids"],
        "labels_read": False,
        "lesion_masks_read": False,
    }
    context["checkpoint_signature"] = _canonical_sha(context)
    if staging.exists():
        persisted = _load_json(staging / "checkpoint_context.json", "Contexto piloto HBP")
        records = _load_jsonl_checkpoint(checkpoint)
        if persisted != context or [row["case_id"] for row in records] != protocol[
            "case_ids"
        ][: len(records)]:
            raise PipelineError("Checkpoint piloto HBP pertence a outro protocolo.")
        for record in records:
            _validate_case_record(staging, record)
    else:
        staging.mkdir(parents=True)
        _write_json_atomic(staging / "checkpoint_context.json", context)
        records = []
        _write_jsonl_checkpoint_atomic(checkpoint, records)
    for index, case_id in enumerate(
        protocol["case_ids"][len(records) :], start=len(records) + 1
    ):
        if progress:
            progress(index, PILOT_CASE_COUNT, case_id)
        row = indexed[case_id]
        source = _safe_image(image_root, row)
        case_dir = staging / case_id
        shutil.rmtree(case_dir, ignore_errors=True)
        case_dir.mkdir()
        started = time.perf_counter()
        try:
            mask_path = case_dir / "automatic_liver_mask.nii.gz"
            segmentation_started = time.perf_counter()
            receipt = isolated_total_mr_liver_segmenter(
                source,
                mask_path,
                device="gpu",
                fast=True,
                timeout_seconds=90,
            )
            segmentation_seconds = time.perf_counter() - segmentation_started
            mask_voxels = _validate_mask(source, mask_path)
            _write_json_atomic(
                case_dir / "case_manifest.json",
                {
                    "case_id": case_id,
                    "policy": "anonymize",
                    "regulatory_state": "PESQUISA",
                    "modality": "MRI",
                },
            )
            panel_started = time.perf_counter()
            result = generate_liver_enriched_panel_set_multiphase(
                phase_paths={"hbp": source},
                coarse_liver_mask_path=mask_path,
                case_manifest_path=case_dir / "case_manifest.json",
                screening_config=config,
                output_dir=case_dir,
                model_trace=model_trace(config),
                visible_phi_confirmed=False,
            )
            panel_seconds = time.perf_counter() - panel_started
            manifest = _load_json(result.manifest_path, "Manifesto painel HBP")
            if (
                manifest.get("input_type")
                != "mri_single_phase_replicated_grayscale_full_fov_liver_enriched"
                or manifest.get("single_phase_replicated_across_rgb") is not True
                or manifest.get("dynamic_enhancement_information_present") is not False
                or manifest.get("fusion_channel_map")
                != {"red": "hbp", "green": "hbp", "blue": "hbp"}
                or manifest.get("lesion_mask_used") is not False
                or manifest.get("ground_truth_used") is not False
                or manifest.get("organ_mask_rendered") is not False
                or manifest.get("crop_to_liver") is not False
            ):
                raise PipelineError("Painel HBP violou a representação congelada.")
            record = {
                "schema": CASE_SCHEMA,
                "case_id": case_id,
                "center_pseudonym": row["center_pseudonym"],
                "status": "complete_label_blind_panel",
                "source_image_sha256": row["image"]["sha256"],
                "automatic_liver_mask_voxels": mask_voxels,
                "automatic_liver_mask_sha256": _sha256(mask_path),
                "segmentation_receipt": receipt,
                "panel_count": result.panel_count,
                "panels": [
                    {"name": path.name, "sha256": _sha256(path)}
                    for path in result.panel_paths
                ],
                "panel_manifest_sha256": _sha256(result.manifest_path),
                "timing_seconds": {
                    "segmentation": segmentation_seconds,
                    "panel_generation": panel_seconds,
                    "technical_total": time.perf_counter() - started,
                },
                "model_inference_executed": False,
                "labels_read": False,
                "lesion_masks_read": False,
                "public_anatomical_masks_used": False,
            }
        except Exception as exc:
            record = {
                "schema": CASE_SCHEMA,
                "case_id": case_id,
                "center_pseudonym": row["center_pseudonym"],
                "status": "technical_failure",
                "error_type": type(exc).__name__,
                "error": str(exc)[:1000],
                "timing_seconds": {
                    "technical_total": time.perf_counter() - started
                },
                "model_inference_executed": False,
                "labels_read": False,
                "lesion_masks_read": False,
                "public_anatomical_masks_used": False,
            }
        records.append(record)
        _write_jsonl_checkpoint_atomic(checkpoint, records)
    failures = [row for row in records if row["status"] == "technical_failure"]
    successes = [row for row in records if row["status"] == "complete_label_blind_panel"]
    technical_times = [
        float(row["timing_seconds"]["technical_total"]) for row in records
    ]
    compatibility = protocol["signal_compatibility_predeclared"]
    base = {
        "schema": RUN_SCHEMA,
        "status": "complete_hbp_technical_pilot_direct_v23_incompatible",
        "protocol_signature": protocol["protocol_signature"],
        "case_count": len(records),
        "successful_case_count": len(successes),
        "technical_failure_count": len(failures),
        "case_ids": protocol["case_ids"],
        "cases": records,
        "panel_count": sum(int(row.get("panel_count", 0)) for row in successes),
        "maximum_technical_seconds": max(technical_times),
        "all_technical_steps_within_180_seconds": all(
            value <= 180.0 for value in technical_times
        ),
        "timing_scope_includes_model_inference": False,
        "signal_compatibility": compatibility,
        "direct_frozen_v23_validation_decision": "REJECTED_INCOMPATIBLE_INPUT_DOMAIN",
        "full_220_case_inference_authorized": False,
        "labels_read": False,
        "lesion_masks_read": False,
        "model_inference_executed": False,
        "research_only": True,
        "clinical_use_allowed": False,
        "requires_human_review": True,
    }
    summary = {**base, "run_signature": _canonical_sha(base)}
    _write_json_atomic(staging / "summary.json", summary)
    (staging / "checkpoint_context.json").unlink(missing_ok=True)
    checkpoint.unlink(missing_ok=True)
    (staging / "checkpoint_cases.backup.jsonl").unlink(missing_ok=True)
    _publish_directory(staging, output)
    return verify_hbp_pilot_run(
        run_root=output,
        protocol_path=protocol_path,
        readiness_path=readiness_path,
        image_root=image_root,
        contract_path=contract_path,
        baseline_lock_path=baseline_lock_path,
        workspace_root=workspace_root,
        config_path=config_path,
    )


def verify_hbp_pilot_run(
    *,
    run_root: Path,
    protocol_path: Path,
    readiness_path: Path,
    image_root: Path,
    contract_path: Path,
    baseline_lock_path: Path,
    workspace_root: Path,
    config_path: Path,
) -> dict[str, Any]:
    protocol, _, _ = verify_hbp_pilot_protocol(
        protocol_path=protocol_path,
        readiness_path=readiness_path,
        image_root=image_root,
        contract_path=contract_path,
        baseline_lock_path=baseline_lock_path,
        workspace_root=workspace_root,
        config_path=config_path,
    )
    root = Path(run_root).resolve()
    summary = _load_json(root / "summary.json", "Resumo piloto HBP")
    signature = summary.get("run_signature")
    unsigned = dict(summary)
    unsigned.pop("run_signature", None)
    records = summary.get("cases")
    if (
        summary.get("schema") != RUN_SCHEMA
        or summary.get("status")
        != "complete_hbp_technical_pilot_direct_v23_incompatible"
        or signature != _canonical_sha(unsigned)
        or summary.get("protocol_signature") != protocol["protocol_signature"]
        or summary.get("case_ids") != protocol["case_ids"]
        or not isinstance(records, list)
        or len(records) != PILOT_CASE_COUNT
        or summary.get("full_220_case_inference_authorized") is not False
        or summary.get("labels_read") is not False
        or summary.get("lesion_masks_read") is not False
        or summary.get("model_inference_executed") is not False
        or summary.get("signal_compatibility", {}).get("exact_v23_score_computable")
        is not False
    ):
        raise PipelineError("Execução do piloto HBP adulterada ou insegura.")
    for record in records:
        _validate_case_record(root, record)
    return summary


def build_hbp_pilot_gallery(*, run_root: Path, output_root: Path) -> dict[str, Any]:
    run_root = Path(run_root).resolve()
    output = Path(output_root).resolve()
    summary = _load_json(run_root / "summary.json", "Resumo piloto HBP")
    signature = summary.get("run_signature")
    unsigned = dict(summary)
    unsigned.pop("run_signature", None)
    if signature != _canonical_sha(unsigned) or summary.get("labels_read") is not False:
        raise PipelineError("Resumo piloto HBP inválido para galeria.")
    if output.exists():
        raise PipelineError("Galeria piloto HBP já existe.")
    staging = output.with_name(f".{output.name}.incomplete-{uuid.uuid4().hex}")
    images = staging / "images"
    images.mkdir(parents=True)
    cards: list[str] = []
    items: list[dict[str, Any]] = []
    for number, record in enumerate(summary["cases"], start=1):
        case_id = record["case_id"]
        if record["status"] == "technical_failure":
            cards.append(
                f"<section><h2>{number}. {html.escape(case_id)}</h2>"
                f"<p>Falha técnica: {html.escape(record['error'])}</p></section>"
            )
            items.append({"case_id": case_id, "status": "technical_failure"})
            continue
        panel_items = []
        tags = []
        for panel_number, panel in enumerate(record["panels"], start=1):
            source = run_root / case_id / panel["name"]
            destination = images / f"{number:02d}_{case_id}_p{panel_number}.png"
            shutil.copyfile(source, destination)
            with Image.open(destination) as image:
                image.load()
                if image.mode != "RGB" or image.info:
                    raise PipelineError("PNG HBP inválido para galeria.")
            panel_items.append(
                {
                    "panel_number": panel_number,
                    "relative_path": f"images/{destination.name}",
                    "sha256": _sha256(destination),
                }
            )
            tags.append(
                f"<h3>Painel {panel_number}/{record['panel_count']}</h3>"
                f"<img src='images/{html.escape(destination.name)}'>"
            )
        cards.append(
            f"<section><h2>{number}. {html.escape(case_id)}</h2>"
            f"<p>{html.escape(record['center_pseudonym'])}; HBP single-phase grayscale; "
            "máscara automática não renderizada.</p>"
            + "".join(tags)
            + "</section>"
        )
        items.append(
            {"case_id": case_id, "status": record["status"], "panels": panel_items}
        )
    document = (
        "<!doctype html><meta charset='utf-8'><title>ARGOS Gd-EOB HBP pilot</title>"
        "<style>body{background:#111827;color:#e5e7eb;font-family:sans-serif;margin:24px}"
        "section{margin-bottom:48px}img{display:block;max-width:100%;border:1px solid #374151}"
        "</style><h1>Gd-EOB HBP — piloto técnico label-blind</h1>"
        "<p>Avaliar presença e cobertura visual do fígado, ausência de crop excessivo, "
        "contorno, PHI ou artefato grave. Não avaliar diagnóstico.</p>"
        + "".join(cards)
    )
    index = staging / "index.html"
    index.write_text(document, encoding="utf-8")
    base = {
        "schema": GALLERY_SCHEMA,
        "status": "pending_human_technical_review",
        "run_signature": signature,
        "case_count": len(items),
        "items": items,
        "index_sha256": _sha256(index),
        "labels_read": False,
        "lesion_masks_read": False,
        "diagnostic_review_requested": False,
    }
    gallery = {**base, "gallery_signature": _canonical_sha(base)}
    _write_json_atomic(staging / "gallery.json", gallery)
    _publish_directory(staging, output)
    return gallery


__all__ = [
    "PILOT_CASE_COUNT",
    "PILOT_CASES_PER_CENTER",
    "build_hbp_pilot_gallery",
    "freeze_hbp_pilot_protocol",
    "run_hbp_pilot",
    "select_pilot_cases",
    "verify_hbp_pilot_protocol",
    "verify_hbp_pilot_run",
]
