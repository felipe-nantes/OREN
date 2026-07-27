"""Label-blind LLD-MMRI v23 liver-enriched 2/3-panel visual pilot."""
from __future__ import annotations

import html
import json
import shutil
import time
import uuid
from pathlib import Path
from typing import Any

from PIL import Image

from dtwin.benchmark.lld_mmri_v23_full_fov_pilot import _phase_paths, _rows
from dtwin.benchmark.lld_mmri_v23_preparation import (
    _load_jsonl_checkpoint,
    _write_jsonl_checkpoint_atomic,
)
from dtwin.benchmark.openswisshcc_alignment import _publish_directory, _sha256
from dtwin.benchmark.openswisshcc_v20_fusion import _canonical_sha
from dtwin.core import PipelineError
from dtwin.medgemma_client import load_screening_config, model_trace
from dtwin.medgemma_panel_liver_enriched import (
    LIVER_ENRICHED_POLICY,
    generate_liver_enriched_panel_set_multiphase,
)
from dtwin.medgemma_screening import _write_json_atomic


COHORT_SCHEMA = "argos-lld-mmri-v23-liver-enriched-pilot-cohort-v1"
GALLERY_SCHEMA = "argos-lld-mmri-v23-liver-enriched-pilot-gallery-v1"
FULL_VERIFICATION_SCHEMA = "argos-lld-mmri-v23-liver-enriched-full-verification-v1"
FULL_PROTOCOL_CASE_COUNT = 335
FULL_ELIGIBLE_CASE_COUNT = 321
FULL_TECHNICAL_FAILURE_COUNT = 14


def _render_case(
    *, prepared_root: Path, row: dict[str, Any], case_dir: Path,
    config: dict[str, Any], number: int,
) -> dict[str, Any]:
    case_id = str(row["case_id"])
    case_manifest = case_dir / "case_manifest.json"
    _write_json_atomic(case_manifest, {
        "case_id": case_id, "policy": "anonymize",
        "regulatory_state": "PESQUISA", "modality": "MRI",
    })
    mask_path = _mask_path(prepared_root, row)
    result = generate_liver_enriched_panel_set_multiphase(
        phase_paths=_phase_paths(prepared_root, row),
        coarse_liver_mask_path=mask_path,
        case_manifest_path=case_manifest,
        screening_config=config,
        output_dir=case_dir,
        model_trace=model_trace(config),
        visible_phi_confirmed=False,
    )
    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    if (
        manifest.get("spatial_policy") != LIVER_ENRICHED_POLICY
        or manifest.get("organ_mask_use_scope")
        != "coarse_axial_localization_only_not_rendered_not_cropped"
        or manifest.get("organ_mask_rendered") is not False
        or manifest.get("lesion_mask_used") is not False
        or manifest.get("ground_truth_used") is not False
        or manifest.get("crop_to_liver") is not False
        or manifest.get("contour_rendered") is not False
        or result.panel_count not in {2, 3}
    ):
        raise PipelineError("Painel liver-enriched violou o contrato tecnico.")
    panels = [
        {
            "panel_number": index,
            "panel": f"{case_id}/{path.name}",
            "panel_sha256": _sha256(path),
        }
        for index, path in enumerate(result.panel_paths, start=1)
    ]
    return {
        "number": number,
        "case_id": case_id,
        "selection_mode": manifest["localization"]["selection_mode"],
        "localizer_stable": manifest["localization"]["localizer_stable"],
        "panel_image_count": result.panel_count,
        "panels": panels,
        "manifest": f"{case_id}/{result.manifest_path.name}",
        "manifest_sha256": _sha256(result.manifest_path),
    }


