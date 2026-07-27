from __future__ import annotations

import json
from pathlib import Path

import pytest

from dtwin.benchmark import openswisshcc_holdout_review as module
from dtwin.benchmark.openswisshcc_alignment import _sha256
from dtwin.benchmark.openswisshcc_holdout_panels import COHORT_SCHEMA, GALLERY_SCHEMA
from dtwin.core import PipelineError


def _write(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True), encoding="utf-8")


def _sources(tmp_path: Path) -> tuple[Path, Path]:
    panels = tmp_path / "panels"
    gallery = tmp_path / "gallery"
    panels.mkdir()
    gallery.mkdir()
    cohort_cases = []
    gallery_cases = []
    for index in range(1, 45):
        case_id = f"anon-openswiss-{index:016x}"
        kind = module.FALLBACK_KIND if index == module.EXPECTED_FALLBACK_INDEX else "multiphase_rgb"
        case_dir = panels / case_id
        case_dir.mkdir()
        panel = case_dir / "panel.png"
        panel.write_bytes(f"panel-{index}".encode())
        panel_sha = _sha256(panel)
        candidate = {
            "case_id": case_id,
            "candidate_kind": kind,
            "candidate_signature": f"signature-{index}",
            "status": "rendered_pending_human_review",
            "panel_sha256": panel_sha,
            "eligible_for_inference": False,
            "lesion_mask_used": False,
            "pathology_label_used": False,
            "holdout_ground_truth_opened": False,
        }
        candidate_path = case_dir / "candidate_manifest.json"
        _write(candidate_path, candidate)
        image = gallery / f"case-{index:03d}.png"
        image.write_bytes(panel.read_bytes())
        cohort_cases.append(
            {
                "case_id": case_id,
                "candidate_kind": kind,
                "candidate_manifest": f"{case_id}/candidate_manifest.json",
                "candidate_manifest_sha256": _sha256(candidate_path),
                "candidate_signature": candidate["candidate_signature"],
                "panel": f"{case_id}/panel.png",
                "panel_sha256": panel_sha,
            }
        )
        gallery_cases.append(
            {
                "index": index,
                "case_id": case_id,
                "candidate_kind": kind,
                "image": image.name,
                "sha256": panel_sha,
            }
        )
    cohort = {
        "schema": COHORT_SCHEMA,
        "status": "complete_pending_human_review",
        "case_count": 44,
        "multiphase_case_count": 43,
        "venous_fallback_case_count": 1,
        "cases": cohort_cases,
        "all_panels_uniform9": True,
        "all_panels_pending_human_review": True,
        "lesion_masks_used": False,
        "pathology_labels_used": False,
        "holdout_ground_truth_opened": False,
        "research_only": True,
        "clinical_use_allowed": False,
    }
    cohort["cohort_signature"] = module._canonical_sha(cohort)
    cohort_path = panels / "cohort_manifest.json"
    _write(cohort_path, cohort)
    (gallery / "index.html").write_text("<html>blind review</html>", encoding="utf-8")
    gallery_manifest = {
        "schema": GALLERY_SCHEMA,
        "status": "pending_human_review",
        "case_count": 44,
        "cases": gallery_cases,
        "panel_cohort_sha256": _sha256(cohort_path),
        "index_sha256": _sha256(gallery / "index.html"),
        "holdout_ground_truth_opened": False,
        "lesion_masks_used": False,
        "research_only": True,
        "clinical_use_allowed": False,
    }
    gallery_manifest["gallery_signature"] = module._canonical_sha(gallery_manifest)
    _write(gallery / "gallery_manifest.json", gallery_manifest)
    return panels, gallery


def test_holdout_review_requires_explicit_approval(tmp_path: Path):
    panels, gallery = _sources(tmp_path)
    with pytest.raises(PipelineError, match="aprovacao humana explicita"):
        module.create_holdout_uniform9_review(
            panel_root=panels,
            gallery_root=gallery,
            output_path=tmp_path / "review.json",
            reviewer="jm",
            approved=False,
        )


