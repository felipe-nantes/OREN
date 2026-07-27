from __future__ import annotations

import json
from pathlib import Path

from PIL import Image
import pytest

from dtwin.benchmark.lld_mmri_v23_panels import COHORT_SCHEMA, GALLERY_SCHEMA
from dtwin.benchmark.lld_mmri_v23_review import (
    REVIEW_SCHEMA,
    create_lld_mmri_v23_review,
    verify_lld_mmri_v23_review,
)
from dtwin.benchmark.openswisshcc_alignment import _sha256
from dtwin.benchmark.openswisshcc_v20_fusion import _canonical_sha
from dtwin.core import PipelineError


def _sources(tmp_path: Path) -> tuple[Path, Path]:
    case_id = "anon-lld-0000000000000000"
    failure_id = "anon-lld-9999999999999999"
    panels = tmp_path / "panels"
    panel = panels / case_id / "panel.png"
    panel.parent.mkdir(parents=True)
    Image.new("RGB", (64, 64), "black").save(panel)
    cohort_base = {
        "schema": COHORT_SCHEMA,
        "status": "complete_pending_human_review",
        "protocol_case_count": 2,
        "case_count": 1,
        "technical_failure_case_count": 1,
        "technical_failure_case_ids": [failure_id],
        "technical_failures_excluded_from_inference": True,
        "technical_failures_count_as_primary_metric_errors": True,
        "case_ids": [case_id],
        "cases": [{"case_id": case_id, "panel": f"{case_id}/panel.png", "panel_sha256": _sha256(panel)}],
        "all_panels_uniform9": True,
        "all_panels_pending_human_review": True,
        "lesion_masks_used": False,
        "pathology_labels_used": False,
        "ground_truth_read": False,
    }
    cohort = dict(cohort_base)
    cohort["cohort_signature"] = _canonical_sha(cohort_base)
    cohort_path = panels / "cohort_manifest.json"
    cohort_path.write_text(json.dumps(cohort), encoding="utf-8")

    gallery = tmp_path / "gallery"
    image = gallery / "images" / f"001_{case_id}.png"
    image.parent.mkdir(parents=True)
    image.write_bytes(panel.read_bytes())
    index = gallery / "index.html"
    index.write_text("<html>technical</html>", encoding="utf-8")
    gallery_base = {
        "schema": GALLERY_SCHEMA,
        "status": "pending_human_review",
        "protocol_case_count": 2,
        "case_count": 1,
        "technical_failure_case_count": 1,
        "technical_failure_case_ids": [failure_id],
        "technical_failures_excluded_from_inference": True,
        "technical_failures_count_as_primary_metric_errors": True,
        "cases": [{"number": 1, "case_id": case_id, "image": f"images/{image.name}", "sha256": _sha256(image)}],
        "source_cohort_sha256": _sha256(cohort_path),
        "source_cohort_signature": cohort["cohort_signature"],
        "index_sha256": _sha256(index),
        "approved": False,
        "ground_truth_read": False,
    }
    manifest = dict(gallery_base)
    manifest["gallery_signature"] = _canonical_sha(gallery_base)
    (gallery / "gallery_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return panels, gallery


def test_creates_and_verifies_all_case_review(tmp_path: Path):
    panels, gallery = _sources(tmp_path)
    review_path = tmp_path / "review.json"
    created = create_lld_mmri_v23_review(
        panel_root=panels,
        gallery_root=gallery,
        output_path=review_path,
        reviewer="jm",
        approved=True,
    )
    assert created["schema"] == REVIEW_SCHEMA
    assert created["all_cases_approved"] is True
    assert created["all_inference_eligible_cases_approved"] is True
    assert created["protocol_case_count"] == 2
    assert created["technical_failure_case_count"] == 1
    assert created["diagnostic_review_performed"] is False
    assert created["ground_truth_read"] is False
    verified = verify_lld_mmri_v23_review(
        panel_root=panels,
        gallery_root=gallery,
        review_path=review_path,
        expected_reviewer="jm",
    )
    assert verified == created


def test_review_requires_explicit_approval(tmp_path: Path):
    panels, gallery = _sources(tmp_path)
    with pytest.raises(PipelineError, match="aprovacao humana explicita"):
        create_lld_mmri_v23_review(
            panel_root=panels,
            gallery_root=gallery,
            output_path=tmp_path / "review.json",
            reviewer="jm",
            approved=False,
        )


def test_review_rejects_changed_gallery_image(tmp_path: Path):
    panels, gallery = _sources(tmp_path)
    image = next((gallery / "images").glob("*.png"))
    image.write_bytes(b"tampered")
    with pytest.raises(PipelineError, match="mudou"):
        create_lld_mmri_v23_review(
            panel_root=panels,
            gallery_root=gallery,
            output_path=tmp_path / "review.json",
            reviewer="jm",
            approved=True,
        )
