from __future__ import annotations

import json
from pathlib import Path

import pytest
from PIL import Image

from dtwin.benchmark.lld_mmri_v23_liver_enriched_pilot import (
    COHORT_SCHEMA,
    GALLERY_SCHEMA,
)
from dtwin.benchmark.lld_mmri_v23_liver_enriched_review import (
    create_liver_enriched_human_review,
    verify_liver_enriched_human_review,
)
from dtwin.benchmark.openswisshcc_alignment import _sha256
from dtwin.benchmark.openswisshcc_v20_fusion import _canonical_sha
from dtwin.core import PipelineError
from dtwin.medgemma_panel_liver_enriched import LIVER_ENRICHED_POLICY


def _signed(value: dict, key: str) -> dict:
    return {**value, key: _canonical_sha(value)}


def _sources(tmp_path: Path, *, config_sha256: str = "a" * 64):
    panel_root = tmp_path / "panels"
    gallery_root = tmp_path / "gallery"
    image_root = gallery_root / "images"
    image_root.mkdir(parents=True)
    cases = []
    items = []
    for sequence, (case_id, stable, count) in enumerate(
        (("anon-stable", True, 3), ("anon-fallback", False, 2)), start=1
    ):
        case_dir = panel_root / case_id
        case_dir.mkdir(parents=True)
        source_panels = []
        copied_panels = []
        manifest_panels = []
        for number in range(1, count + 1):
            source = case_dir / f"panel_{number}.png"
            copied = image_root / f"{case_id}_{number}.png"
            Image.new("RGB", (128, 128), (sequence, number, 0)).save(source)
            copied.write_bytes(source.read_bytes())
            digest = _sha256(source)
            source_panels.append({
                "panel_number": number,
                "panel": f"{case_id}/{source.name}",
                "panel_sha256": digest,
            })
            copied_panels.append({
                "panel_number": number,
                "image": f"images/{copied.name}",
                "sha256": digest,
            })
            manifest_panels.append({"panel_number": number, "image": source.name, "sha256": digest})
        manifest = case_dir / "medgemma_liver_screening_manifest.json"
        manifest.write_text(json.dumps({
            "spatial_policy": LIVER_ENRICHED_POLICY,
            "panel_image_count": count,
            "panels": manifest_panels,
            "input_volume_sha256": "1" * 64,
            "coarse_liver_mask_sha256": "2" * 64,
            "views": {"total_distinct_axial_indices": count * 9},
            "organ_mask_rendered": False,
            "lesion_mask_used": False,
            "ground_truth_used": False,
            "crop_to_liver": False,
            "contour_rendered": False,
        }), encoding="utf-8")
        mode = "stable_coarse_localizer_interleaved_3x9" if stable else "weak_localizer_mask_independent_cranial_75pct_interleaved_2x9"
        cases.append({
            "number": sequence, "case_id": case_id, "selection_mode": mode,
            "localizer_stable": stable, "panel_image_count": count,
            "panels": source_panels, "manifest": f"{case_id}/{manifest.name}",
            "manifest_sha256": _sha256(manifest),
        })
        items.append({
            "case_id": case_id, "selection_mode": mode, "localizer_stable": stable,
            "panel_count": count, "panels": copied_panels,
        })
    cohort_base = {
        "schema": COHORT_SCHEMA, "status": "complete_pending_human_review",
        "case_count": 2, "case_ids": ["anon-stable", "anon-fallback"],
        "selection": "test", "spatial_policy": LIVER_ENRICHED_POLICY,
        "config_sha256": config_sha256,
        "stable_localizer_case_count": 1, "weak_localizer_fallback_case_count": 1,
        "total_panel_image_count": 5, "cases": cases,
        "organ_masks_read_for_localization_only": 2, "organ_masks_rendered": 0,
        "lesion_masks_read": 0, "ground_truth_read": False,
        "eligible_for_inference": False, "research_only": True,
        "clinical_use_allowed": False,
    }
    cohort = _signed(cohort_base, "cohort_signature")
    cohort_path = panel_root / "cohort_manifest.json"
    cohort_path.write_text(json.dumps(cohort), encoding="utf-8")
    index = gallery_root / "index.html"
    index.write_text("<p>review</p>", encoding="utf-8")
    gallery_base = {
        "schema": GALLERY_SCHEMA, "status": "pending_human_review",
        "cohort_signature": cohort["cohort_signature"],
        "source_cohort_sha256": _sha256(cohort_path), "index_sha256": _sha256(index),
        "case_count": 2, "total_panel_image_count": 5, "items": items,
        "organ_masks_rendered": 0, "lesion_masks_read": 0,
        "ground_truth_read": False, "eligible_for_inference": False,
    }
    gallery = _signed(gallery_base, "gallery_signature")
    (gallery_root / "gallery_manifest.json").write_text(json.dumps(gallery), encoding="utf-8")
    return panel_root, gallery_root


def test_liver_enriched_review_roundtrip(tmp_path: Path):
    panels, gallery = _sources(tmp_path)
    review_path = tmp_path / "review.json"
    created = create_liver_enriched_human_review(
        panel_root=panels, gallery_root=gallery, output_path=review_path,
        reviewer="jm", approved=True,
    )
    verified = verify_liver_enriched_human_review(
        panel_root=panels, gallery_root=gallery, review_path=review_path,
        expected_reviewer="jm",
    )
    assert verified == created
    assert verified["stable_3panel_case_count"] == 1
    assert verified["fallback_2panel_case_count"] == 1


def test_liver_enriched_review_requires_explicit_approval(tmp_path: Path):
    panels, gallery = _sources(tmp_path)
    with pytest.raises(PipelineError, match="aprovacao humana explicita"):
        create_liver_enriched_human_review(
            panel_root=panels, gallery_root=gallery,
            output_path=tmp_path / "review.json", reviewer="jm", approved=False,
        )


def test_liver_enriched_review_detects_changed_panel(tmp_path: Path):
    panels, gallery = _sources(tmp_path)
    review_path = tmp_path / "review.json"
    create_liver_enriched_human_review(
        panel_root=panels, gallery_root=gallery, output_path=review_path,
        reviewer="jm", approved=True,
    )
    (gallery / "images" / "anon-fallback_2.png").write_bytes(b"changed")
    with pytest.raises(PipelineError, match="mudou antes da revisao"):
        verify_liver_enriched_human_review(
            panel_root=panels, gallery_root=gallery, review_path=review_path,
        )


def test_liver_enriched_review_detects_changed_html(tmp_path: Path):
    panels, gallery = _sources(tmp_path)
    review_path = tmp_path / "review.json"
    create_liver_enriched_human_review(
        panel_root=panels, gallery_root=gallery, output_path=review_path,
        reviewer="jm", approved=True,
    )
    (gallery / "index.html").write_text("changed", encoding="utf-8")
    with pytest.raises(PipelineError, match="Galeria liver-enriched invalida"):
        verify_liver_enriched_human_review(
            panel_root=panels, gallery_root=gallery, review_path=review_path,
        )