def _validate_checkpoint_record(root: Path, record: dict[str, Any]) -> None:
    case_id = str(record.get("case_id", ""))
    manifest = (root / str(record.get("manifest", ""))).resolve()
    panels = record.get("panels")
    expected_count = 3 if record.get("localizer_stable") is True else 2
    if (
        not manifest.is_relative_to(root)
        or not manifest.is_file()
        or _sha256(manifest) != record.get("manifest_sha256")
        or record.get("panel_image_count") != expected_count
        or not isinstance(panels, list)
        or len(panels) != expected_count
    ):
        raise PipelineError("Checkpoint liver-enriched possui manifesto invalido.")
    for number, panel in enumerate(panels, start=1):
        path = (root / str(panel.get("panel", ""))).resolve()
        if (
            panel.get("panel_number") != number
            or not path.is_relative_to(root)
            or not path.is_file()
            or _sha256(path) != panel.get("panel_sha256")
        ):
            raise PipelineError("Checkpoint liver-enriched possui painel invalido.")


def _mask_path(prepared_root: Path, row: dict[str, Any]) -> Path:
    if (
        row.get("ground_truth_read") is not False
        or row.get("lesion_mask_present") is not False
        or row.get("pathology_label_present") is not False
    ):
        raise PipelineError("Caso liver-enriched perdeu isolamento de labels ou lesao.")
    matches = [item for item in row.get("files", []) if item.get("role") == "liver_mask_venous"]
    if len(matches) != 1:
        raise PipelineError("Caso liver-enriched sem localizador hepatico unico.")
    item = matches[0]
    relative = Path(str(item.get("relative_path", "")))
    path = (prepared_root / "inputs" / relative).resolve()
    if (
        relative.is_absolute()
        or ".." in relative.parts
        or not path.is_relative_to(prepared_root / "inputs")
        or not path.is_file()
        or path.stat().st_size != item.get("bytes")
        or _sha256(path) != item.get("sha256")
        or any(term in path.name.lower() for term in ("lesion", "label", "ground_truth"))
    ):
        raise PipelineError("Localizador hepatico ausente, adulterado ou proibido.")
    return path


