from __future__ import annotations

import pytest

from dtwin.benchmark import openswisshcc_candidate_volume_evaluation as evaluation
from dtwin.core import PipelineError


def _rows(count: int = 20):
    rows = []
    for index in range(count):
        positive = index >= count // 2
        rows.append(
            {
                "case_id": f"anon-{index:03d}",
                "case_score": float(index),
                "selected_candidate_classification": "POSITIVA" if positive else "NEGATIVA",
                "selected_candidate_number": 1,
                "candidate_stack_count": 1,
                "scoring_elapsed_seconds": 10.0,
                "prediction_sha256": f"hash-{index}",
            }
        )
    return rows


def _protocol(rows):
    payload = {
        "schema": evaluation.PROTOCOL_SCHEMA,
        "status": "frozen_before_protected_development_labels",
        "case_count": len(rows),
        "case_ids": [row["case_id"] for row in rows],
        "primary_signal": evaluation.PRIMARY_SIGNAL,
        "development_gate": {
            "minimum_loocv_sensitivity": 0.75,
            "minimum_loocv_specificity": 0.75,
            "required_repeated_runs_passing_75_75": evaluation.REPEATS,
            "inconclusive_is_error_for_raw_categorical_diagnostic": True,
        },
        "score_time_gate_passed": True,
        "full_raw_dicom_end_to_end_180_seconds_proven": False,
        "ground_truth_read": False,
        "metrics_calculated": False,
        "holdout_opened": False,
    }
    payload["protocol_signature"] = evaluation._canonical_sha(payload)
    return payload


def test_protocol_freezes_blind_vector_and_refuses_overwrite(tmp_path, monkeypatch):
    rows = _rows()
    context = {
        "score_protocol": {"protocol_signature": "score-sig"},
        "progress_sha256": "progress-hash",
        "summary_sha256": "summary-hash",
        "summary": {
            "scoring_timing_seconds": {"minimum": 10.0, "median": 10.0, "mean": 10.0, "maximum": 10.0, "all_within_180": True},
            "timing_scope": "precomputed_candidate_scoring_only",
        },
    }
    monkeypatch.setattr(evaluation, "validate_blind_score_run", lambda **kwargs: (context, rows))
    out = tmp_path / "protocol.json"
    result = evaluation.create_evaluation_protocol(bundle_root=tmp_path, run_root=tmp_path, score_protocol_path=tmp_path / "score.json", output_path=out, expected_case_count=20)
    assert result["primary_signal"] == evaluation.PRIMARY_SIGNAL
    assert result["full_raw_dicom_end_to_end_180_seconds_proven"] is False
    assert result["ground_truth_read"] is False
    with pytest.raises(PipelineError, match="ja existe"):
        evaluation.create_evaluation_protocol(bundle_root=tmp_path, run_root=tmp_path, score_protocol_path=tmp_path / "score.json", output_path=out, expected_case_count=20)


def test_evaluation_aborts_before_reading_labels_without_authorization(tmp_path, monkeypatch):
    rows = _rows()
    monkeypatch.setattr(evaluation, "verify_evaluation_protocol", lambda **kwargs: (_protocol(rows), rows))
    monkeypatch.setattr(evaluation, "_load_development_labels", lambda *args, **kwargs: pytest.fail("labels foram lidos"))
    with pytest.raises(PipelineError, match="nao foi autorizada"):
        evaluation.evaluate_development(bundle_root=tmp_path, run_root=tmp_path, score_protocol_path=tmp_path / "s", evaluation_protocol_path=tmp_path / "e", labels_path=tmp_path / "labels", output_dir=tmp_path / "out", expected_case_count=20)


def test_authorized_evaluation_is_nested_atomic_and_keeps_holdout_closed(tmp_path, monkeypatch):
    rows = _rows()
    protocol = _protocol(rows)
    monkeypatch.setattr(evaluation, "verify_evaluation_protocol", lambda **kwargs: (protocol, rows))
    labels = {row["case_id"]: {"label": "POSITIVE" if index >= 10 else "NEGATIVE"} for index, row in enumerate(rows)}
    monkeypatch.setattr(evaluation, "_load_development_labels", lambda *args, **kwargs: (labels, "labels-hash"))
    out = tmp_path / "evaluation"
    result = evaluation.evaluate_development(bundle_root=tmp_path, run_root=tmp_path, score_protocol_path=tmp_path / "s", evaluation_protocol_path=tmp_path / "e", labels_path=tmp_path / "labels", output_dir=out, allow_protected_development_labels=True, expected_case_count=20)
    assert result["development_accuracy_gate_passed"] is True
    assert result["full_operational_gate_passed"] is False
    assert result["goal_75_75_and_full_180_proven"] is False
    assert result["holdout_opened"] is False
    assert (out / "evaluation.json").is_file()
    assert len((out / "case_scores.csv").read_text(encoding="utf-8").splitlines()) == 21


def test_raw_inconclusive_is_error_for_both_classes():
    rows = _rows(10)
    rows[0]["selected_candidate_classification"] = "INCONCLUSIVA"
    rows[-1]["selected_candidate_classification"] = "INCONCLUSIVA"
    truth = [False] * 5 + [True] * 5
    result = evaluation._raw_categorical(rows, truth)
    assert result["inconclusive_count"] == 2
    assert result["fp"] == 1
    assert result["fn"] == 1


def test_loocv_and_repeated_fit_threshold_on_training_only():
    scores = [float(index) for index in range(20)]
    truth = [False] * 10 + [True] * 10
    loocv = evaluation._loocv(scores, truth)
    repeated = evaluation._repeated_nested(scores, truth, repeats=3, folds=5)
    assert loocv["sensitivity"] >= 0.9
    assert loocv["specificity"] >= 0.9
    assert repeated["threshold_fit_inside_each_training_fold"] is True
    assert repeated["runs_passing_75_75"] == 3


def test_blind_run_rejects_forbidden_label_before_validation(tmp_path, monkeypatch):
    assert evaluation._contains_forbidden_key({"nested": {"label": "POSITIVE"}}) is True
    assert evaluation._contains_forbidden_key({"ground_truth_read": False}) is False


def test_protocol_signature_detects_tampering():
    rows = _rows()
    protocol = _protocol(rows)
    unsigned = {key: value for key, value in protocol.items() if key != "protocol_signature"}
    assert protocol["protocol_signature"] == evaluation._canonical_sha(unsigned)
    unsigned["score_time_gate_passed"] = False
    assert protocol["protocol_signature"] != evaluation._canonical_sha(unsigned)
