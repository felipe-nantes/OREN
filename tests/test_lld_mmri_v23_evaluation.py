from __future__ import annotations

import json
from pathlib import Path

import pytest

from dtwin.benchmark import lld_mmri_v23_evaluation as module
from dtwin.benchmark.lld_mmri_v23_predictions import PREDICTION_SCHEMA, RUN_SCHEMA
from dtwin.benchmark.openswisshcc_alignment import _sha256
from dtwin.benchmark.openswisshcc_v20_fusion import _canonical_sha
from dtwin.core import PipelineError


def _artifacts(tmp_path: Path, monkeypatch):
    case_ids = [f"anon-lld-{index:016d}" for index in range(4)]
    protocol = {
        "case_ids": case_ids,
        "case_count": 4,
        "positive_count": 2,
        "negative_count": 2,
        "target_condition": "hcc_suspicion",
        "protocol_signature": "p" * 64,
        "calibrator_signature": "c" * 64,
    }
    predictions_root = tmp_path / "predictions"
    predictions_root.mkdir()
    decisions = ["POSITIVE", "POSITIVE", "NEGATIVE", "NEGATIVE"]
    scores = [0.9, 0.8, 0.2, 0.1]
    predictions = []
    for case_id, decision, score in zip(case_ids, decisions, scores, strict=True):
        base = {
            "schema": PREDICTION_SCHEMA,
            "case_id": case_id,
            "prediction": decision,
            "score": score,
            "protocol_signature": protocol["protocol_signature"],
            "calibrator_signature": protocol["calibrator_signature"],
            "ground_truth_read": False,
            "metrics_calculated": False,
        }
        row = dict(base)
        row["prediction_signature"] = _canonical_sha(base)
        predictions.append(row)
    predictions_path = predictions_root / "predictions.jsonl"
    predictions_path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in predictions),
        encoding="utf-8",
    )
    summary_base = {
        "schema": RUN_SCHEMA,
        "status": "frozen_complete_predictions_before_labels",
        "protocol_case_count": 4,
        "case_count": 4,
        "case_ids": case_ids,
        "technical_failure_case_count": 0,
        "technical_failure_case_ids": [],
        "technical_failures_excluded_from_inference": True,
        "technical_failures_count_as_primary_metric_errors": True,
        "predictions_sha256": _sha256(predictions_path),
        "protocol_signature": protocol["protocol_signature"],
        "calibrator_signature": protocol["calibrator_signature"],
        "predictions_frozen": True,
        "ground_truth_read": False,
        "metrics_calculated": False,
        "qualified": False,
    }
    summary = dict(summary_base)
    summary["run_signature"] = _canonical_sha(summary_base)
    (predictions_root / "summary.json").write_text(json.dumps(summary), encoding="utf-8")

    labels_path = tmp_path / "labels.jsonl"
    subtypes = ["hcc", "hcc", "fnh", "cyst"]
    labels = []
    for index, (case_id, subtype) in enumerate(zip(case_ids, subtypes, strict=True)):
        labels.append(
            {
                "schema": module.LABEL_SCHEMA,
                "case_id": case_id,
                "label": "POSITIVE" if index < 2 else "NEGATIVE",
                "subtype": subtype,
                "target_condition": "hcc_suspicion",
                "research_only": True,
                "clinical_use_allowed": False,
            }
        )
    labels_path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in labels),
        encoding="utf-8",
    )
    protocol["protected_labels_sha256"] = _sha256(labels_path)
    monkeypatch.setattr(module, "_load_and_validate_protocol", lambda _: (protocol, []))
    return protocol, predictions_root, labels_path, summary


def test_requires_explicit_label_authorization(monkeypatch, tmp_path: Path):
    _, predictions, labels, _ = _artifacts(tmp_path, monkeypatch)
    with pytest.raises(PipelineError, match="nao autorizada"):
        module.evaluate_lld_mmri_v23_after_prediction_freeze(
            protocol_root=tmp_path,
            prediction_root=predictions,
            protected_labels_path=labels,
            output_root=tmp_path / "evaluation",
        )


def test_reports_accuracy_but_does_not_qualify_without_end_to_end_time(monkeypatch, tmp_path: Path):
    _, predictions, labels, _ = _artifacts(tmp_path, monkeypatch)
    result = module.evaluate_lld_mmri_v23_after_prediction_freeze(
        protocol_root=tmp_path,
        prediction_root=predictions,
        protected_labels_path=labels,
        output_root=tmp_path / "evaluation",
        allow_protected_public_labels=True,
    )
    assert result["confusion_matrix"] == {"tp": 2, "tn": 2, "fp": 0, "fn": 0}
    assert result["sensitivity"] == 1.0
    assert result["specificity"] == 1.0
    assert result["roc_auc"] == 1.0
    assert result["roc_auc_available"] is True
    assert result["roc_auc_unavailable_reason"] is None
    assert result["accuracy_gate_75_75_passed"] is True
    assert result["end_to_end_180_second_gate_passed"] is False
    assert result["qualified"] is False
    assert result["lesion_masks_read"] == 0