def test_holdout_signed_review_roundtrip(tmp_path: Path):
    panels, gallery = _sources(tmp_path)
    review_path = tmp_path / "review.json"
    created = module.create_holdout_uniform9_review(
        panel_root=panels,
        gallery_root=gallery,
        output_path=review_path,
        reviewer="jm",
        approved=True,
        note="technical review only",
    )
    verified = module.verify_holdout_uniform9_review(
        panel_root=panels,
        gallery_root=gallery,
        review_path=review_path,
        expected_reviewer="jm",
    )
    assert verified["review_signature"] == created["review_signature"]
    assert verified["case_count"] == 44
    assert verified["venous_fallback_gallery_index"] == 28
    assert verified["diagnostic_review_performed"] is False
    assert verified["holdout_ground_truth_opened"] is False


def test_holdout_review_detects_panel_change(tmp_path: Path):
    panels, gallery = _sources(tmp_path)
    review_path = tmp_path / "review.json"
    module.create_holdout_uniform9_review(
        panel_root=panels,
        gallery_root=gallery,
        output_path=review_path,
        reviewer="jm",
        approved=True,
    )
    (panels / "anon-openswiss-0000000000000001" / "panel.png").write_bytes(b"changed")
    with pytest.raises(PipelineError, match="divergiu"):
        module.verify_holdout_uniform9_review(
            panel_root=panels, gallery_root=gallery, review_path=review_path
        )


def test_holdout_review_detects_index_change(tmp_path: Path):
    panels, gallery = _sources(tmp_path)
    (gallery / "index.html").write_text("changed", encoding="utf-8")
    with pytest.raises(PipelineError, match="Galeria holdout"):
        module.create_holdout_uniform9_review(
            panel_root=panels,
            gallery_root=gallery,
            output_path=tmp_path / "review.json",
            reviewer="jm",
            approved=True,
        )


def test_holdout_review_rejects_fallback_outside_item_28(tmp_path: Path):
    panels, gallery = _sources(tmp_path)
    cohort_path = panels / "cohort_manifest.json"
    cohort = json.loads(cohort_path.read_text(encoding="utf-8"))
    cohort["cases"][27]["candidate_kind"] = "multiphase_rgb"
    cohort["cases"][0]["candidate_kind"] = module.FALLBACK_KIND
    cohort["cohort_signature"] = module._canonical_sha(
        {key: value for key, value in cohort.items() if key != "cohort_signature"}
    )
    _write(cohort_path, cohort)
    gallery_manifest_path = gallery / "gallery_manifest.json"
    gallery_manifest = json.loads(gallery_manifest_path.read_text(encoding="utf-8"))
    gallery_manifest["panel_cohort_sha256"] = _sha256(cohort_path)
    gallery_manifest["cases"][27]["candidate_kind"] = "multiphase_rgb"
    gallery_manifest["cases"][0]["candidate_kind"] = module.FALLBACK_KIND
    gallery_manifest["gallery_signature"] = module._canonical_sha(
        {key: value for key, value in gallery_manifest.items() if key != "gallery_signature"}
    )
    _write(gallery_manifest_path, gallery_manifest)
    with pytest.raises(PipelineError):
        module.create_holdout_uniform9_review(
            panel_root=panels,
            gallery_root=gallery,
            output_path=tmp_path / "review.json",
            reviewer="jm",
            approved=True,
        )


def test_holdout_review_detects_signature_tampering(tmp_path: Path):
    panels, gallery = _sources(tmp_path)
    review_path = tmp_path / "review.json"
    module.create_holdout_uniform9_review(
        panel_root=panels,
        gallery_root=gallery,
        output_path=review_path,
        reviewer="jm",
        approved=True,
    )
    review = json.loads(review_path.read_text(encoding="utf-8"))
    review["reviewer"] = "other"
    _write(review_path, review)
    with pytest.raises(PipelineError, match="adulterada"):
        module.verify_holdout_uniform9_review(
            panel_root=panels, gallery_root=gallery, review_path=review_path
        )
