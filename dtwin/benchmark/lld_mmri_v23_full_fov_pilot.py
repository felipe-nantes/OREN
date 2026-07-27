"""Label-blind mask-independent full-FOV pilot for LLD-MMRI v23."""
from __future__ import annotations

import html
import json
import shutil
import uuid
from pathlib import Path
from typing import Any

from dtwin.benchmark.openswisshcc_alignment import _publish_directory, _sha256
from dtwin.benchmark.openswisshcc_v20_fusion import _canonical_sha
from dtwin.core import PipelineError
from dtwin.medgemma_client import load_screening_config, model_trace
from dtwin.medgemma_panel_full_fov import (
    FULL_FOV_MULTIPANEL_POLICY,
    FULL_FOV_POLICY,
    generate_full_fov_panel_multiphase,
    generate_full_fov_panel_set_multiphase,
)
from dtwin.medgemma_screening import _write_json_atomic


COHORT_SCHEMA = "argos-lld-mmri-v23-full-fov-pilot-cohort-v1"
GALLERY_SCHEMA = "argos-lld-mmri-v23-full-fov-pilot-gallery-v2"
ROLE_TO_PHASE = {"t1_arterial": "art", "t1_venous": "pv", "t1_delayed": "del"}


def _rows(prepared_root: Path) -> list[dict[str, Any]]:
    try:
        rows = [
            json.loads(line)
            for line in (prepared_root / "inputs.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    except (OSError, json.JSONDecodeError) as exc:
        raise PipelineError("Inputs LLD-MMRI ausentes no piloto full-FOV.") from exc
    if not rows:
        raise PipelineError("Piloto full-FOV sem casos preparados.")
    return rows


def _phase_paths(prepared_root: Path, row: dict[str, Any]) -> dict[str, Path]:
    if (
        row.get("ground_truth_read") is not False
        or row.get("lesion_mask_present") is not False
        or row.get("pathology_label_present") is not False
    ):
        raise PipelineError("Caso full-FOV perdeu isolamento de labels ou lesao.")
    case_id = str(row.get("case_id", ""))
    case_root = (prepared_root / "inputs" / case_id).resolve()
    if not case_root.is_relative_to(prepared_root):
        raise PipelineError("Caminho de caso full-FOV inseguro.")
    by_role = {str(item.get("role")): item for item in row.get("files", [])}
    result: dict[str, Path] = {}
    for role, phase in ROLE_TO_PHASE.items():
        item = by_role.get(role)
        if not isinstance(item, dict):
            raise PipelineError(f"Caso full-FOV sem {role}.")
        relative = Path(str(item.get("relative_path", "")))
        if relative.is_absolute() or ".." in relative.parts:
            raise PipelineError("Arquivo full-FOV inseguro.")
        path = (prepared_root / "inputs" / relative).resolve()
        if (
            not path.is_relative_to(prepared_root / "inputs")
            or not path.is_file()
            or path.stat().st_size != item.get("bytes")
            or _sha256(path) != item.get("sha256")
            or any(term in path.name.lower() for term in ("lesion", "label", "ground_truth", "mask"))
        ):
            raise PipelineError("Fase full-FOV ausente, adulterada ou proibida.")
        result[phase] = path
    return result


def build_full_fov_pilot(
    *,
    prepared_root: Path,
    output_root: Path,
    config_path: Path,
    case_ids: list[str],
) -> dict[str, Any]:
    prepared_root = Path(prepared_root).resolve()
    output_root = Path(output_root).resolve()
    config_path = Path(config_path).resolve()
    config = load_screening_config(config_path)
    if config.get("panel", {}).get("spatial_focus") != "full_fov_no_mask":
        raise PipelineError("Config do piloto nao e full-FOV sem mascara.")
    all_rows = _rows(prepared_root)
    by_id = {str(row.get("case_id")): row for row in all_rows}
    if not case_ids or len(set(case_ids)) != len(case_ids) or any(case_id not in by_id for case_id in case_ids):
        raise PipelineError("Selecao full-FOV invalida ou duplicada.")
    if output_root.exists():
        raise PipelineError("Piloto full-FOV existente; sobrescrita recusada.")
    staging = output_root.with_name(f"._{output_root.name}_{uuid.uuid4().hex[:8]}")
    staging.mkdir(parents=True)
    records = []
    requested_panel_count = int(config.get("panel", {}).get("panel_image_count", 1))
    if requested_panel_count not in {1, 3}:
        raise PipelineError("Piloto full-FOV permite somente 1 ou 3 paineis.")
    expected_policy = FULL_FOV_MULTIPANEL_POLICY if requested_panel_count == 3 else FULL_FOV_POLICY
    try:
        for number, case_id in enumerate(case_ids, start=1):
            row = by_id[case_id]
            case_dir = staging / case_id
            case_dir.mkdir()
            case_manifest = case_dir / "case_manifest.json"
            _write_json_atomic(
                case_manifest,
                {"case_id": case_id, "policy": "anonymize", "regulatory_state": "PESQUISA", "modality": "MRI"},
            )
            arguments = {
                "phase_paths": _phase_paths(prepared_root, row),
                "case_manifest_path": case_manifest,
                "screening_config": config,
                "output_dir": case_dir,
                "model_trace": model_trace(config),
                "visible_phi_confirmed": False,
            }
            result = (
                generate_full_fov_panel_set_multiphase(**arguments)
                if requested_panel_count == 3
                else generate_full_fov_panel_multiphase(**arguments)
            )
            manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
            if (
                manifest.get("spatial_policy") != expected_policy
                or manifest.get("organ_mask_used") is not False
                or manifest.get("lesion_mask_used") is not False
                or manifest.get("ground_truth_used") is not False
                or manifest.get("contour_rendered") is not False
                or manifest.get("crop_to_liver") is not False
            ):
                raise PipelineError("Painel full-FOV violou isolamento de mascara.")
            panel_paths = tuple(result.panel_paths) or (result.panel_path,)
            panel_records = [
                {
                    "panel_number": panel_number,
                    "panel": f"{case_id}/{panel_path.name}",
                    "panel_sha256": _sha256(panel_path),
                }
                for panel_number, panel_path in enumerate(panel_paths, start=1)
            ]
            records.append(
                {
                    "number": number,
                    "case_id": case_id,
                    # Legacy preview fields remain tied to the first panel.
                    "panel": panel_records[0]["panel"],
                    "panel_sha256": panel_records[0]["panel_sha256"],
                    "panel_image_count": len(panel_records),
                    "panels": panel_records,
                    "manifest": f"{case_id}/{result.manifest_path.name}",
                    "manifest_sha256": _sha256(result.manifest_path),
                }
            )
        base = {
            "schema": COHORT_SCHEMA,
            "status": "complete_pending_human_review",
            "case_count": len(records),
            "case_ids": case_ids,
            "selection": "protocol_first_n_plus_representative_failure_no_labels",
            "spatial_policy": expected_policy,
            "panel_image_count_per_case": requested_panel_count,
            "total_panel_image_count": len(records) * requested_panel_count,
            "config_sha256": _sha256(config_path),
            "cases": records,
            "organ_masks_read": 0,
            "lesion_masks_read": 0,
            "ground_truth_read": False,
            "eligible_for_inference": False,
            "research_only": True,
            "clinical_use_allowed": False,
        }
        cohort = dict(base)
        cohort["cohort_signature"] = _canonical_sha(base)
        _write_json_atomic(staging / "cohort_manifest.json", cohort)
        _publish_directory(staging, output_root)
        return cohort
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def build_full_fov_gallery(*, panel_root: Path, output_root: Path) -> dict[str, Any]:
    panel_root = Path(panel_root).resolve()
    output_root = Path(output_root).resolve()
    try:
        cohort = json.loads((panel_root / "cohort_manifest.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PipelineError("Coorte full-FOV invalida para galeria.") from exc
    unsigned = dict(cohort)
    signature = unsigned.pop("cohort_signature", None)
    if (
        cohort.get("schema") != COHORT_SCHEMA
        or signature != _canonical_sha(unsigned)
        or cohort.get("eligible_for_inference") is not False
        or cohort.get("organ_masks_read") != 0
        or cohort.get("lesion_masks_read") != 0
        or cohort.get("ground_truth_read") is not False
    ):
        raise PipelineError("Coorte full-FOV adulterada.")
    if output_root.exists():
        raise PipelineError("Galeria full-FOV existente; sobrescrita recusada.")
    staging = output_root.with_name(f"._{output_root.name}_{uuid.uuid4().hex[:8]}")
    images = staging / "images"
    images.mkdir(parents=True)
    items = []
    cards = []
    try:
        for record in cohort["cases"]:
            case_id = str(record["case_id"])
            manifest_path = (panel_root / record["manifest"]).resolve()
            if (
                not manifest_path.is_relative_to(panel_root)
                or _sha256(manifest_path) != record["manifest_sha256"]
            ):
                raise PipelineError("Hash full-FOV divergiu ao gerar galeria.")
            panels = record.get("panels") or [
                {"panel_number": 1, "panel": record["panel"], "panel_sha256": record["panel_sha256"]}
            ]
            card_images = []
            item_panels = []
            for panel in panels:
                panel_number = int(panel["panel_number"])
                source = (panel_root / panel["panel"]).resolve()
                if not source.is_relative_to(panel_root) or _sha256(source) != panel["panel_sha256"]:
                    raise PipelineError("Hash de painel full-FOV divergiu ao gerar galeria.")
                destination = images / f"{int(record['number']):03d}_{case_id}_p{panel_number:02d}.png"
                shutil.copyfile(source, destination)
                copied = {
                    "panel_number": panel_number,
                    "image": f"images/{destination.name}",
                    "sha256": _sha256(destination),
                }
                item_panels.append(copied)
                card_images.append(
                    f"<h3>Painel {panel_number}/{len(panels)}</h3>"
                    f"<img src='{html.escape(copied['image'])}' alt='{html.escape(case_id)} painel {panel_number}'>"
                )
            items.append({"case_id": case_id, "panel_count": len(item_panels), "panels": item_panels})
            cards.append(
                f"<section><h2>{int(record['number'])}. {html.escape(case_id)}</h2>"
                + "".join(card_images)
                + "</section>"
            )
        document = (
            "<!doctype html><meta charset='utf-8'><title>ARGOS LLD-MMRI full-FOV pilot</title>"
            "<style>body{background:#111827;color:#e5e7eb;font-family:sans-serif;margin:24px}"
            "section{margin:0 0 36px}img{display:block;max-width:100%;border:1px solid #374151}</style>"
            "<h1>LLD-MMRI v23 — piloto full-FOV sem máscara</h1>"
            "<p>Avaliar fígado completamente visível, ausência de crop/contorno e ausência de PHI.</p>"
            + "".join(cards)
        )
        (staging / "index.html").write_text(document, encoding="utf-8")
        base = {
            "schema": GALLERY_SCHEMA,
            "status": "pending_human_review",
            "cohort_signature": signature,
            "source_cohort_sha256": _sha256(panel_root / "cohort_manifest.json"),
            "index_sha256": _sha256(staging / "index.html"),
            "case_count": len(items),
            "total_panel_image_count": sum(item["panel_count"] for item in items),
            "items": items,
            "organ_masks_read": 0,
            "lesion_masks_read": 0,
            "ground_truth_read": False,
            "eligible_for_inference": False,
        }
        gallery = dict(base)
        gallery["gallery_signature"] = _canonical_sha(base)
        _write_json_atomic(staging / "gallery_manifest.json", gallery)
        _publish_directory(staging, output_root)
        return gallery
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise


__all__ = ["build_full_fov_gallery", "build_full_fov_pilot"]