def test_technical_failure_counts_as_error_without_fabricated_prediction(
    monkeypatch, tmp_path: Path
):
    protocol, predictions_root, labels, _ = _artifacts(tmp_path, monkeypatch)
    predictions_path = predictions_root / "predictions.jsonl"
    rows = [
        json.loads(line)
        for line in predictions_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ][1:]
    predictions_path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )
    summary_path = predictions_root / "summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    summary.pop("run_signature")
    summary.update(
        case_count=3,
        case_ids=protocol["case_ids"][1:],
        technical_failure_case_count=1,
        technical_failure_case_ids=[protocol["case_ids"][0]],
        predictions_sha256=_sha256(predictions_path),
    )
    summary["run_signature"] = _canonical_sha(summary)
    summary_path.write_text(json.dumps(summary), encoding="utf-8")
    result = module.evaluate_lld_mmri_v23_after_prediction_freeze(
        protocol_root=tmp_path,
        prediction_root=predictions_root,
        protected_labels_path=labels,
        output_root=tmp_path / "evaluation",
        allow_protected_public_labels=True,
    )
    assert result["confusion_matrix"] == {"tp": 1, "tn": 2, "fp": 0, "fn": 1}
    assert result["sensitivity"] == 0.5
    assert result["specificity"] == 1.0
    assert result["technical_failure_case_count"] == 1
    assert result["roc_auc_scope"] == "inference_eligible_cases_only"
    case_rows = [
        json.loads(line)
        for line in (tmp_path / "evaluation" / "case_results.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    assert case_rows[0]["prediction"] == "TECHNICAL_FAILURE"
    assert case_rows[0]["score"] is None


def test_auc_is_explicitly_unavailable_when_failures_remove_one_truth_class(
    monkeypatch, tmp_path: Path
):
    protocol, predictions_root, labels, _ = _artifacts(tmp_path, monkeypatch)
    predictions_path = predictions_root / "predictions.jsonl"
    rows = [
        json.loads(line)
        for line in predictions_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ][:2]
    predictions_path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )
    failure_ids = protocol["case_ids"][2:]
    summary_path = predictions_root / "summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    summary.pop("run_signature")
    summary.update(
        case_count=2,
        case_ids=protocol["case_ids"][:2],
        technical_failure_case_count=2,
        technical_failure_case_ids=failure_ids,
        predictions_sha256=_sha256(predictions_path),
    )
    summary["run_signature"] = _canonical_sha(summary)
    summary_path.write_text(json.dumps(summary), encoding="utf-8")

    result = module.evaluate_lld_mmri_v23_after_prediction_freeze(
        protocol_root=tmp_path,
        prediction_root=predictions_root,
        protected_labels_path=labels,
        output_root=tmp_path / "evaluation",
        allow_protected_public_labels=True,
    )
    assert result["roc_auc"] is None
    assert result["roc_auc_available"] is False
    assert result["roc_auc_inference_eligible_positive_count"] == 2
    assert result["roc_auc_inference_eligible_negative_count"] == 0
    assert result["roc_auc_unavailable_reason"] == (
        "one_or_both_truth_classes_absent_after_technical_failure_exclusion"
    )
    assert result["specificity"] == 0.0
    assert result["qualified"] is False


def test_qualifies_only_with_signed_direct_end_to_end_timing(monkeypatch, tmp_path: Path):
    protocol, predictions, labels, prediction_summary = _artifacts(tmp_path, monkeypatch)
    required_stages = [
        "input_validation", "liver_segmentation", "panel_generation",
        "lesion_localizer", "candidate_shape", "medsiglip", "medgemma",
        "fusion_persistence",
    ]
    case_rows = []
    for case_id in protocol["case_ids"]:
        case_base = {
            "schema": "argos-lld-mmri-v23-direct-case-timing-v1",
            "case_id": case_id,
            "runner_id": "argos-lld-mmri-v23-direct-case-runner-v1",
            "elapsed_seconds": 179.0,
            "maximum_seconds": 180.0,
            "within_budget": True,
            "continuous_wall_clock": True,
            "component_sum_only": False,
            "ground_truth_read": False,
            "lesion_masks_read": 0,
            "stages": {name: {"status": "complete"} for name in required_stages},
        }
        case = dict(case_base)
        case["case_timing_signature"] = _canonical_sha(case_base)
        case_rows.append(case)
    cases_path = tmp_path / "cases.jsonl"
    cases_path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in case_rows),
        encoding="utf-8",
    )
    timing_base = {
        "schema": module.TIMING_SCHEMA,
        "status": "complete_measured_end_to_end",
        "protocol_case_count": 4,
        "case_count": 4,
        "case_ids": protocol["case_ids"],
        "technical_failure_case_count": 0,
        "technical_failure_case_ids": [],
        "technical_failures_count_as_primary_metric_errors": True,
        "prediction_run_signature": prediction_summary["run_signature"],
        "runner_id": "argos-lld-mmri-v23-direct-case-runner-v1",
        "required_stages": required_stages,
        "continuous_wall_clock": True,
        "component_sum_only": False,
        "maximum_allowed_seconds": 180.0,
        "all_inference_eligible_cases_within_180_seconds": True,
        "all_cases_within_180_seconds": True,
        "max_end_to_end_seconds": 179.0,
        "all_predictions_exactly_reproduced": True,
        "ground_truth_read": False,
        "lesion_masks_read": 0,
        "cases_sha256": _sha256(cases_path),
    }
    timing = dict(timing_base)
    timing["timing_signature"] = _canonical_sha(timing_base)
    timing_path = tmp_path / "timing.json"
    timing_path.write_text(json.dumps(timing), encoding="utf-8")
    result = module.evaluate_lld_mmri_v23_after_prediction_freeze(
        protocol_root=tmp_path,
        prediction_root=predictions,
        protected_labels_path=labels,
        output_root=tmp_path / "evaluation",
        allow_protected_public_labels=True,
        end_to_end_timing_path=timing_path,
    )
    assert result["qualified"] is True


