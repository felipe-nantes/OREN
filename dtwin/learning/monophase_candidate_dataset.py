"""Derive a label-blind single-phase MedSigLIP dataset from approved panels.

The approved hybrid-v1 panels encode arterial, portal/venous and delayed MRI
as RGB.  This module extracts one declared source channel (v1: green/portal-
venous) and replicates it across RGB.  Replication satisfies the image encoder's
RGB input contract without synthesizing phase differences.

Protected labels and lesion masks are neither accepted nor read.  The derived
dataset preserves the source protocol, split universe, technical failures and
per-image provenance hashes so the existing embedding and nested-OOF machinery
can verify it unchanged.
"""
from __future__ import annotations

import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any

import yaml
from PIL import Image, ImageChops

from dtwin.core import PipelineError
from dtwin.learning.candidate_dataset import (
    CANDIDATE_DATASET_SCHEMA,
    CANDIDATE_RECORD_SCHEMA,
    verify_candidate_dataset,
)
from dtwin.learning.protocol import canonical_sha256, sha256_file

CONFIG_SCHEMA = "oren-medsiglip-monophase-representation-config-v1"
DERIVATION_SCHEMA = "oren-medsiglip-monophase-derivation-v1"
CHANNEL_INDEX = {"red": 0, "green": 1, "blue": 2}


def _json(path: Path, description: str) -> dict[str, Any]:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PipelineError(f"{description} ausente ou inválido: {path}") from exc
    if not isinstance(value, dict):
        raise PipelineError(f"{description} deve ser objeto JSON.")
    return value


