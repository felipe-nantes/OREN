from __future__ import annotations

import json
from pathlib import Path

import pytest

from dtwin.benchmark import lld_mmri_v23_liver_enriched_evaluation as module
from dtwin.benchmark.openswisshcc_alignment import _sha256
from dtwin.benchmark.openswisshcc_v20_fusion import _canonical_sha
from dtwin.core import PipelineError


def _write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True), encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )


def _signed(value: dict, field: str) -> dict:
    return {**value, field: _canonical_sha(value)}


def _report(case_id: str, decision: str, probabilities: list[dict]) -> dict:
    return {
        "case_id": case_id,
        "resultado_hipotese": decision,
        "panel_reports": [
            {
                "panel_number": index,
                "panel_total": len(probabilities),
                "response_validation_audit": {"choice_probabilities": probability},
            }
            for index, probability in enumerate(probabilities, start=1)
        ],
    }


def _artifacts(tmp_path: Path, monkeypatch):
    case_ids = ["case-pos", "case-neg", "case-inc", "case-fail-pos", "case-fail-neg"]
    eligible_ids = case_ids[:3]
    failure_ids = case_ids[3:]
    labels_path = tmp_path / "labels.jsonl"
    labels = [
        {"schema": module.LABEL_SCHEMA, "case_id": "case-pos", "label": "POSITIVE", "subtype": "hcc", "target_condition": "hcc_suspicion", "research_only": True, "clinical_use_allowed": False},
        {"schema": module.LABEL_SCHEMA, "case_id": "case-neg", "label": "NEGATIVE", "subtype": "benign", "target_condition": "hcc_suspicion", "research_only": True, "clinical_use_allowed": False},
        {"schema": module.LABEL_SCHEMA, "case_id": "case-inc", "label": "POSITIVE", "subtype": "hcc", "target_condition": "hcc_suspicion", "research_only": True, "clinical_use_allowed": False},
        {"schema": module.LABEL_SCHEMA, "case_id": "case-fail-pos", "label": "POSITIVE", "subtype": "hcc", "target_condition": "hcc_suspicion", "research_only": True, "clinical_use_allowed": False},
        {"schema": module.LABEL_SCHEMA, "case_id": "case-fail-neg", "label": "NEGATIVE", "subtype": "benign", "target_condition": "hcc_suspicion", "research_only": True, "clinical_use_allowed": False},
    ]
    _write_jsonl(labels_path, labels)
    public_protocol = {
        "case_ids": case_ids,
        "case_count": 5,
        "positive_count": 3,
        "negative_count": 2,
        "target_condition": "hcc_suspicion",
        "protocol_signature": "p" * 64,
        "protected_labels_sha256": _sha256(labels_path),
    }
    monkeypatch.setattr(module, "_load_and_validate_protocol", lambda _: (public_protocol, []))

    timing_protocol_path = tmp_path / "timing_protocol.json"
    timing_base = {
        "technical_failure_case_ids": failure_ids,
        "cases": [{"case_id": case_id} for case_id in eligible_ids],
    }
    timing_protocol = _signed(timing_base, "protocol_signature")
    _write_json(timing_protocol_path, timing_protocol)
    timing_verification = {
        "case_count": 3,
        "protocol_case_count": 5,
        "technical_failure_case_count": 2,
        "ground_truth_read": False,
        "lesion_masks_read": 0,
        "review_signature": "r" * 64,
        "run_signature": "u" * 64,
    }
    monkeypatch.setattr(module, "verify_liver_enriched_timing_run", lambda **_: timing_verification)

    timing_root = tmp_path / "timing"
    decisions = ["POSITIVA", "NEGATIVA", "INCONCLUSIVA"]
    probability_sets = [
        [{"POSITIVA": 0.2, "NEGATIVA": 0.7, "INCONCLUSIVA": 0.1}, {"POSITIVA": 0.8, "NEGATIVA": 0.1, "INCONCLUSIVA": 0.1}],
        [{"POSITIVA": 0.1, "NEGATIVA": 0.8, "INCONCLUSIVA": 0.1}],
        [{"POSITIVA": 0.4, "NEGATIVA": 0.2, "INCONCLUSIVA": 0.4}],
    ]
    timing_rows = []
    for case_id, decision, probabilities in zip(eligible_ids, decisions, probability_sets, strict=True):
        report_path = timing_root / case_id / "medgemma_report.json"
        manifest_path = timing_root / case_id / "timing_manifest.json"
        _write_json(report_path, _report(case_id, decision, probabilities))
        report_hash = _sha256(report_path)
        manifest = {
            "case_id": case_id,
            "prediction": decision,
            "report_sha256": report_hash,
            "panel_image_count": len(probabilities),
            "elapsed_seconds": 20.0,
            "within_time_limit": True,
        }
        _write_json(manifest_path, manifest)
        timing_rows.append({
            "case_id": case_id,
            "prediction": decision,
            "report_sha256": report_hash,
            "case_signature": f"sig-{case_id}",
        })
    _write_jsonl(timing_root / "cases.jsonl", timing_rows)
    common = {
        "protocol_root": tmp_path / "protocol",
        "panel_root": tmp_path / "panels",
        "gallery_root": tmp_path / "gallery",
        "review_path": tmp_path / "review.json",
        "config_path": tmp_path / "config.yaml",
        "timing_protocol_path": timing_protocol_path,
        "timing_output_root": timing_root,
    }
    return common, labels_path


