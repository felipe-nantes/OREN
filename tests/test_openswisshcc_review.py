import hashlib
import json
from pathlib import Path

import pytest

from dtwin.benchmark.openswisshcc_review import (
    create_panel_review,
    ready_case_ids,
    verify_panel_review,
)
from dtwin.core import PipelineError


def _candidate(root: Path, case_id: str = "anon-test") -> Path:
    case = root / case_id
    case.mkdir(parents=True)
    panel = case / "panel.png"
    panel.write_bytes(b"safe-panel-bytes")
    manifest = {
        "case_id": case_id,
        "candidate_signature": "candidate-signature",
        "candidate_version": "candidate-v1",
        "panel_filename": panel.name,
        "panel_sha256": hashlib.sha256(panel.read_bytes()).hexdigest(),
        "panel_bytes": panel.stat().st_size,
        "research_only": True,
        "clinical_use_allowed": False,
    }
    (case / "candidate_manifest.json").write_text(
        json.dumps(manifest), encoding="utf-8"
    )
    return panel


def _confirmations() -> dict[str, bool]:
    return {
        "no_visible_phi": True,
        "multiphase_alignment_acceptable": True,
        "liver_framing_acceptable": True,
    }


def test_review_is_separate_hash_bound_and_verifiable(tmp_path):
    panels = tmp_path / "panels"
    _candidate(panels)
    review_path = tmp_path / "reviews" / "approved.json"
    result = create_panel_review(
        panel_root=panels,
        case_ids=["anon-test"],
        output_path=review_path,
        reviewer="human-reviewer",
        confirmations=_confirmations(),
    )
    assert result["panel_count"] == 1
    assert result["ground_truth_read"] is False
    assert result["inference_executed"] is False
    assert verify_panel_review(
        review_path=review_path,
        panel_root=panels,
        required_case_ids=["anon-test"],
    )["review_signature"] == result["review_signature"]


def test_review_rejects_missing_explicit_confirmation(tmp_path):
    panels = tmp_path / "panels"
    _candidate(panels)
    confirmations = _confirmations()
    confirmations["no_visible_phi"] = False
    with pytest.raises(PipelineError, match="confirmações visuais"):
        create_panel_review(
            panel_root=panels,
            case_ids=["anon-test"],
            output_path=tmp_path / "review.json",
            reviewer="human-reviewer",
            confirmations=confirmations,
        )


def test_review_fails_if_approved_panel_bytes_change(tmp_path):
    panels = tmp_path / "panels"
    panel = _candidate(panels)
    review_path = tmp_path / "review.json"
    create_panel_review(
        panel_root=panels,
        case_ids=["anon-test"],
        output_path=review_path,
        reviewer="human-reviewer",
        confirmations=_confirmations(),
    )
    panel.write_bytes(b"changed-after-review")
    with pytest.raises(PipelineError, match="Hash do painel"):
        verify_panel_review(review_path=review_path, panel_root=panels)


def test_review_fails_if_manifest_is_tampered(tmp_path):
    panels = tmp_path / "panels"
    _candidate(panels)
    review_path = tmp_path / "review.json"
    create_panel_review(
        panel_root=panels,
        case_ids=["anon-test"],
        output_path=review_path,
        reviewer="human-reviewer",
        confirmations=_confirmations(),
    )
    review = json.loads(review_path.read_text(encoding="utf-8"))
    review["reviewer"] = "tampered"
    review_path.write_text(json.dumps(review), encoding="utf-8")
    with pytest.raises(PipelineError, match="Assinatura"):
        verify_panel_review(review_path=review_path, panel_root=panels)


def test_review_fails_if_signed_methodology_is_tampered(tmp_path):
    panels = tmp_path / "panels"
    _candidate(panels)
    review_path = tmp_path / "review.json"
    create_panel_review(
        panel_root=panels,
        case_ids=["anon-test"],
        output_path=review_path,
        reviewer="human-reviewer",
        confirmations=_confirmations(),
    )
    review = json.loads(review_path.read_text(encoding="utf-8"))
    review["reviewed_at_utc"] = "2000-01-01T00:00:00+00:00"
    review_path.write_text(json.dumps(review), encoding="utf-8")
    with pytest.raises(PipelineError, match="Assinatura"):
        verify_panel_review(review_path=review_path, panel_root=panels)


def test_review_rejects_different_requested_case_set(tmp_path):
    panels = tmp_path / "panels"
    _candidate(panels)
    review_path = tmp_path / "review.json"
    create_panel_review(
        panel_root=panels,
        case_ids=["anon-test"],
        output_path=review_path,
        reviewer="human-reviewer",
        confirmations=_confirmations(),
    )
    with pytest.raises(PipelineError, match="não corresponde"):
        verify_panel_review(
            review_path=review_path,
            panel_root=panels,
            required_case_ids=["anon-other"],
        )


def test_ready_case_ids_ignore_staging_and_gate_failures(tmp_path):
    panels = tmp_path / "panels"
    _candidate(panels, "anon-ready")
    (panels / ".anon-staging").mkdir()
    (panels / "anon-incomplete").mkdir()
    assert ready_case_ids(panels) == ["anon-ready"]


def test_review_does_not_overwrite_existing_approval(tmp_path):
    panels = tmp_path / "panels"
    _candidate(panels)
    review_path = tmp_path / "review.json"
    kwargs = dict(
        panel_root=panels,
        case_ids=["anon-test"],
        output_path=review_path,
        reviewer="human-reviewer",
        confirmations=_confirmations(),
    )
    create_panel_review(**kwargs)
    with pytest.raises(PipelineError, match="não será sobrescrito"):
        create_panel_review(**kwargs)
