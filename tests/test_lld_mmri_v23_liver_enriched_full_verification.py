from __future__ import annotations

import json
from pathlib import Path

import pytest
from PIL import Image, PngImagePlugin

from dtwin.benchmark import lld_mmri_v23_liver_enriched_pilot as module
from dtwin.benchmark.openswisshcc_alignment import _sha256
from dtwin.benchmark.openswisshcc_v20_fusion import _canonical_sha
from dtwin.core import PipelineError


def _write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, indent=2), encoding="utf-8")


def _fixture(
    tmp_path: Path, monkeypatch, *, png_metadata: bool = False,
    bad_interleave: bool = False,
) -> tuple[Path, Path, Path]:
    monkeypatch.setattr(module, "FULL_PROTOCOL_CASE_COUNT", 3)
    monkeypatch.setattr(module, "FULL_ELIGIBLE_CASE_COUNT", 2)
    monkeypatch.setattr(module, "FULL_TECHNICAL_FAILURE_COUNT", 1)
    prepared = tmp_path / "prepared"
    panels_root = tmp_path / "panels"
    prepared.mkdir()
    panels_root.mkdir()
    config = tmp_path / "config.yaml"
    config.write_text("medgemma_screening: {}\n", encoding="utf-8")
    case_ids = ["anon-lld-0000000000000001", "anon-lld-0000000000000002"]
    rows = [{"case_id": case_id} for case_id in case_ids]
    inputs = prepared / "inputs.jsonl"
    inputs.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    summary_base = {
        "case_ids": case_ids,
        "technical_failure_case_ids": ["anon-lld-0000000000000003"],
        "inputs_sha256": _sha256(inputs),
        "ground_truth_read": False,
        "lesion_masks_read": 0,
    }
    summary = {**summary_base, "preparation_signature": _canonical_sha(summary_base)}
    _write_json(prepared / "summary.json", summary)

    records = []
    for number, (case_id, stable) in enumerate(zip(case_ids, [True, False]), start=1):
        count = 3 if stable else 2
        all_indices = list(range(count * 9))
        per_panel = [all_indices[index::count] for index in range(count)]
        if bad_interleave and number == 1:
            per_panel[0][0], per_panel[0][1] = per_panel[0][1], per_panel[0][0]
        case_root = panels_root / case_id
        case_root.mkdir()
        manifest_panels = []
        record_panels = []
        for panel_number, indices in enumerate(per_panel, start=1):
            filename = f"medgemma_liver_screening_panel_{panel_number:03d}_of_{count:03d}.png"
            path = case_root / filename
            info = None
            if png_metadata and number == 1 and panel_number == 1:
                info = PngImagePlugin.PngInfo()
                info.add_text("forbidden", "metadata")
            Image.new("RGB", (2, 2), "black").save(path, pnginfo=info)
            digest = _sha256(path)
            manifest_panels.append({
                "panel_number": panel_number,
                "panel_total": count,
                "image": filename,
                "sha256": digest,
                "axial_indices_zyx_absolute": indices,
                "png_metadata_keys": [] if info is None else ["forbidden"],
            })
            record_panels.append({
                "panel_number": panel_number,
                "panel": f"{case_id}/{filename}",
                "panel_sha256": digest,
            })
        mode = (
            "stable_coarse_localizer_interleaved_3x9"
            if stable else
            "weak_localizer_mask_independent_cranial_75pct_interleaved_2x9"
        )
        manifest = {
            "case_id": case_id,
            "spatial_policy": module.LIVER_ENRICHED_POLICY,
            "organ_mask_use_scope": "coarse_axial_localization_only_not_rendered_not_cropped",
            "organ_mask_rendered": False,
            "lesion_mask_used": False,
            "ground_truth_used": False,
            "crop_to_liver": False,
            "contour_rendered": False,
            "phi_metadata_removed": True,
            "visible_phi_review_required": True,
            "requires_human_review": True,
            "panel_image_count": count,
            "panels": manifest_panels,
            "localization": {
                "selection_mode": mode,
                "localizer_stable": stable,
                "selected_distinct_axial_count": count * 9,
            },
            "views": {
                "total_distinct_axial_indices": count * 9,
                "all_axial_indices_zyx_absolute": all_indices,
            },
        }
        manifest_path = case_root / "medgemma_liver_screening_manifest.json"
        _write_json(manifest_path, manifest)
        records.append({
            "number": number,
            "case_id": case_id,
            "selection_mode": mode,
            "localizer_stable": stable,
            "panel_image_count": count,
            "panels": record_panels,
            "manifest": f"{case_id}/{manifest_path.name}",
            "manifest_sha256": _sha256(manifest_path),
        })
    cohort_base = {
        "schema": module.COHORT_SCHEMA,
        "status": "complete_pending_human_review",
        "protocol_case_count": 3,
        "case_count": 2,
        "case_ids": case_ids,
        "technical_failure_case_count": 1,
        "technical_failure_case_ids": ["anon-lld-0000000000000003"],
        "spatial_policy": module.LIVER_ENRICHED_POLICY,
        "config_sha256": _sha256(config),
        "source_preparation_signature": summary["preparation_signature"],
        "source_inputs_sha256": _sha256(inputs),
        "stable_localizer_case_count": 1,
        "weak_localizer_fallback_case_count": 1,
        "total_panel_image_count": 5,
        "cases": records,
        "organ_masks_read_for_localization_only": 2,
        "organ_masks_rendered": 0,
        "lesion_masks_read": 0,
        "ground_truth_read": False,
        "eligible_for_inference": False,
        "research_only": True,
        "clinical_use_allowed": False,
    }
    _write_json(
        panels_root / "cohort_manifest.json",
        {**cohort_base, "cohort_signature": _canonical_sha(cohort_base)},
    )
    return panels_root, prepared, config


def test_full_verifier_recomputes_every_contract(monkeypatch, tmp_path: Path):
    panel_root, prepared, config = _fixture(tmp_path, monkeypatch)
    result = module.verify_liver_enriched_full_cohort(
        panel_root=panel_root, prepared_root=prepared, config_path=config,
    )
    assert result["case_count"] == 2
    assert result["panel_image_count"] == 5
    assert result["all_manifest_and_panel_hashes_verified"] is True
    assert result["all_axial_interleaving_verified"] is True
    assert result["png_metadata_absent"] is True


def test_full_verifier_rejects_axial_interleaving_tamper(monkeypatch, tmp_path: Path):
    panel_root, prepared, config = _fixture(
        tmp_path, monkeypatch, bad_interleave=True,
    )
    with pytest.raises(PipelineError, match="Metadados|Intercalacao"):
        module.verify_liver_enriched_full_cohort(
            panel_root=panel_root, prepared_root=prepared, config_path=config,
        )


def test_full_verifier_rejects_png_metadata(monkeypatch, tmp_path: Path):
    panel_root, prepared, config = _fixture(
        tmp_path, monkeypatch, png_metadata=True,
    )
    with pytest.raises(PipelineError, match="Metadados|PNG"):
        module.verify_liver_enriched_full_cohort(
            panel_root=panel_root, prepared_root=prepared, config_path=config,
        )


def test_full_verifier_rejects_panel_byte_tamper(monkeypatch, tmp_path: Path):
    panel_root, prepared, config = _fixture(tmp_path, monkeypatch)
    panel = next(panel_root.rglob("*.png"))
    panel.write_bytes(panel.read_bytes() + b"tamper")
    with pytest.raises(PipelineError, match="painel invalido"):
        module.verify_liver_enriched_full_cohort(
            panel_root=panel_root, prepared_root=prepared, config_path=config,
        )
