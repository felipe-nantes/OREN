from pathlib import Path

import pytest

from dtwin.benchmark import openswisshcc_volumetric_batch as batch
from dtwin.core import PipelineError


def test_batch_publishes_only_complete_reviewed_cohort(tmp_path, monkeypatch):
    source = tmp_path / "source"
    source.mkdir()
    ids = ["anon-a", "anon-b"]
    monkeypatch.setattr(batch, "ready_case_ids", lambda root: ids)
    monkeypatch.setattr(
        batch,
        "verify_panel_review",
        lambda **kwargs: {"review_signature": "review-signature"},
    )

    def fake_renderer(**kwargs):
        case_id = kwargs["case_id"]
        case = kwargs["output_root"] / case_id
        case.mkdir()
        return {
            "case_id": case_id,
            "candidate_kind": "multiphase_rgb" if case_id == "anon-a" else "venous_single_phase_fallback",
            "candidate_signature": f"signature-{case_id}",
            "panel_strategy": "volumetric_blocks",
            "panel_image_count": 2 if case_id == "anon-a" else 3,
            "panel_set_sha256": f"set-{case_id}",
            "coverage": {
                "gate_passed": True,
                "total_liver_voxels": 100,
                "covered_liver_voxels": 100,
            },
        }

    output = tmp_path / "published"
    result = batch.build_volumetric_candidate_cohort(
        input_root=tmp_path / "inputs",
        alignment_root=tmp_path / "alignments",
        source_panel_root=source,
        source_review_path=tmp_path / "review.json",
        output_root=output,
        multiphase_config=Path("multi.yaml"),
        fallback_config=Path("fallback.yaml"),
        high_contrast_fallback_config=Path("high.yaml"),
        source_high_contrast_config=Path("source-high.yaml"),
        profile_path=Path("profile.yaml"),
        expected_case_count=2,
        renderer=fake_renderer,
    )
    assert result["case_count"] == 2
    assert result["panel_image_count"] == 5
    assert result["max_panels_per_case"] == 3
    assert result["source_review_signature"] == "review-signature"
    assert result["ground_truth_read"] is False
    assert result["inference_executed"] is False
    assert result["requires_new_human_review"] is True
    assert (output / "cohort_manifest.json").is_file()


def test_batch_rejects_existing_destination(tmp_path):
    output = tmp_path / "published"
    output.mkdir()
    with pytest.raises(PipelineError, match="ja existe"):
        batch.build_volumetric_candidate_cohort(
            input_root=tmp_path,
            alignment_root=tmp_path,
            source_panel_root=tmp_path,
            source_review_path=tmp_path / "review.json",
            output_root=output,
            multiphase_config=Path("multi.yaml"),
            fallback_config=Path("fallback.yaml"),
            high_contrast_fallback_config=Path("high.yaml"),
            source_high_contrast_config=Path("source-high.yaml"),
            profile_path=Path("profile.yaml"),
        )

