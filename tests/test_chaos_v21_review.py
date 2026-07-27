from __future__ import annotations

import json
from pathlib import Path

import pytest
from PIL import Image

from dtwin.benchmark import chaos_v21_review as module
from dtwin.benchmark.chaos_v21_panels import COHORT_SCHEMA, GALLERY_SCHEMA
from dtwin.core import PipelineError


def _write(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, sort_keys=True), encoding="utf-8")


def _sources(tmp_path: Path) -> tuple[Path, Path]:
    panels, gallery = tmp_path / "panels", tmp_path / "gallery"
    case = panels / "anon-public-test"
    case.mkdir(parents=True)
    panel = case / "panel.png"
    Image.new("RGB", (32, 32), "black").save(panel)
    cohort = {
        "schema": COHORT_SCHEMA, "status": "complete_pending_human_review",
        "case_count": 1, "case_ids": ["anon-public-test"],
        "cases": [{
            "case_id": "anon-public-test", "panel": "anon-public-test/panel.png",
            "panel_sha256": module._sha256(panel),
        }],
        "all_panels_pending_human_review": True,
        "lesion_masks_used": False, "pathology_labels_used": False,
        "ground_truth_read": False, "holdout_opened": False,
        "combined_primary_metric_allowed": False,
    }
    cohort["cohort_signature"] = module._canonical_sha(cohort)
    _write(panels / "cohort_manifest.json", cohort)
    gallery.mkdir()
    gallery_image = gallery / "01.png"
    gallery_image.write_bytes(panel.read_bytes())
    (gallery / "index.html").write_text("safe gallery", encoding="utf-8")
    gallery_data = {
        "schema": GALLERY_SCHEMA, "status": "pending_human_review",
        "approved": False,
        "cases": [{
            "case_id": "anon-public-test", "image": "01.png",
            "sha256": module._sha256(panel),
        }],
        "source_cohort_sha256": module._sha256(panels / "cohort_manifest.json"),
        "index_sha256": module._sha256(gallery / "index.html"),
        "ground_truth_read": False, "holdout_opened": False,
        "combined_primary_metric_allowed": False,
    }
    gallery_data["gallery_signature"] = module._canonical_sha(gallery_data)
    _write(gallery / "gallery_manifest.json", gallery_data)
    return panels, gallery


def test_review_requires_explicit_approval(tmp_path: Path):
    panels, gallery = _sources(tmp_path)
    with pytest.raises(PipelineError, match="aprovacao humana explicita"):
        module.create_chaos_v21_review(
            panel_root=panels, gallery_root=gallery,
            output_path=tmp_path / "review.json", reviewer="jm", approved=False,
        )


def test_review_is_signed_and_verifiable(tmp_path: Path):
    panels, gallery = _sources(tmp_path)
    path = tmp_path / "review.json"
    created = module.create_chaos_v21_review(
        panel_root=panels, gallery_root=gallery, output_path=path,
        reviewer="jm", approved=True,
    )
    verified = module.verify_chaos_v21_review(
        panel_root=panels, gallery_root=gallery, review_path=path,
        expected_reviewer="jm",
    )
    assert verified["review_signature"] == created["review_signature"]
    assert verified["diagnostic_review_performed"] is False
    assert verified["combined_primary_metric_allowed"] is False


def test_review_invalidates_after_gallery_image_change(tmp_path: Path):
    panels, gallery = _sources(tmp_path)
    path = tmp_path / "review.json"
    module.create_chaos_v21_review(
        panel_root=panels, gallery_root=gallery, output_path=path,
        reviewer="jm", approved=True,
    )
    (gallery / "01.png").write_bytes(b"changed")
    with pytest.raises(PipelineError, match="Hash"):
        module.verify_chaos_v21_review(
            panel_root=panels, gallery_root=gallery, review_path=path,
        )


def test_review_invalidates_after_signature_change(tmp_path: Path):
    panels, gallery = _sources(tmp_path)
    path = tmp_path / "review.json"
    module.create_chaos_v21_review(
        panel_root=panels, gallery_root=gallery, output_path=path,
        reviewer="jm", approved=True,
    )
    value = json.loads(path.read_text(encoding="utf-8"))
    value["reviewer"] = "other"
    _write(path, value)
    with pytest.raises(PipelineError, match="adulterada"):
        module.verify_chaos_v21_review(
            panel_root=panels, gallery_root=gallery, review_path=path,
        )
