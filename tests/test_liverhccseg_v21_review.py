from __future__ import annotations

import json
from pathlib import Path

import pytest
from PIL import Image

from dtwin.benchmark import liverhccseg_v21_review as module
from dtwin.benchmark.liverhccseg_v21_panels import COHORT_SCHEMA, GALLERY_SCHEMA
from dtwin.core import PipelineError


def _write(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def _sources(tmp_path: Path) -> tuple[Path, Path]:
    panels, gallery = tmp_path / "panels", tmp_path / "gallery"
    case_id = "anon-public-test"
    panel = panels / case_id / "panel.png"
    panel.parent.mkdir(parents=True)
    Image.new("RGB", (64, 64), "black").save(panel)
    digest = module._sha256(panel)
    cohort = {
        "schema": COHORT_SCHEMA, "status": "complete_pending_human_review",
        "case_count": 1, "case_ids": [case_id],
        "cases": [{"case_id": case_id, "panel": f"{case_id}/panel.png", "panel_sha256": digest}],
        "all_panels_pending_human_review": True, "lesion_masks_used": False,
        "pathology_labels_used": False, "ground_truth_read": False, "holdout_opened": False,
    }
    cohort["cohort_signature"] = module._canonical_sha(cohort)
    _write(panels / "cohort_manifest.json", cohort)
    gallery.mkdir()
    gallery_image = gallery / "01.png"
    Image.new("RGB", (64, 64), "black").save(gallery_image)
    (gallery / "index.html").write_text("safe gallery", encoding="utf-8")
    gallery_data = {
        "schema": GALLERY_SCHEMA, "status": "pending_human_review", "approved": False,
        "cases": [{"case_id": case_id, "image": "01.png", "sha256": digest}],
        "source_cohort_sha256": module._sha256(panels / "cohort_manifest.json"),
        "index_sha256": module._sha256(gallery / "index.html"),
        "ground_truth_read": False, "holdout_opened": False,
    }
    gallery_data["gallery_signature"] = module._canonical_sha(gallery_data)
    _write(gallery / "gallery_manifest.json", gallery_data)
    return panels, gallery


def test_review_requires_explicit_approval(tmp_path: Path):
    panels, gallery = _sources(tmp_path)
    with pytest.raises(PipelineError, match="explicita"):
        module.create_liverhccseg_v21_review(
            panel_root=panels, gallery_root=gallery, output_path=tmp_path / "review.json",
            reviewer="jm", approved=False,
        )


def test_signed_review_roundtrip(tmp_path: Path):
    panels, gallery = _sources(tmp_path)
    path = tmp_path / "review.json"
    created = module.create_liverhccseg_v21_review(
        panel_root=panels, gallery_root=gallery, output_path=path,
        reviewer="jm", approved=True, note="technical gate passed",
    )
    verified = module.verify_liverhccseg_v21_review(
        panel_root=panels, gallery_root=gallery, review_path=path, expected_reviewer="jm"
    )
    assert verified["review_signature"] == created["review_signature"]
    assert verified["diagnostic_review_performed"] is False
    assert verified["ground_truth_read"] is False


def test_review_detects_panel_change(tmp_path: Path):
    panels, gallery = _sources(tmp_path)
    path = tmp_path / "review.json"
    module.create_liverhccseg_v21_review(
        panel_root=panels, gallery_root=gallery, output_path=path, reviewer="jm", approved=True
    )
    panel = panels / "anon-public-test/panel.png"
    Image.new("RGB", (64, 64), "white").save(panel)
    with pytest.raises(PipelineError, match="divergiu"):
        module.verify_liverhccseg_v21_review(panel_root=panels, gallery_root=gallery, review_path=path)


def test_review_detects_signature_tampering(tmp_path: Path):
    panels, gallery = _sources(tmp_path)
    path = tmp_path / "review.json"
    module.create_liverhccseg_v21_review(
        panel_root=panels, gallery_root=gallery, output_path=path, reviewer="jm", approved=True
    )
    value = json.loads(path.read_text())
    value["reviewer"] = "other"
    _write(path, value)
    with pytest.raises(PipelineError, match="adulterada"):
        module.verify_liverhccseg_v21_review(panel_root=panels, gallery_root=gallery, review_path=path)

