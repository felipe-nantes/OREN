from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from dtwin.benchmark import openswisshcc_holdout_evaluation as module
from dtwin.benchmark.openswisshcc import anonymized_case_id
from dtwin.benchmark.openswisshcc_alignment import _sha256
from dtwin.benchmark.openswisshcc_holdout_signals import (
    EXPECTED_CALIBRATOR_SIGNATURE,
    RAW_SIGNAL_SUMMARY_SCHEMA,
    freeze_holdout_v21_predictions,
)
from dtwin.benchmark.public_independent_v21_calibrator import (
    SCORE_SCHEMA,
    SCORE_SUMMARY_SCHEMA,
)
from dtwin.core import PipelineError


def _write(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True), encoding="utf-8")


def _write_participants(path: Path) -> None:
    with path.open("w", encoding="utf-8", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=["ID", "HCC"], delimiter="\t")
        writer.writeheader()
        for number in range(1, 133):
            truth_positive = number <= 39 or 48 <= number <= 71
            writer.writerow(
                {"ID": f"sub-{number:03d}", "HCC": "1" if truth_positive else ""}
            )


def _blind_freeze(tmp_path: Path, *, slow_case: bool = False):
    subjects = [f"sub-{number:03d}" for number in range(45, 89)]
    case_ids = [anonymized_case_id(subject) for subject in subjects]
    calibrator = tmp_path / "calibrator.json"
    calibrator.write_text("frozen", encoding="utf-8")
    context = {
        "case_ids": case_ids,
        "review_signature": "r" * 64,
        "calibrator_path": calibrator,
        "calibrator": {"decision_rule": "frozen rule", "threshold": 0.5},
    }
    raw = tmp_path / "raw"
    raw.mkdir()
    raw_signals = raw / "raw_signals.jsonl"
    raw_signals.write_text(
        "".join(json.dumps({"case_id": case_id}) + "\n" for case_id in case_ids),
        encoding="utf-8",
    )
    _write(
        raw / "summary.json",
        {
            "schema": RAW_SIGNAL_SUMMARY_SCHEMA,
            "status": "complete_raw_signals_no_labels_no_decision",
            "case_ids": case_ids,
            "review_signature": context["review_signature"],
            "ground_truth_read": False,
        },
    )
    scores = tmp_path / "scores"
    scores.mkdir()
    rows = []
    for index, (subject, case_id) in enumerate(zip(subjects, case_ids, strict=True)):
        subject_number = int(subject[-3:])
        truth_positive = 48 <= subject_number <= 71
        positive_index = subject_number - 48 if truth_positive else None
        negative_index = (
            subject_number - 45 if subject_number <= 47 else subject_number - 69
        ) if not truth_positive else None
        decision = (
            "POSITIVE"
            if (truth_positive and positive_index < 19)
            or (not truth_positive and negative_index < 5)
            else "NEGATIVE"
        )
        elapsed = 181.0 if slow_case and index == 0 else 100.0
        rows.append(
            {
                "schema": SCORE_SCHEMA,
                "case_id": case_id,
                "weighted_ecdf_score": 0.9 if truth_positive else 0.1,
                "decision": decision,
                "calibrator_signature": EXPECTED_CALIBRATOR_SIGNATURE,
                "total_component_seconds": elapsed,
                "time_gate_180_seconds_passed": elapsed <= 180.0,
                "ground_truth_read": False,
                "metrics_calculated": False,
                "holdout_opened": False,
                "research_only": True,
                "clinical_use_allowed": False,
            }
        )
    scores_path = scores / "scores.jsonl"
    scores_path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows), encoding="utf-8"
    )
    _write(
        scores / "summary.json",
        {
            "schema": SCORE_SUMMARY_SCHEMA,
            "status": "complete_predictions_frozen_labels_still_closed",
            "case_count": 44,
            "case_ids": case_ids,
            "scores_sha256": _sha256(scores_path),
            "source_signals_sha256": _sha256(raw_signals),
            "calibrator_sha256": _sha256(calibrator),
            "calibrator_signature": EXPECTED_CALIBRATOR_SIGNATURE,
            "positive_prediction_count": sum(row["decision"] == "POSITIVE" for row in rows),
            "negative_prediction_count": sum(row["decision"] == "NEGATIVE" for row in rows),
            "all_time_gates_passed": all(row["time_gate_180_seconds_passed"] for row in rows),
            "ground_truth_read": False,
            "metrics_calculated": False,
            "holdout_opened": False,
        },
    )
    freeze_path = tmp_path / "freeze.json"
    freeze = freeze_holdout_v21_predictions(
        context=context,
        raw_signal_root=raw,
        score_root=scores,
        output_path=freeze_path,
    )
    participants = tmp_path / "participants.tsv"
    _write_participants(participants)
    provenance = tmp_path / "source_map.jsonl"
    provenance.write_text(
        "".join(
            json.dumps({"case_id": case_id, "public_subject_id": subject, "role": "t1_venous"})
            + "\n"
            for subject, case_id in zip(subjects, case_ids, strict=True)
        ),
        encoding="utf-8",
    )
    return context, raw, scores, freeze_path, freeze, participants, provenance


def test_labels_cannot_open_without_explicit_authorization(tmp_path: Path, monkeypatch):
    context, raw, scores, freeze_path, freeze, participants, provenance = _blind_freeze(tmp_path)
    called = False

    def forbidden(_path):
        nonlocal called
        called = True
        raise AssertionError("participants should stay closed")

    monkeypatch.setattr(module, "load_subject_labels", forbidden)
    with pytest.raises(PipelineError, match="nao foi autorizada"):
        module.materialize_holdout_v21_labels_after_freeze(
            context=context,
            raw_signal_root=raw,
            score_root=scores,
            freeze_path=freeze_path,
            authorized_protocol_signature=freeze["protocol_signature"],
            participants_path=participants,
            protected_provenance_path=provenance,
            output_dir=tmp_path / "labels",
            allow_protected_holdout_labels=False,
        )
    assert called is False