def _jsonl(path: Path, description: str) -> list[dict[str, Any]]:
    try:
        rows = [
            json.loads(line)
            for line in Path(path).read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    except (OSError, json.JSONDecodeError) as exc:
        raise PipelineError(f"{description} ausente ou inválido: {path}") from exc
    if any(not isinstance(row, dict) for row in rows):
        raise PipelineError(f"{description} contém registro inválido.")
    return rows


def _load_config(path: Path) -> dict[str, Any]:
    try:
        value = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise PipelineError(f"Config monofásica inválida: {path}") from exc
    if not isinstance(value, dict) or value.get("schema") != CONFIG_SCHEMA:
        raise PipelineError("Schema da representação monofásica inválido.")
    channel = str(value.get("source_rgb_channel") or "")
    if channel not in CHANNEL_INDEX:
        raise PipelineError("Canal RGB monofásico deve ser red, green ou blue.")
    phase = str(value.get("expected_source_phase_key") or "").strip()
    if not phase:
        raise PipelineError("Fase-fonte esperada não foi declarada.")
    if value.get("replicate_source_across_rgb") is not True:
        raise PipelineError("Representação monofásica deve replicar a fase real em RGB.")
    if value.get("dynamic_enhancement_information_present") is not False:
        raise PipelineError("Config monofásica não pode declarar dinâmica de contraste.")
    if value.get("ground_truth_allowed_during_derivation") is not False:
        raise PipelineError("Derivação monofásica deve permanecer label-blind.")
    return value


def _relative(root: Path, path: Path) -> str:
    try:
        return Path(path).resolve().relative_to(Path(root).resolve()).as_posix()
    except ValueError as exc:
        raise PipelineError(f"Artefato fora do workspace: {path}") from exc


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with Path(path).open("w", encoding="utf-8", newline="\n") as stream:
        for row in rows:
            stream.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def _source_channel_map(root: Path, record: dict[str, Any]) -> dict[str, str]:
    manifest_path = root / str(record.get("source_manifest_path") or "")
    manifest = _json(manifest_path, "Manifesto-fonte do painel")
    if sha256_file(manifest_path) != record.get("source_manifest_sha256"):
        raise PipelineError("Hash do manifesto-fonte divergiu.")
    channel_map = manifest.get("fusion_channel_map")
    if not isinstance(channel_map, dict):
        raise PipelineError("Painel-fonte não declara fusion_channel_map.")
    normalized = {str(key): str(value) for key, value in channel_map.items()}
    if any(channel not in CHANNEL_INDEX for channel in normalized):
        raise PipelineError("fusion_channel_map contains an unknown RGB channel.")
    return normalized


def _resolved_channel(
    *,
    channel_map: dict[str, str],
    configured_channel: str,
    expected_phase: str,
    resolve_by_manifest: bool,
) -> str | None:
    if channel_map.get(configured_channel) == expected_phase:
        return configured_channel
    if not resolve_by_manifest:
        received = channel_map.get(configured_channel, "")
        raise PipelineError(
            f"Canal {configured_channel} não representa {expected_phase!r}: recebido {received!r}."
        )
    matches = [channel for channel, phase in channel_map.items() if phase == expected_phase]
    if len(matches) > 1:
        raise PipelineError(f"Fase {expected_phase!r} aparece em multiplos canais RGB.")
    return matches[0] if matches else None


def derive_monophase_candidate_dataset(
    *,
    config_path: Path,
    source_candidate_root: Path,
    protocol_path: Path,
    splits_path: Path,
    workspace_root: Path,
    output_root: Path,
) -> dict[str, Any]:
    """Materialize immutable grayscale panels without opening protected labels."""

    root = Path(workspace_root).resolve()
    source = Path(source_candidate_root).resolve()
    destination = Path(output_root).resolve()
    if destination.exists():
        raise PipelineError("Dataset monofásico já existe; saída é imutável.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    config = _load_config(Path(config_path))
    source_manifest = verify_candidate_dataset(
        protocol_path=protocol_path,
        splits_path=splits_path,
        workspace_root=root,
        output_root=source,
    )
    source_records_path = source / "candidate_records.jsonl"
    source_failures_path = source / "technical_failures.jsonl"
    source_records = _jsonl(source_records_path, "Candidatos-fonte")
    failure_rows = _jsonl(source_failures_path, "Falhas técnicas-fonte")
    channel = str(config["source_rgb_channel"])
    expected_phase = str(config["expected_source_phase_key"])
    resolve_by_manifest = config.get("resolve_source_phase_by_manifest") is True
    missing_phase_policy = str(config.get("missing_expected_phase_policy") or "abort")
    if missing_phase_policy not in {"abort", "technical_failure"}:
        raise PipelineError("missing_expected_phase_policy deve ser abort ou technical_failure.")

    staging = Path(tempfile.mkdtemp(prefix=f".{destination.name}.", dir=destination.parent))
    try:
        derived_rows: list[dict[str, Any]] = []
        manifest_cache: dict[str, dict[str, str]] = {}
        resolved_channels: dict[tuple[str, int], str | None] = {}
        missing_phase_cases: set[str] = set()
        for record in source_records:
            manifest_key = str(record.get("source_manifest_path") or "")
            channel_map = manifest_cache.get(manifest_key)
            if channel_map is None:
                channel_map = _source_channel_map(root, record)
                manifest_cache[manifest_key] = channel_map
            actual_channel = _resolved_channel(
                channel_map=channel_map,
                configured_channel=channel,
                expected_phase=expected_phase,
                resolve_by_manifest=resolve_by_manifest,
            )
            key = (str(record["case_id"]), int(record["panel_number"]))
            resolved_channels[key] = actual_channel
            if actual_channel is None:
                missing_phase_cases.add(str(record["case_id"]))

        if missing_phase_cases and missing_phase_policy == "abort":
            examples = ", ".join(sorted(missing_phase_cases)[:3])
            raise PipelineError(
                f"Fase {expected_phase!r} ausente em {len(missing_phase_cases)} caso(s): {examples}."
            )
        existing_failure_ids = {str(row.get("case_id")) for row in failure_rows}
        if missing_phase_cases & existing_failure_ids:
            raise PipelineError("Caso sem fase ja consta como falha tecnica-fonte.")
        failure_rows.extend(
            {
                "schema": "argos-hybrid-label-blind-technical-failure-v1",
                "case_id": case_id,
                "failure_reason": f"expected_source_phase_unavailable:{expected_phase}",
                "counts_as_error": True,
                "research_only": True,
            }
            for case_id in sorted(missing_phase_cases)
        )
        for record in source_records:
            case_id = str(record["case_id"])
            if case_id in missing_phase_cases:
                continue
            source_image = root / str(record.get("image_path") or "")
            if sha256_file(source_image) != record.get("image_sha256"):
                raise PipelineError(f"Imagem-fonte alterada: {record.get('image_path')}")
            panel_number = int(record["panel_number"])
            actual_channel = resolved_channels[(case_id, panel_number)]
            if actual_channel is None:
                raise PipelineError("Resolucao interna de fase monofasica inconsistente.")
            channel_index = CHANNEL_INDEX[actual_channel]
            relative_image = Path("panels") / case_id / (
                f"monophase_panel_{panel_number:03d}_of_{int(record['panel_total']):03d}.png"
            )
            staged_image = staging / relative_image
            staged_image.parent.mkdir(parents=True, exist_ok=True)
            with Image.open(source_image) as opened:
                rgb = opened.convert("RGB")
                selected = rgb.getchannel(channel_index)
                mono = Image.merge("RGB", (selected, selected, selected))
                mono.save(staged_image, format="PNG", optimize=True)
            with Image.open(staged_image) as exported:
                if exported.info:
                    raise PipelineError("PNG monofásico contém metadados inesperados.")
                r, g, b = exported.convert("RGB").split()
                if ImageChops.difference(r, g).getbbox() or ImageChops.difference(g, b).getbbox():
                    raise PipelineError("Painel monofásico não é grayscale RGB exato.")

            final_image = destination / relative_image
            derived_rows.append(
                {
                    **record,
                    "schema": CANDIDATE_RECORD_SCHEMA,
                    "candidate_kind": "global_liver_panel_monophase",
                    "phase": str(config["output_phase_name"]),
                    "image_path": _relative(root, final_image),
                    "image_sha256": sha256_file(staged_image),
                    "source_image_path": str(record["image_path"]),
                    "source_image_sha256": str(record["image_sha256"]),
                    "source_rgb_channel": actual_channel,
                    "configured_source_rgb_channel": channel,
                    "source_phase_key": expected_phase,
                    "single_phase_replicated_across_rgb": True,
                    "dynamic_enhancement_information_present": False,
                    "ground_truth_used": False,
                    "lesion_mask_used": False,
                    "research_only": True,
                    "clinical_use_allowed": False,
                }
            )

        derived_rows.sort(key=lambda row: (row["case_id"], row["panel_number"]))
        records_path = staging / "candidate_records.jsonl"
        failures_path = staging / "technical_failures.jsonl"
        _write_jsonl(records_path, derived_rows)
        _write_jsonl(failures_path, failure_rows)
        body = {
            "schema": CANDIDATE_DATASET_SCHEMA,
            "derivation_schema": DERIVATION_SCHEMA,
            "status": "complete_label_blind_pending_independent_verification",
            "protocol_signature": source_manifest["protocol_signature"],
            "splits_sha256": source_manifest["splits_sha256"],
            "config_sha256": sha256_file(config_path),
            "source_dataset_signature": source_manifest["dataset_signature"],
            "source_candidate_records_sha256": sha256_file(source_records_path),
            "source_rgb_channel": channel,
            "source_phase_key": expected_phase,
            "representation": str(config["output_phase_name"]),
            "single_phase_replicated_across_rgb": True,
            "dynamic_enhancement_information_present": False,
            "expected_case_count": int(source_manifest["expected_case_count"]),
            "materialized_case_count": (
                int(source_manifest["materialized_case_count"]) - len(missing_phase_cases)
            ),
            "technical_failure_count": len(failure_rows),
            "missing_expected_phase_case_count": len(missing_phase_cases),
            "candidate_record_count": len(derived_rows),
            "candidate_records_sha256": sha256_file(records_path),
            "technical_failures_sha256": sha256_file(failures_path),
            "ground_truth_read": False,
            "lesion_masks_read": 0,
            "lesion_contours_rendered": False,
            "research_only": True,
            "clinical_use_allowed": False,
        }
        manifest = {**body, "dataset_signature": canonical_sha256(body)}
        (staging / "dataset_manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        os.replace(staging, destination)
    finally:
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)
    return manifest


__all__ = [
    "CONFIG_SCHEMA",
    "DERIVATION_SCHEMA",
    "derive_monophase_candidate_dataset",
]
