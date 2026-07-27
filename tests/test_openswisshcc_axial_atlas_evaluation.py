from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from dtwin.benchmark import openswisshcc_axial_atlas_evaluation as evaluation
from dtwin.benchmark import openswisshcc_axial_atlas_score as score
from dtwin.benchmark.openswisshcc_axial_atlas import PROTOCOL_SIGNATURE as ATLAS_SIGNATURE
from dtwin.benchmark.openswisshcc_highdimensional_inference import _canonical_hash
from dtwin.benchmark.openswisshcc_volume_score import CHOICES, CONTRACT, SCORING_METHOD
from dtwin.core import PipelineError, sha256_of


def _write(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True) + "\n", encoding="utf-8")


def _score_protocol(path: Path, case_ids: list[str]) -> dict:
    base = {
        "schema_version": score.PROTOCOL_SCHEMA,
        "status": "frozen_before_blind_4b_scores",
        "atlas_protocol_signature": ATLAS_SIGNATURE,
        "atlas_cohort_sha256": "atlas",
        "review_sha256": "review",
        "review_signature": "review-signature",
        "case_ids": case_ids,
        "case_count": len(case_ids),
        "maximum_frames": 20,
        "model_id": "google/medgemma-1.5-4b-it",
        "model_version": "MedGemma 1.5 4B Instruction-Tuned",
        "contract": CONTRACT,
        "endpoint_url": "http://127.0.0.1:8001/score-volume",
        "instruction": score.INSTRUCTION,
        "query_template": score.QUERY_TEMPLATE,
        "scoring": {
            "response_prefix": '{"resultado_hipotese":"',
            "choices": list(CHOICES),
            "method": SCORING_METHOD,
            "requests_per_case": 1,
            "automatic_retries": 0,
            "score": "log_odds_positive_vs_negative",
            "epsilon": 1e-8,
            "probability_tolerance": 1e-6,
        },
        "case_time_gate_seconds": 180.0,
        "maximum_image_edge": 768,
        "ground_truth_read": False,
        "metrics_calculated": False,
        "holdout_opened": False,
        "research_only": True,
        "clinical_use_allowed": False,
        "requires_human_review": True,
    }
    protocol = {**base, "protocol_signature": _canonical_hash(base)}
    _write(path, protocol)
    return protocol


def _probabilities(raw_score: float) -> dict[str, float]:
    positive_share = 1.0 / (1.0 + math.exp(-raw_score))
    return {
        "POSITIVA": 0.95 * positive_share,
        "NEGATIVA": 0.95 * (1.0 - positive_share),
        "INCONCLUSIVA": 0.05,
    }