def test_score_uses_maximum_positive_panel_probability() -> None:
    score, values = module._score_from_report(
        _report(
            "case",
            "POSITIVA",
            [
                {"POSITIVA": 0.2, "NEGATIVA": 0.7, "INCONCLUSIVA": 0.1},
                {"POSITIVA": 0.8, "NEGATIVA": 0.1, "INCONCLUSIVA": 0.1},
            ],
        )
    )
    assert score == 0.8
    assert values == [0.2, 0.8]


@pytest.mark.parametrize(
    "value",
    [
        {"POSITIVA": 0.5, "NEGATIVA": 0.5},
        {"POSITIVA": 0.8, "NEGATIVA": 0.8, "INCONCLUSIVA": 0.1},
        {"POSITIVA": -0.1, "NEGATIVA": 0.6, "INCONCLUSIVA": 0.5},
    ],
)
def test_invalid_choice_probabilities_are_rejected(value: dict) -> None:
    with pytest.raises(PipelineError):
        module._validate_probability_set(value)


def test_freeze_verify_and_evaluate_penalizes_failures_and_inconclusive(
    tmp_path: Path, monkeypatch
) -> None:
    common, labels_path = _artifacts(tmp_path, monkeypatch)
    evaluation_protocol_path = tmp_path / "evaluation_protocol.json"
    protocol = module.freeze_liver_enriched_evaluation_protocol(
        **common, output_path=evaluation_protocol_path
    )
    assert protocol["labels_opened"] is False
    assert protocol["evaluation_protocol_signature"]

    prediction_root = tmp_path / "predictions"
    frozen = module.freeze_liver_enriched_predictions(
        **common,
        evaluation_protocol_path=evaluation_protocol_path,
        output_root=prediction_root,
    )
    assert frozen["prediction_counts"] == {
        "POSITIVE": 1,
        "NEGATIVE": 1,
        "INCONCLUSIVE": 1,
    }
    verified, rows = module.verify_liver_enriched_predictions(
        **common,
        evaluation_protocol_path=evaluation_protocol_path,
        prediction_root=prediction_root,
    )
    assert verified["case_count"] == 3
    assert rows[0]["score"] == 0.8

    with pytest.raises(PipelineError, match="nao autorizada"):
        module.evaluate_liver_enriched_predictions(
            **common,
            evaluation_protocol_path=evaluation_protocol_path,
            prediction_root=prediction_root,
            protected_labels_path=labels_path,
            output_root=tmp_path / "unauthorized",
        )

    summary = module.evaluate_liver_enriched_predictions(
        **common,
        evaluation_protocol_path=evaluation_protocol_path,
        prediction_root=prediction_root,
        protected_labels_path=labels_path,
        output_root=tmp_path / "evaluation",
        allow_protected_public_labels=True,
    )
    assert summary["confusion_matrix"] == {"tp": 1, "tn": 1, "fp": 1, "fn": 2}
    assert summary["technical_failure_positive_count"] == 1
    assert summary["technical_failure_negative_count"] == 1
    assert summary["inconclusive_count"] == 1
    assert summary["sensitivity"] == pytest.approx(1 / 3)
    assert summary["specificity"] == pytest.approx(1 / 2)
    assert summary["qualified"] is False


def test_prediction_tampering_is_detected_before_labels_are_read(
    tmp_path: Path, monkeypatch
) -> None:
    common, _ = _artifacts(tmp_path, monkeypatch)
    evaluation_protocol_path = tmp_path / "evaluation_protocol.json"
    module.freeze_liver_enriched_evaluation_protocol(
        **common, output_path=evaluation_protocol_path
    )
    prediction_root = tmp_path / "predictions"
    module.freeze_liver_enriched_predictions(
        **common,
        evaluation_protocol_path=evaluation_protocol_path,
        output_root=prediction_root,
    )
    rows = module._jsonl(prediction_root / "predictions.jsonl", "predictions")
    rows[0]["score"] = 0.01
    _write_jsonl(prediction_root / "predictions.jsonl", rows)
    missing_labels = tmp_path / "must_not_be_read.jsonl"
    with pytest.raises(PipelineError, match="predicoes liver-enriched invalido"):
        module.evaluate_liver_enriched_predictions(
            **common,
            evaluation_protocol_path=evaluation_protocol_path,
            prediction_root=prediction_root,
            protected_labels_path=missing_labels,
            output_root=tmp_path / "evaluation",
            allow_protected_public_labels=True,
        )
