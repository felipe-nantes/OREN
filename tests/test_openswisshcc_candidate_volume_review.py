from __future__ import annotations

import json

import pytest

import dtwin.benchmark.openswisshcc_candidate_volume_review as review
from dtwin.benchmark.openswisshcc_highdimensional_inference import _canonical_hash
from dtwin.core import PipelineError


def _bundle():
    return {
        "cohort_sha256": "a" * 64,
        "cohort": {"gallery_signature": "b" * 64},
        "case_count": 10,
        "candidate_stack_count": 27,
    }


def _confirmations(value=True):
    return {key: value for key in review.REQUIRED_CONFIRMATIONS}


def test_approved_review_requires_every_explicit_confirmation(tmp_path, monkeypatch):
    monkeypatch.setattr(review, "validate_candidate_volume_bundle", lambda _: _bundle())
    confirmations = _confirmations()
    confirmations["dynamic_t1_alignment"] = False
    with pytest.raises(PipelineError, match="todas as confirmacoes"):
        review.record_candidate_volume_review(
            bundle_root=tmp_path,
            out_path=tmp_path / "review.json",
            reviewer="jm",
            confirmations=confirmations,
            approved=True,
        )


def test_approved_review_is_signed_and_bound_to_exact_gallery(tmp_path, monkeypatch):
    monkeypatch.setattr(review, "validate_candidate_volume_bundle", lambda _: _bundle())
    path = tmp_path / "review.json"
    value = review.record_candidate_volume_review(
        bundle_root=tmp_path,
        out_path=path,
        reviewer="jm",
        confirmations=_confirmations(),
        approved=True,
        reviewed_at_utc="2026-07-16T12:00:00+00:00",
    )
    unsigned = dict(value)
    signature = unsigned.pop("review_signature")
    assert signature == _canonical_hash(unsigned)
    assert value["cohort_sha256"] == "a" * 64
    assert value["gallery_signature"] == "b" * 64
    assert value["ground_truth_read"] is False
    assert value["holdout_opened"] is False
    assert json.loads(path.read_text()) == value


def test_rejection_requires_notes_and_cannot_enable_scoring(tmp_path, monkeypatch):
    monkeypatch.setattr(review, "validate_candidate_volume_bundle", lambda _: _bundle())
    with pytest.raises(PipelineError, match="observacao"):
        review.record_candidate_volume_review(
            bundle_root=tmp_path,
            out_path=tmp_path / "review.json",
            reviewer="jm",
            confirmations=_confirmations(False),
            approved=False,
        )
    value = review.record_candidate_volume_review(
        bundle_root=tmp_path,
        out_path=tmp_path / "review.json",
        reviewer="jm",
        confirmations=_confirmations(False),
        approved=False,
        notes="Alinhamento insuficiente no candidato 2.",
    )
    assert value["status"] == "rejected_technical_review"


def test_review_record_refuses_overwrite(tmp_path, monkeypatch):
    monkeypatch.setattr(review, "validate_candidate_volume_bundle", lambda _: _bundle())
    path = tmp_path / "review.json"
    kwargs = dict(
        bundle_root=tmp_path,
        out_path=path,
        reviewer="jm",
        confirmations=_confirmations(),
        approved=True,
        reviewed_at_utc="2026-07-16T12:00:00+00:00",
    )
    review.record_candidate_volume_review(**kwargs)
    with pytest.raises(PipelineError, match="sobrescrita"):
        review.record_candidate_volume_review(**kwargs)
