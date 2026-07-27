from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from dtwin.benchmark import openswisshcc_axial_atlas_rag_evaluation as evaluation
from dtwin.benchmark import openswisshcc_axial_atlas_rag_score as score
from dtwin.core import PipelineError, sha256_of


def _write(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True) + "\n", encoding="utf-8")


def _probabilities(raw_score: float) -> dict[str, float]:
    positive_share = 1.0 / (1.0 + math.exp(-raw_score))
    return {
        "POSITIVA": 0.95 * positive_share,
        "NEGATIVA": 0.95 * (1.0 - positive_share),
        "INCONCLUSIVA": 0.05,
    }


def _bundle(tmp_path: Path, monkeypatch, count: int = 10):
    root = tmp_path / "scores"
    prediction_dir = root / "predictions"
    prediction_dir.mkdir(parents=True)
    case_ids = [f"anon-case-{index:03d}" for index in range(count)]
    protocol = {
        "protocol_signature": "score-protocol",
        "case_ids": case_ids,
        "rag_fingerprint": {"context_sha256": "rag-context"},
        "rag_addendum_sha256": "rag-addendum",
    }
    monkeypatch.setattr(evaluation, "_load_score_protocol", lambda _: protocol)
    records, elapsed_values = [], []
    for index, case_id in enumerate(case_ids):
        probabilities = _probabilities(float(index - count // 2) + 0.25)
        classification = max(probabilities, key=probabilities.get)
        raw = score.score_log_odds(probabilities)
        elapsed = 5.0 + index / 10
        prediction = {
            "schema_version": score.PREDICTION_SCHEMA,
            "status": "technical_passed",
            "case_id": case_id,
            "protocol_signature": protocol["protocol_signature"],
            "rag_context_sha256": "rag-context",
            "rag_addendum_sha256": "rag-addendum",
            "classification": classification,
            "choice_probabilities": probabilities,
            "log_odds_positive_vs_negative": raw,
            "request_elapsed_seconds": elapsed,
            "time_gate_passed": True,
            "tie_detected": False,
            "ground_truth_read_during_inference": False,
            "lesion_mask_read_during_inference": False,
            "metrics_calculated_during_inference": False,
            "holdout_opened": False,
            "research_only": True,
            "clinical_use_allowed": False,
        }
        path = prediction_dir / f"{case_id}.json"
        _write(path, prediction)
        records.append(
            {
                "case_id": case_id,
                "prediction_sha256": sha256_of(path),
                "classification": classification,
                "log_odds_positive_vs_negative": raw,
                "request_elapsed_seconds": elapsed,
            }
        )
        elapsed_values.append(elapsed)
    _write(
        root / "summary.json",
        {
            "schema_version": score.SUMMARY_SCHEMA,
            "status": "complete",
            "protocol_signature": protocol["protocol_signature"],
            "rag_context_sha256": "rag-context",
            "case_count": count,
            "completed_case_count": count,
            "pending_case_count": 0,
            "predictions": records,
            "request_count": count,
            "request_timing_seconds": {
                "minimum": min(elapsed_values),
                "median": (elapsed_values[count // 2 - 1] + elapsed_values[count // 2]) / 2,
                "mean": sum(elapsed_values) / count,
                "maximum": max(elapsed_values),
                "all_within_180": True,
            },
            "ground_truth_read_during_inference": False,
            "lesion_mask_read_during_inference": False,
            "metrics_calculated_during_inference": False,
            "holdout_opened": False,
            "accuracy_claimed": False,
        },
    )
    return root, tmp_path / "score_protocol.json", case_ids


def _labels(tmp_path: Path, case_ids: list[str], holdout: bool = False) -> Path:
    directory = tmp_path / ("holdout" if holdout else "protected_ground_truth")
    directory.mkdir()
    path = directory / "development_labels.jsonl"
    midpoint = len(case_ids) // 2
    rows = [
        {
            "schema": "argos-openswisshcc-ground-truth-v1",
            "case_id": case_id,
            "public_subject_id": str(index),
            "label": "NEGATIVE" if index < midpoint else "POSITIVE",
            "target_condition": "hcc_presence",
            "label_basis": "public",
            "review_status": "reviewed",
        }
        for index, case_id in enumerate(case_ids)
    ]
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    return path


def _frozen(tmp_path: Path, monkeypatch):
    root, score_protocol, case_ids = _bundle(tmp_path, monkeypatch)
    protocol_path = tmp_path / "evaluation_protocol.json"
    evaluation.freeze_evaluation_protocol(
        score_root=root,
        score_protocol_path=score_protocol,
        output_path=protocol_path,
        expected_case_count=len(case_ids),
    )
    return root, score_protocol, protocol_path, case_ids


def test_freeze_binds_rag_context_and_score_vector(tmp_path, monkeypatch):
    root, score_protocol, protocol_path, case_ids = _frozen(tmp_path, monkeypatch)
    protocol, rows = evaluation.verify_evaluation_protocol(
        score_root=root,
        score_protocol_path=score_protocol,
        protocol_path=protocol_path,
        expected_case_count=len(case_ids),
    )
    assert len(rows) == 10
    assert protocol["rag_context_sha256"] == "rag-context"
    assert protocol["ground_truth_read"] is False
    assert protocol["holdout_opened"] is False


def test_freeze_rejects_prediction_tampering(tmp_path, monkeypatch):
    root, score_protocol, case_ids = _bundle(tmp_path, monkeypatch)
    path = root / "predictions" / f"{case_ids[0]}.json"
    path.write_text(path.read_text(encoding="utf-8") + " ", encoding="utf-8")
    with pytest.raises(PipelineError, match="Hash"):
        evaluation.freeze_evaluation_protocol(
            score_root=root,
            score_protocol_path=score_protocol,
            output_path=tmp_path / "protocol.json",
            expected_case_count=len(case_ids),
        )


def test_evaluation_requires_new_explicit_authorization(tmp_path, monkeypatch):
    root, score_protocol, protocol_path, case_ids = _frozen(tmp_path, monkeypatch)
    with pytest.raises(PipelineError, match="não foi autorizada"):
        evaluation.evaluate_development(
            score_root=root,
            score_protocol_path=score_protocol,
            protocol_path=protocol_path,
            labels_path=_labels(tmp_path, case_ids),
            output_dir=tmp_path / "evaluation",
            expected_case_count=len(case_ids),
        )


def test_evaluation_rejects_holdout_even_with_flag(tmp_path, monkeypatch):
    root, score_protocol, protocol_path, case_ids = _frozen(tmp_path, monkeypatch)
    with pytest.raises(PipelineError, match="nunca holdout"):
        evaluation.evaluate_development(
            score_root=root,
            score_protocol_path=score_protocol,
            protocol_path=protocol_path,
            labels_path=_labels(tmp_path, case_ids, holdout=True),
            output_dir=tmp_path / "evaluation",
            allow_protected_development_labels=True,
            expected_case_count=len(case_ids),
        )


def test_separable_scores_pass_dev_gate_but_not_final_qualification(tmp_path, monkeypatch):
    root, score_protocol, protocol_path, case_ids = _frozen(tmp_path, monkeypatch)
    result = evaluation.evaluate_development(
        score_root=root,
        score_protocol_path=score_protocol,
        protocol_path=protocol_path,
        labels_path=_labels(tmp_path, case_ids),
        output_dir=tmp_path / "evaluation",
        allow_protected_development_labels=True,
        expected_case_count=len(case_ids),
    )
    assert result["development_reader_gate_passed"] is True
    assert result["primary_loocv_metrics"]["sensitivity"] == 1.0
    assert result["primary_loocv_metrics"]["specificity"] == 1.0
    assert result["qualified"] is False
    assert result["holdout_opened"] is False