def build_liver_enriched_pilot(
    *, prepared_root: Path, output_root: Path, config_path: Path, case_ids: list[str],
) -> dict[str, Any]:
    prepared_root = Path(prepared_root).resolve()
    output_root = Path(output_root).resolve()
    config_path = Path(config_path).resolve()
    config = load_screening_config(config_path)
    if config.get("panel", {}).get("spatial_focus") != "liver_enriched_full_fov":
        raise PipelineError("Config do piloto nao e liver-enriched full-FOV.")
    rows = _rows(prepared_root)
    by_id = {str(row.get("case_id")): row for row in rows}
    if not case_ids or len(case_ids) != len(set(case_ids)) or any(case_id not in by_id for case_id in case_ids):
        raise PipelineError("Selecao liver-enriched invalida ou duplicada.")
    if output_root.exists():
        raise PipelineError("Piloto liver-enriched existente; sobrescrita recusada.")
    summary = json.loads((prepared_root / "summary.json").read_text(encoding="utf-8"))
    if (
        summary.get("ground_truth_read") is not False
        and summary.get("labels_read") is not False
    ) or summary.get("lesion_masks_read") != 0:
        raise PipelineError("Preparacao liver-enriched nao esta label-blind.")
    staging = output_root.with_name(f"._{output_root.name}_{uuid.uuid4().hex[:8]}")
    staging.mkdir(parents=True)
    records: list[dict[str, Any]] = []
    try:
        for number, case_id in enumerate(case_ids, start=1):
            row = by_id[case_id]
            case_dir = staging / case_id
            case_dir.mkdir()
            records.append(_render_case(
                prepared_root=prepared_root, row=row, case_dir=case_dir,
                config=config, number=number,
            ))
        base = {
            "schema": COHORT_SCHEMA,
            "status": "complete_pending_human_review",
            "case_count": len(records),
            "case_ids": case_ids,
            "selection": "previous_full_fov_pilot10_plus_all_weak_localizer_cases",
            "spatial_policy": LIVER_ENRICHED_POLICY,
            "config_sha256": _sha256(config_path),
            "source_preparation_signature": summary.get("preparation_signature"),
            "source_inputs_sha256": summary.get("inputs_sha256"),
            "stable_localizer_case_count": sum(item["localizer_stable"] is True for item in records),
            "weak_localizer_fallback_case_count": sum(item["localizer_stable"] is False for item in records),
            "total_panel_image_count": sum(item["panel_image_count"] for item in records),
            "cases": records,
            "organ_masks_read_for_localization_only": len(records),
            "organ_masks_rendered": 0,
            "lesion_masks_read": 0,
            "ground_truth_read": False,
            "eligible_for_inference": False,
            "research_only": True,
            "clinical_use_allowed": False,
        }
        cohort = {**base, "cohort_signature": _canonical_sha(base)}
        _write_json_atomic(staging / "cohort_manifest.json", cohort)
        _publish_directory(staging, output_root)
        return cohort
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def build_liver_enriched_full_cohort(
    *, prepared_root: Path, output_root: Path, config_path: Path,
) -> dict[str, Any]:
    """Render all 321 eligible cases with durable, validated checkpoints."""
    prepared_root = Path(prepared_root).resolve()
    output_root = Path(output_root).resolve()
    config_path = Path(config_path).resolve()
    config = load_screening_config(config_path)
    if config.get("panel", {}).get("spatial_focus") != "liver_enriched_full_fov":
        raise PipelineError("Config da coorte completa nao e liver-enriched full-FOV.")
    rows = _rows(prepared_root)
    summary = json.loads((prepared_root / "summary.json").read_text(encoding="utf-8"))
    summary_unsigned = dict(summary)
    preparation_signature = summary_unsigned.pop("preparation_signature", None)
    case_ids = [str(row.get("case_id")) for row in rows]
    technical_failure_ids = list(summary.get("technical_failure_case_ids", []))
    inputs_path = prepared_root / "inputs.jsonl"
    if (
        preparation_signature != _canonical_sha(summary_unsigned)
        or summary.get("status") != "complete_label_blind_inputs_with_automatic_liver_masks"
        or summary.get("case_count") != 321
        or summary.get("protocol_case_count") != 335
        or summary.get("technical_failure_case_count") != 14
        or len(technical_failure_ids) != 14
        or summary.get("case_ids") != case_ids
        or summary.get("inputs_sha256") != _sha256(inputs_path)
        or (
            summary.get("ground_truth_read") is not False
            and summary.get("labels_read") is not False
        )
        or summary.get("lesion_masks_read") != 0
        or len(case_ids) != len(set(case_ids))
        or set(case_ids) & set(technical_failure_ids)
    ):
        raise PipelineError("Preparacao completa liver-enriched invalida ou nao cega.")
    if output_root.exists():
        raise PipelineError("Coorte completa liver-enriched existente; sobrescrita recusada.")
    output_root.parent.mkdir(parents=True, exist_ok=True)
    staging = output_root.with_name(f".{output_root.name}.incomplete")
    context = {
        "schema": "argos-lld-mmri-v23-liver-enriched-full-checkpoint-v1",
        "preparation_signature": preparation_signature,
        "inputs_sha256": summary["inputs_sha256"],
        "config_sha256": _sha256(config_path),
        "protocol_case_count": 335,
        "case_ids": case_ids,
        "technical_failure_case_ids": technical_failure_ids,
        "spatial_policy": LIVER_ENRICHED_POLICY,
        "ground_truth_read": False,
        "lesion_masks_read": 0,
    }
    context["checkpoint_signature"] = _canonical_sha(context)
    checkpoint_path = staging / "checkpoint_cases.jsonl"
    if staging.exists():
        persisted = json.loads((staging / "checkpoint_context.json").read_text(encoding="utf-8"))
        records = _load_jsonl_checkpoint(checkpoint_path)
        if persisted != context:
            raise PipelineError("Checkpoint liver-enriched pertence a outro protocolo.")
        if [row.get("case_id") for row in records] != case_ids[:len(records)]:
            raise PipelineError("Ordem do checkpoint liver-enriched foi adulterada.")
        for record in records:
            _validate_checkpoint_record(staging, record)
    else:
        staging.mkdir()
        _write_json_atomic(staging / "checkpoint_context.json", context)
        records = []
        _write_jsonl_checkpoint_atomic(checkpoint_path, records)
    current_case_id: str | None = None
    try:
        for number, row in enumerate(rows[len(records):], start=len(records) + 1):
            current_case_id = str(row["case_id"])
            case_started = time.perf_counter()
            case_dir = staging / current_case_id
            if case_dir.exists():
                shutil.rmtree(case_dir)
            case_dir.mkdir()
            record = _render_case(
                prepared_root=prepared_root, row=row, case_dir=case_dir,
                config=config, number=number,
            )
            record["elapsed_seconds"] = time.perf_counter() - case_started
            records.append(record)
            _write_jsonl_checkpoint_atomic(checkpoint_path, records)
        base = {
            "schema": COHORT_SCHEMA,
            "status": "complete_pending_human_review",
            "protocol_case_count": 335,
            "case_count": len(records),
            "case_ids": case_ids,
            "technical_failure_case_count": len(technical_failure_ids),
            "technical_failure_case_ids": technical_failure_ids,
            "technical_failures_excluded_from_inference": True,
            "technical_failures_count_as_primary_metric_errors": True,
            "selection": "all_321_inference_eligible_cases_in_frozen_protocol_order",
            "spatial_policy": LIVER_ENRICHED_POLICY,
            "config_sha256": _sha256(config_path),
            "source_preparation_signature": preparation_signature,
            "source_inputs_sha256": summary["inputs_sha256"],
            "stable_localizer_case_count": sum(item["localizer_stable"] is True for item in records),
            "weak_localizer_fallback_case_count": sum(item["localizer_stable"] is False for item in records),
            "total_panel_image_count": sum(int(item["panel_image_count"]) for item in records),
            "cases": records,
            "organ_masks_read_for_localization_only": len(records),
            "organ_masks_rendered": 0,
            "lesion_masks_read": 0,
            "ground_truth_read": False,
            "eligible_for_inference": False,
            "research_only": True,
            "clinical_use_allowed": False,
        }
        cohort = {**base, "cohort_signature": _canonical_sha(base)}
        _write_json_atomic(staging / "cohort_manifest.json", cohort)
        (staging / "checkpoint_context.json").unlink(missing_ok=True)
        checkpoint_path.unlink(missing_ok=True)
        (staging / "checkpoint_cases.backup.jsonl").unlink(missing_ok=True)
        (staging / "failure.json").unlink(missing_ok=True)
        _publish_directory(staging, output_root)
        return cohort
    except Exception as exc:
        _write_json_atomic(staging / "failure.json", {
            "schema": "argos-lld-mmri-v23-liver-enriched-full-failure-v1",
            "case_id": current_case_id,
            "completed_case_count": len(records),
            "error_type": type(exc).__name__,
            "error": str(exc)[:1000],
            "ground_truth_read": False,
            "lesion_masks_read": 0,
            "resumable_after_root_cause_review": True,
        })
        raise


