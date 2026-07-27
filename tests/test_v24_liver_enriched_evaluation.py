from __future__ import annotations

import pytest

from dtwin.benchmark import v24_liver_enriched_evaluation as subject


def test_combined_score_uses_frozen_80_20_weights(monkeypatch):
    monkeypatch.setattr(subject, "_score", lambda row, references: 0.75)
    monkeypatch.setattr(subject, "_ecdf", lambda value, reference: 0.25)
    value = subject._combined_score({}, 0.4, {}, [0.1, 0.2])
    assert value == pytest.approx(0.65)
    assert subject.V23_WEIGHT == 0.80
    assert subject.LIVER_ENRICHED_WEIGHT == 0.20


def test_prediction_keeps_technical_failure_without_fabricated_score():
    row = subject._prediction(
        case_id="anon-failure",
        score=None,
        threshold=None,
        status="technical_failure_count_as_error",
        extra={"validation": "loocv"},
    )
    assert row["prediction"] == "TECHNICAL_FAILURE"
    assert row["score"] is None
    assert row["threshold"] is None
    assert row["held_out_label_used_for_transform"] is False


def test_prediction_threshold_is_deterministic():
    positive = subject._prediction(
        case_id="a",
        score=0.5,
        threshold=0.5,
        status="complete",
        extra={},
    )
    negative = subject._prediction(
        case_id="b",
        score=0.499,
        threshold=0.5,
        status="complete",
        extra={},
    )
    assert positive["prediction"] == "POSITIVE"
    assert negative["prediction"] == "NEGATIVE"