def test_valid_timing_over_budget_fails_gate_without_invalidating_evidence(
    tmp_path: Path
):
    case_id = "anon-lld-0000000000000000"
    required_stages = [
        "input_validation", "liver_segmentation", "panel_generation",
        "lesion_localizer", "candidate_shape", "medsiglip", "medgemma",
        "fusion_persistence",
    ]
    case_base = {
        "schema": "argos-lld-mmri-v23-direct-case-timing-v1",
        "case_id": case_id,
        "runner_id": "argos-lld-mmri-v23-direct-case-runner-v1",
        "elapsed_seconds": 181.0,
        "maximum_seconds": 180.0,
        "within_budget": False,
        "continuous_wall_clock": True,
        "component_sum_only": False,
        "ground_truth_read": False,
        "lesion_masks_read": 0,
        "stages": {name: {"status": "complete"} for name in required_stages},
    }
    case = dict(case_base)
    case["case_timing_signature"] = _canonical_sha(case_base)
    cases_path = tmp_path / "cases.jsonl"
    cases_path.write_text(json.dumps(case, sort_keys=True) + "\n", encoding="utf-8")
    timing_base = {
        "schema": module.TIMING_SCHEMA,
        "status": "complete_measured_end_to_end",
        "protocol_case_count": 1,
        "case_count": 1,
        "case_ids": [case_id],
        "technical_failure_case_count": 0,
        "technical_failure_case_ids": [],
        "technical_failures_count_as_primary_metric_errors": True,
        "prediction_run_signature": "r" * 64,
        "runner_id": "argos-lld-mmri-v23-direct-case-runner-v1",
        "required_stages": required_stages,
        "continuous_wall_clock": True,
        "component_sum_only": False,
        "maximum_allowed_seconds": 180.0,
        "all_inference_eligible_cases_within_180_seconds": False,
        "all_cases_within_180_seconds": False,
        "max_end_to_end_seconds": 181.0,
        "all_predictions_exactly_reproduced": True,
        "ground_truth_read": False,
        "lesion_masks_read": 0,
        "cases_sha256": _sha256(cases_path),
    }
    timing = dict(timing_base)
    timing["timing_signature"] = _canonical_sha(timing_base)
    timing_path = tmp_path / "summary.json"
    timing_path.write_text(json.dumps(timing), encoding="utf-8")

    passed, evidence = module._timing_gate(
        timing_path,
        case_ids=[case_id],
        protocol_case_count=1,
        technical_failure_case_ids=[],
        prediction_run_signature="r" * 64,
    )
    assert passed is False
    assert evidence["max_end_to_end_seconds"] == 181.0


def test_rejects_prediction_tampering_before_label_parse(monkeypatch, tmp_path: Path):
    _, predictions, labels, _ = _artifacts(tmp_path, monkeypatch)
    (predictions / "predictions.jsonl").write_text("{}\n", encoding="utf-8")
    with pytest.raises(PipelineError, match="congeladas"):
        module.evaluate_lld_mmri_v23_after_prediction_freeze(
            protocol_root=tmp_path,
            prediction_root=predictions,
            protected_labels_path=labels,
            output_root=tmp_path / "evaluation",
            allow_protected_public_labels=True,
        )