def test_materialized_labels_are_bound_to_frozen_predictions(tmp_path: Path):
    context, raw, scores, freeze_path, freeze, participants, provenance = _blind_freeze(tmp_path)
    result = module.materialize_holdout_v21_labels_after_freeze(
        context=context,
        raw_signal_root=raw,
        score_root=scores,
        freeze_path=freeze_path,
        authorized_protocol_signature=freeze["protocol_signature"],
        participants_path=participants,
        protected_provenance_path=provenance,
        output_dir=tmp_path / "labels",
        allow_protected_holdout_labels=True,
    )
    assert result["positive_count"] == 24
    assert result["negative_count"] == 20
    assert result["prediction_protocol_signature"] == freeze["protocol_signature"]
    assert result["lesion_masks_read"] == 0


def test_same_domain_evaluation_reports_all_required_metrics(tmp_path: Path):
    context, raw, scores, freeze_path, freeze, participants, provenance = _blind_freeze(tmp_path)
    labels = tmp_path / "labels"
    module.materialize_holdout_v21_labels_after_freeze(
        context=context,
        raw_signal_root=raw,
        score_root=scores,
        freeze_path=freeze_path,
        authorized_protocol_signature=freeze["protocol_signature"],
        participants_path=participants,
        protected_provenance_path=provenance,
        output_dir=labels,
        allow_protected_holdout_labels=True,
    )
    result = module.evaluate_holdout_v21_same_domain(
        context=context,
        raw_signal_root=raw,
        score_root=scores,
        freeze_path=freeze_path,
        authorized_protocol_signature=freeze["protocol_signature"],
        protected_label_bundle_root=labels,
        output_dir=tmp_path / "evaluation",
        allow_protected_holdout_labels=True,
    )
    assert result["confusion_matrix"] == {"tp": 19, "tn": 15, "fp": 5, "fn": 5}
    assert result["sensitivity"] == pytest.approx(19 / 24)
    assert result["specificity"] == pytest.approx(15 / 20)
    assert result["roc_auc"] == 1.0
    assert result["gates"]["qualified"] is True
    assert result["lesion_masks_read"] == 0
    assert (tmp_path / "evaluation" / "report.md").is_file()


def test_same_domain_time_gate_fails_above_180_seconds(tmp_path: Path):
    context, raw, scores, freeze_path, freeze, participants, provenance = _blind_freeze(
        tmp_path, slow_case=True
    )
    labels = tmp_path / "labels"
    module.materialize_holdout_v21_labels_after_freeze(
        context=context,
        raw_signal_root=raw,
        score_root=scores,
        freeze_path=freeze_path,
        authorized_protocol_signature=freeze["protocol_signature"],
        participants_path=participants,
        protected_provenance_path=provenance,
        output_dir=labels,
        allow_protected_holdout_labels=True,
    )
    result = module.evaluate_holdout_v21_same_domain(
        context=context,
        raw_signal_root=raw,
        score_root=scores,
        freeze_path=freeze_path,
        authorized_protocol_signature=freeze["protocol_signature"],
        protected_label_bundle_root=labels,
        output_dir=tmp_path / "evaluation",
        allow_protected_holdout_labels=True,
    )
    assert result["gates"]["sensitivity_passed"] is True
    assert result["gates"]["specificity_passed"] is True
    assert result["gates"]["time_passed"] is False
    assert result["qualified"] is False


def test_evaluation_rejects_tampered_protected_label_bundle(tmp_path: Path):
    context, raw, scores, freeze_path, freeze, participants, provenance = _blind_freeze(tmp_path)
    labels = tmp_path / "labels"
    module.materialize_holdout_v21_labels_after_freeze(
        context=context,
        raw_signal_root=raw,
        score_root=scores,
        freeze_path=freeze_path,
        authorized_protocol_signature=freeze["protocol_signature"],
        participants_path=participants,
        protected_provenance_path=provenance,
        output_dir=labels,
        allow_protected_holdout_labels=True,
    )
    with (labels / "holdout_labels.jsonl").open("a", encoding="utf-8") as output:
        output.write("{}\n")
    with pytest.raises(PipelineError, match="adulterado"):
        module.evaluate_holdout_v21_same_domain(
            context=context,
            raw_signal_root=raw,
            score_root=scores,
            freeze_path=freeze_path,
            authorized_protocol_signature=freeze["protocol_signature"],
            protected_label_bundle_root=labels,
            output_dir=tmp_path / "evaluation",
            allow_protected_holdout_labels=True,
        )


def test_wrong_authorized_signature_cannot_open_labels(tmp_path: Path):
    context, raw, scores, freeze_path, _freeze, participants, provenance = _blind_freeze(tmp_path)
    with pytest.raises(PipelineError, match="Assinatura autorizada"):
        module.materialize_holdout_v21_labels_after_freeze(
            context=context,
            raw_signal_root=raw,
            score_root=scores,
            freeze_path=freeze_path,
            authorized_protocol_signature="0" * 64,
            participants_path=participants,
            protected_provenance_path=provenance,
            output_dir=tmp_path / "labels",
            allow_protected_holdout_labels=True,
        )


def test_auc_handles_ties_deterministically():
    assert module._auc([0.5, 0.7], [0.5, 0.4]) == pytest.approx(0.875)