def build_liver_enriched_gallery(*, panel_root: Path, output_root: Path) -> dict[str, Any]:
    panel_root = Path(panel_root).resolve()
    output_root = Path(output_root).resolve()
    cohort = json.loads((panel_root / "cohort_manifest.json").read_text(encoding="utf-8"))
    unsigned = dict(cohort)
    signature = unsigned.pop("cohort_signature", None)
    if (
        cohort.get("schema") != COHORT_SCHEMA
        or signature != _canonical_sha(unsigned)
        or cohort.get("eligible_for_inference") is not False
        or cohort.get("lesion_masks_read") != 0
        or cohort.get("ground_truth_read") is not False
    ):
        raise PipelineError("Coorte liver-enriched adulterada.")
    if output_root.exists():
        raise PipelineError("Galeria liver-enriched existente; sobrescrita recusada.")
    staging = output_root.with_name(f"._{output_root.name}_{uuid.uuid4().hex[:8]}")
    images = staging / "images"
    images.mkdir(parents=True)
    items: list[dict[str, Any]] = []
    cards: list[str] = []
    try:
        for record in cohort["cases"]:
            case_id = str(record["case_id"])
            manifest = (panel_root / record["manifest"]).resolve()
            if not manifest.is_relative_to(panel_root) or _sha256(manifest) != record["manifest_sha256"]:
                raise PipelineError("Manifesto liver-enriched divergiu na galeria.")
            copied_panels = []
            card_images = []
            for panel in record["panels"]:
                source = (panel_root / panel["panel"]).resolve()
                if not source.is_relative_to(panel_root) or _sha256(source) != panel["panel_sha256"]:
                    raise PipelineError("Painel liver-enriched divergiu na galeria.")
                panel_number = int(panel["panel_number"])
                destination = images / f"{int(record['number']):03d}_{case_id}_p{panel_number:02d}.png"
                shutil.copyfile(source, destination)
                copied = {
                    "panel_number": panel_number,
                    "image": f"images/{destination.name}",
                    "sha256": _sha256(destination),
                }
                copied_panels.append(copied)
                card_images.append(
                    f"<h3>Painel {panel_number}/{record['panel_image_count']}</h3>"
                    f"<img src='{html.escape(copied['image'])}' alt='{html.escape(case_id)} painel {panel_number}'>"
                )
            items.append({
                "case_id": case_id,
                "selection_mode": record["selection_mode"],
                "localizer_stable": record["localizer_stable"],
                "panel_count": record["panel_image_count"],
                "panels": copied_panels,
            })
            cards.append(
                f"<section><h2>{int(record['number'])}. {html.escape(case_id)}</h2>"
                f"<p>Modo: {html.escape(record['selection_mode'])}</p>"
                + "".join(card_images) + "</section>"
            )
        document = (
            "<!doctype html><meta charset='utf-8'><title>ARGOS LLD-MMRI liver-enriched v3</title>"
            "<style>body{background:#111827;color:#e5e7eb;font-family:sans-serif;margin:24px}"
            "section{margin:0 0 48px}img{display:block;max-width:100%;border:1px solid #374151}"
            "h3{margin-top:24px}</style>"
            "<h1>LLD-MMRI v23 — piloto v3 liver-enriched</h1>"
            "<p>Avaliar se todos os painéis mostram fígado suficiente, sem crop, contorno ou PHI. "
            "Casos fallback possuem dois painéis; os demais possuem três painéis intercalados.</p>"
            + "".join(cards)
        )
        index_path = staging / "index.html"
        index_path.write_text(document, encoding="utf-8")
        base = {
            "schema": GALLERY_SCHEMA,
            "status": "pending_human_review",
            "cohort_signature": signature,
            "source_cohort_sha256": _sha256(panel_root / "cohort_manifest.json"),
            "index_sha256": _sha256(index_path),
            "case_count": len(items),
            "total_panel_image_count": sum(item["panel_count"] for item in items),
            "items": items,
            "organ_masks_rendered": 0,
            "lesion_masks_read": 0,
            "ground_truth_read": False,
            "eligible_for_inference": False,
        }
        gallery = {**base, "gallery_signature": _canonical_sha(base)}
        _write_json_atomic(staging / "gallery_manifest.json", gallery)
        _publish_directory(staging, output_root)
        return gallery
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def verify_liver_enriched_full_cohort(
    *, panel_root: Path, prepared_root: Path, config_path: Path,
) -> dict[str, Any]:
    """Independently verify every manifest and panel in the full blind cohort."""

    panel_root = Path(panel_root).resolve()
    prepared_root = Path(prepared_root).resolve()
    config_path = Path(config_path).resolve()
    cohort_path = panel_root / "cohort_manifest.json"
    summary_path = prepared_root / "summary.json"
    inputs_path = prepared_root / "inputs.jsonl"
    cohort = json.loads(cohort_path.read_text(encoding="utf-8"))
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    cohort_unsigned = dict(cohort)
    cohort_signature = cohort_unsigned.pop("cohort_signature", None)
    summary_unsigned = dict(summary)
    preparation_signature = summary_unsigned.pop("preparation_signature", None)
    rows = _rows(prepared_root)
    case_ids = [str(row.get("case_id")) for row in rows]
    failures = list(summary.get("technical_failure_case_ids", []))
    records = cohort.get("cases")
    if (
        cohort.get("schema") != COHORT_SCHEMA
        or cohort_signature != _canonical_sha(cohort_unsigned)
        or preparation_signature != _canonical_sha(summary_unsigned)
        or not isinstance(records, list)
        or cohort.get("status") != "complete_pending_human_review"
        or cohort.get("protocol_case_count") != FULL_PROTOCOL_CASE_COUNT
        or cohort.get("case_count") != FULL_ELIGIBLE_CASE_COUNT
        or cohort.get("technical_failure_case_count") != FULL_TECHNICAL_FAILURE_COUNT
        or len(records) != FULL_ELIGIBLE_CASE_COUNT
        or len(case_ids) != FULL_ELIGIBLE_CASE_COUNT
        or len(failures) != FULL_TECHNICAL_FAILURE_COUNT
        or len(set(case_ids)) != len(case_ids)
        or len(set(failures)) != len(failures)
        or set(case_ids) & set(failures)
        or cohort.get("case_ids") != case_ids
        or [record.get("case_id") for record in records] != case_ids
        or cohort.get("source_preparation_signature") != preparation_signature
        or cohort.get("source_inputs_sha256") != _sha256(inputs_path)
        or summary.get("inputs_sha256") != _sha256(inputs_path)
        or cohort.get("config_sha256") != _sha256(config_path)
        or cohort.get("spatial_policy") != LIVER_ENRICHED_POLICY
        or cohort.get("organ_masks_read_for_localization_only") != len(records)
        or cohort.get("organ_masks_rendered") != 0
        or cohort.get("lesion_masks_read") != 0
        or cohort.get("ground_truth_read") is not False
        or cohort.get("eligible_for_inference") is not False
        or cohort.get("research_only") is not True
        or cohort.get("clinical_use_allowed") is not False
    ):
        raise PipelineError("Coorte completa liver-enriched falhou na verificacao independente.")

    stable = 0
    weak = 0
    total_panels = 0
    dimensions: set[tuple[int, int]] = set()
    for number, (row, record) in enumerate(zip(rows, records, strict=True), start=1):
        if record.get("number") != number or record.get("case_id") != row.get("case_id"):
            raise PipelineError("Ordem de casos liver-enriched divergiu.")
        _validate_checkpoint_record(panel_root, record)
        manifest_path = (panel_root / record["manifest"]).resolve()
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        localizer_stable = record.get("localizer_stable") is True
        expected_panels = 3 if localizer_stable else 2
        expected_slices = expected_panels * 9
        selection_mode = (
            "stable_coarse_localizer_interleaved_3x9"
            if localizer_stable
            else "weak_localizer_mask_independent_cranial_75pct_interleaved_2x9"
        )
        manifest_panels = manifest.get("panels")
        localization = manifest.get("localization", {})
        views = manifest.get("views", {})
        if (
            manifest.get("case_id") != record["case_id"]
            or manifest.get("spatial_policy") != LIVER_ENRICHED_POLICY
            or manifest.get("organ_mask_use_scope")
            != "coarse_axial_localization_only_not_rendered_not_cropped"
            or manifest.get("organ_mask_rendered") is not False
            or manifest.get("lesion_mask_used") is not False
            or manifest.get("ground_truth_used") is not False
            or manifest.get("crop_to_liver") is not False
            or manifest.get("contour_rendered") is not False
            or manifest.get("phi_metadata_removed") is not True
            or manifest.get("visible_phi_review_required") is not True
            or manifest.get("requires_human_review") is not True
            or manifest.get("panel_image_count") != expected_panels
            or not isinstance(manifest_panels, list)
            or len(manifest_panels) != expected_panels
            or record.get("selection_mode") != selection_mode
            or localization.get("selection_mode") != selection_mode
            or localization.get("localizer_stable") is not localizer_stable
            or localization.get("selected_distinct_axial_count") != expected_slices
            or views.get("total_distinct_axial_indices") != expected_slices
        ):
            raise PipelineError("Contrato interno de painel liver-enriched invalido.")
        per_panel_indices: list[list[int]] = []
        for panel_number, (record_panel, manifest_panel) in enumerate(
            zip(record["panels"], manifest_panels, strict=True), start=1
        ):
            indices = manifest_panel.get("axial_indices_zyx_absolute")
            panel_path = (panel_root / record_panel["panel"]).resolve()
            if (
                manifest_panel.get("panel_number") != panel_number
                or manifest_panel.get("panel_total") != expected_panels
                or manifest_panel.get("image") != panel_path.name
                or manifest_panel.get("sha256") != record_panel.get("panel_sha256")
                or manifest_panel.get("png_metadata_keys") != []
                or not isinstance(indices, list)
                or len(indices) != 9
                or len(set(indices)) != 9
                or indices != sorted(indices)
            ):
                raise PipelineError("Metadados de painel liver-enriched invalidos.")
            with Image.open(panel_path) as image:
                image.load()
                if image.mode != "RGB" or image.info or image.width < 1 or image.height < 1:
                    raise PipelineError("PNG liver-enriched invalido ou com metadados.")
                dimensions.add(image.size)
            per_panel_indices.append(indices)
        all_indices = views.get("all_axial_indices_zyx_absolute")
        interleaved = [
            per_panel_indices[panel_index][tile_index]
            for tile_index in range(9)
            for panel_index in range(expected_panels)
        ]
        if (
            not isinstance(all_indices, list)
            or all_indices != sorted(all_indices)
            or len(set(all_indices)) != expected_slices
            or interleaved != all_indices
        ):
            raise PipelineError("Intercalacao axial liver-enriched foi adulterada.")
        stable += int(localizer_stable)
        weak += int(not localizer_stable)
        total_panels += expected_panels
    if (
        cohort.get("stable_localizer_case_count") != stable
        or cohort.get("weak_localizer_fallback_case_count") != weak
        or cohort.get("total_panel_image_count") != total_panels
        or stable + weak != FULL_ELIGIBLE_CASE_COUNT
    ):
        raise PipelineError("Totais da coorte liver-enriched divergem dos artefatos.")
    base = {
        "schema": FULL_VERIFICATION_SCHEMA,
        "status": "independently_verified_pending_human_review",
        "source_cohort_sha256": _sha256(cohort_path),
        "cohort_signature": cohort_signature,
        "preparation_signature": preparation_signature,
        "case_count": len(records),
        "protocol_case_count": FULL_PROTOCOL_CASE_COUNT,
        "technical_failure_case_count": len(failures),
        "stable_localizer_case_count": stable,
        "weak_localizer_fallback_case_count": weak,
        "panel_image_count": total_panels,
        "panel_dimensions": [list(value) for value in sorted(dimensions)],
        "all_manifest_and_panel_hashes_verified": True,
        "all_axial_interleaving_verified": True,
        "png_metadata_absent": True,
        "ground_truth_read": False,
        "lesion_masks_read": 0,
        "eligible_for_inference": False,
    }
    return {**base, "verification_signature": _canonical_sha(base)}


__all__ = [
    "COHORT_SCHEMA", "GALLERY_SCHEMA", "FULL_VERIFICATION_SCHEMA",
    "build_liver_enriched_full_cohort", "build_liver_enriched_gallery",
    "build_liver_enriched_pilot", "verify_liver_enriched_full_cohort",
]