def _blind_bundle(tmp_path: Path, count: int = 10) -> tuple[Path, Path, list[str]]:
    root = tmp_path / "scores"
    predictions = root / "predictions"
    predictions.mkdir(parents=True)
    case_ids = [f"anon-case-{index:03d}" for index in range(count)]
    protocol_path = tmp_path / "score_protocol.json"
    protocol = _score_protocol(protocol_path, case_ids)
    records, times = [], []
    for index, case_id in enumerate(case_ids):
        # Evita empate sintético exatamente em zero; empates reais são
        # validados separadamente pelo contrato do scorer.
        probabilities = _probabilities(float(index - count // 2) + 0.25)
        classification = max(probabilities, key=probabilities.get)
        calculated = score.score_log_odds(probabilities)
        elapsed = 5.0 + index / 10
        prediction = {
            "schema_version": score.PREDICTION_SCHEMA,
            "status": "technical_passed",
            "case_id": case_id,
            "protocol_signature": protocol["protocol_signature"],
            "classification": classification,
            "choice_probabilities": probabilities,
            "log_odds_positive_vs_negative": calculated,
            "request_elapsed_seconds": elapsed,
            "time_gate_passed": True,
            "tie_detected": False,
            "ground_truth_read": False,
            "metrics_calculated": False,
            "holdout_opened": False,
            "research_only": True,
            "clinical_use_allowed": False,
            "requires_human_review": True,
        }
        path = predictions / f"{case_id}.json"
        _write(path, prediction)
        records.append(
            {
                "case_id": case_id,
                "prediction_sha256": sha256_of(path),
                "classification": classification,
                "log_odds_positive_vs_negative": calculated,
                "request_elapsed_seconds": elapsed,
            }
        )
        times.append(elapsed)
    _write(
        root / "summary.json",
        {
            "schema_version": score.SUMMARY_SCHEMA,
            "status": "complete",
            "protocol_signature": protocol["protocol_signature"],
            "case_count": count,
            "completed_case_count": count,
            "pending_case_count": 0,
            "predictions": records,
            "request_count": count,
            "request_timing_seconds": {
                "minimum": min(times),
                "median": sorted(times)[len(times) // 2],
                "mean": sum(times) / len(times),
                "maximum": max(times),
                "all_within_180": True,
            },
            "timing_scope": "precomputed_atlas_scoring_only",
            "end_to_end_180_seconds_proven": False,
            "accuracy_claimed": False,
            "ground_truth_read": False,
            "metrics_calculated": False,
            "holdout_opened": False,
        },
    )
    return root, protocol_path, case_ids


def _labels(tmp_path: Path, case_ids: list[str], *, holdout: bool = False) -> Path:
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


def _frozen(tmp_path: Path, count: int = 10):
    root, score_protocol, case_ids = _blind_bundle(tmp_path, count)
    protocol = tmp_path / "evaluation_protocol.json"
    evaluation.freeze_evaluation_protocol(
        score_root=root,
        score_protocol_path=score_protocol,
        output_path=protocol,
        expected_case_count=count,
    )
    return root, score_protocol, protocol, case_ids


def test_freeze_is_blind_and_binds_complete_score_vector(tmp_path):
    root, score_protocol, protocol_path, case_ids = _frozen(tmp_path)
    protocol, rows = evaluation.verify_evaluation_protocol(
        score_root=root,
        score_protocol_path=score_protocol,
        protocol_path=protocol_path,
        expected_case_count=len(case_ids),
    )
    assert len(rows) == len(case_ids)
    assert protocol["status"] == "frozen_before_protected_development_labels"
    assert protocol["ground_truth_read"] is False
    assert protocol["holdout_opened"] is False
    assert protocol["development_gate"]["minimum_loocv_sensitivity"] == 0.75


def test_freeze_rejects_prediction_hash_tampering(tmp_path):
    root, score_protocol, case_ids = _blind_bundle(tmp_path)
    path = root / "predictions" / f"{case_ids[0]}.json"
    path.write_text(path.read_text(encoding="utf-8") + " ", encoding="utf-8")
    with pytest.raises(PipelineError, match="Hash"):
        evaluation.freeze_evaluation_protocol(
            score_root=root,
            score_protocol_path=score_protocol,
            output_path=tmp_path / "protocol.json",
            expected_case_count=len(case_ids),
        )


def test_freeze_rejects_argmax_divergence_even_with_updated_hash(tmp_path):
    root, score_protocol, case_ids = _blind_bundle(tmp_path)
    path = root / "predictions" / f"{case_ids[0]}.json"
    prediction = json.loads(path.read_text(encoding="utf-8"))
    prediction["classification"] = "INCONCLUSIVA"
    _write(path, prediction)
    summary_path = root / "summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    summary["predictions"][0]["classification"] = "INCONCLUSIVA"
    summary["predictions"][0]["prediction_sha256"] = sha256_of(path)
    _write(summary_path, summary)
    with pytest.raises(PipelineError, match="Argmax"):
        evaluation.freeze_evaluation_protocol(
            score_root=root,
            score_protocol_path=score_protocol,
            output_path=tmp_path / "protocol.json",
            expected_case_count=len(case_ids),
        )


def test_evaluation_requires_explicit_authorization(tmp_path):
    root, score_protocol, protocol, case_ids = _frozen(tmp_path)
    labels = _labels(tmp_path, case_ids)
    with pytest.raises(PipelineError, match="não foi autorizada"):
        evaluation.evaluate_development(
            score_root=root,
            score_protocol_path=score_protocol,
            protocol_path=protocol,
            labels_path=labels,
            output_dir=tmp_path / "evaluation",
            expected_case_count=len(case_ids),
        )
    assert not (tmp_path / "evaluation").exists()


def test_evaluation_rejects_holdout_even_when_flag_is_true(tmp_path):
    root, score_protocol, protocol, case_ids = _frozen(tmp_path)
    labels = _labels(tmp_path, case_ids, holdout=True)
    with pytest.raises(PipelineError, match="nunca holdout"):
        evaluation.evaluate_development(
            score_root=root,
            score_protocol_path=score_protocol,
            protocol_path=protocol,
            labels_path=labels,
            output_dir=tmp_path / "evaluation",
            allow_protected_development_labels=True,
            expected_case_count=len(case_ids),
        )


def test_separable_scores_pass_reader_gate_but_not_final_qualification(tmp_path):
    root, score_protocol, protocol, case_ids = _frozen(tmp_path)
    result = evaluation.evaluate_development(
        score_root=root,
        score_protocol_path=score_protocol,
        protocol_path=protocol,
        labels_path=_labels(tmp_path, case_ids),
        output_dir=tmp_path / "evaluation",
        allow_protected_development_labels=True,
        expected_case_count=len(case_ids),
    )
    assert result["development_reader_gate_passed"] is True
    assert result["primary_loocv_metrics"]["sensitivity"] == 1.0
    assert result["primary_loocv_metrics"]["specificity"] == 1.0
    assert result["secondary_diagnostics_not_eligible_to_replace_primary"]["apparent_roc_auc"] == 1.0
    assert result["qualified"] is False
    assert result["end_to_end_180_seconds_proven"] is False
    assert result["holdout_opened"] is False
    assert (tmp_path / "evaluation" / "evaluation.json").is_file()
    assert (tmp_path / "evaluation" / "case_scores.csv").is_file()


def test_existing_protocol_cannot_be_silently_replaced(tmp_path):
    root, score_protocol, protocol_path, case_ids = _frozen(tmp_path)
    protocol = json.loads(protocol_path.read_text(encoding="utf-8"))
    protocol["primary_signal"] = "altered"
    _write(protocol_path, protocol)
    with pytest.raises(PipelineError, match="diverge"):
        evaluation.freeze_evaluation_protocol(
            score_root=root,
            score_protocol_path=score_protocol,
            output_path=protocol_path,
            expected_case_count=len(case_ids),
        )
