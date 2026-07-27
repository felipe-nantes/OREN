from __future__ import annotations

import json
from pathlib import Path

import pytest
from PIL import Image

from dtwin.benchmark.lld_mmri_v23_full_fov_pilot import COHORT_SCHEMA, GALLERY_SCHEMA
from dtwin.benchmark.lld_mmri_v23_full_fov_review import (
    create_full_fov_human_review,
    verify_full_fov_human_review,
)
from dtwin.benchmark.openswisshcc_alignment import _sha256
from dtwin.benchmark.openswisshcc_v20_fusion import _canonical_sha
from dtwin.core import PipelineError
from dtwin.medgemma_panel_full_fov import FULL_FOV_MULTIPANEL_POLICY


def _signed(value: dict, key: str) -> dict:
    return {**value, key: _canonical_sha(value)}


def _sources(tmp_path: Path, *, config_sha256: str = "a" * 64) -> tuple[Path, Path]:
    panel_root = tmp_path / "panels"
    gallery_root = tmp_path / "gallery"
    case_id = "anon-lld-review-test"
    case_dir = panel_root / case_id
    image_dir = gallery_root / "images"
    case_dir.mkdir(parents=True)
    image_dir.mkdir(parents=True)
    panels = []
    copies = []
    for number in range(1, 4):
        source = case_dir / f"panel_{number}.png"
        copied = image_dir / f"copy_{number}.png"
        Image.new("RGB", (128, 128), (number, 0, 0)).save(source)
        copied.write_bytes(source.read_bytes())
        digest = _sha256(source)
        panels.append({"panel_number": number, "panel": f"{case_id}/{source.name}", "panel_sha256": digest})
        copies.append({"panel_number": number, "image": f"images/{copied.name}", "sha256": digest})
    manifest = case_dir / "medgemma_liver_screening_manifest.json"
    manifest.write_text(json.dumps({
        "case_id": case_id,
        "spatial_policy": FULL_FOV_MULTIPANEL_POLICY,
        "input_volume_sha256": "b" * 64,
        "organ_mask_used": False,
        "lesion_mask_used": False,
        "ground_truth_used": False,
        "panels": [
            {
                "panel_number": item["panel_number"],
                "panel_image": Path(item["panel"]).name,
                "panel_sha256": item["panel_sha256"],
                "axial_range": [(item["panel_number"] - 1) * 9, item["panel_number"] * 9 - 1],
            }
            for item in panels
        ],
        "views": {"total_distinct_axial_indices": 27},
    }), encoding="utf-8")
    cohort_base = {
        "schema": COHORT_SCHEMA,
        "status": "complete_pending_human_review",
        "case_count": 1,
        "case_ids": [case_id],
        "selection": "test",
        "spatial_policy": FULL_FOV_MULTIPANEL_POLICY,
        "config_sha256": config_sha256,
        "panel_image_count_per_case": 3,
        "total_panel_image_count": 3,
        "cases": [{
            "number": 1,
            "case_id": case_id,
            "panel": panels[0]["panel"],
            "panel_sha256": panels[0]["panel_sha256"],
            "panel_image_count": 3,
            "panels": panels,
            "manifest": f"{case_id}/{manifest.name}",
            "manifest_sha256": _sha256(manifest),
        }],
        "organ_masks_read": 0,
        "lesion_masks_read": 0,
        "ground_truth_read": False,
        "eligible_for_inference": False,
        "research_only": True,
        "clinical_use_allowed": False,
    }
    cohort = _signed(cohort_base, "cohort_signature")
    cohort_path = panel_root / "cohort_manifest.json"
    cohort_path.write_text(json.dumps(cohort), encoding="utf-8")
    index = gallery_root / "index.html"
    index.write_text("<p>review</p>", encoding="utf-8")
    gallery_base = {
        "schema": GALLERY_SCHEMA,
        "status": "pending_human_review",
        "cohort_signature": cohort["cohort_signature"],
        "source_cohort_sha256": _sha256(cohort_path),
        "index_sha256": _sha256(index),
        "case_count": 1,
        "total_panel_image_count": 3,
        "items": [{"case_id": case_id, "panel_count": 3, "panels": copies}],
        "organ_masks_read": 0,
        "lesion_masks_read": 0,
        "ground_truth_read": False,
        "eligible_for_inference": False,
    }
    gallery = _signed(gallery_base, "gallery_signature")
    (gallery_root / "gallery_manifest.json").write_text(json.dumps(gallery), encoding="utf-8")
    return panel_root, gallery_root


def test_full_fov_review_roundtrip_and_exact_sources(tmp_path: Path):
    panels, gallery = _sources(tmp_path)
    review_path = tmp_path / "review.json"
    created = create_full_fov_human_review(
        panel_root=panels,
        gallery_root=gallery,
        output_path=review_path,
        reviewer="jm",
        approved=True,
    )
    verified = verify_full_fov_human_review(
        panel_root=panels,
        gallery_root=gallery,
        review_path=review_path,
        expected_reviewer="jm",
    )
    assert verified == created
    assert verified["ground_truth_read"] is False
    assert verified["organ_masks_read"] == verified["lesion_masks_read"] == 0


def test_full_fov_review_refuses_missing_approval(tmp_path: Path):
    panels, gallery = _sources(tmp_path)
    with pytest.raises(PipelineError, match="aprovacao humana explicita"):
        create_full_fov_human_review(
            panel_root=panels,
            gallery_root=gallery,
            output_path=tmp_path / "review.json",
            reviewer="jm",
            approved=False,
        )


def test_full_fov_review_detects_changed_gallery_image(tmp_path: Path):
    panels, gallery = _sources(tmp_path)
    review_path = tmp_path / "review.json"
    create_full_fov_human_review(
        panel_root=panels,
        gallery_root=gallery,
        output_path=review_path,
        reviewer="jm",
        approved=True,
    )
    (gallery / "images" / "copy_2.png").write_bytes(b"tampered")
    with pytest.raises(PipelineError, match="mudou antes da revisao"):
        verify_full_fov_human_review(
            panel_root=panels,
            gallery_root=gallery,
            review_path=review_path,
        )


def test_full_fov_review_detects_changed_html(tmp_path: Path):
    panels, gallery = _sources(tmp_path)
    review_path = tmp_path / "review.json"
    create_full_fov_human_review(
        panel_root=panels,
        gallery_root=gallery,
        output_path=review_path,
        reviewer="jm",
        approved=True,
    )
    (gallery / "index.html").write_text("changed", encoding="utf-8")
    with pytest.raises(PipelineError, match="Galeria full-FOV 3x9 invalida"):
        verify_full_fov_human_review(
            panel_root=panels,
            gallery_root=gallery,
            review_path=review_path,
        )
