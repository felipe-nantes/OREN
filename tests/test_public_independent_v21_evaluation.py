import json
from pathlib import Path

import pytest

from dtwin.benchmark import public_independent_v21_evaluation as module
from dtwin.benchmark.public_independent_v21_calibrator import (
    CALIBRATOR_SCHEMA,
    SCORE_SCHEMA,
    SCORE_SUMMARY_SCHEMA,
    WEIGHTS,
    _canonical_sha,
)
from dtwin.core import PipelineError
from dtwin.datasets.liverhccseg_labels import AUDIT_SCHEMA


def _write(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def _fixture(tmp_path: Path):
    count = 4
    case_ids = [f"anon-public-{index}" for index in range(count)]
    calibrator = {
        "schema": CALIBRATOR_SCHEMA, "status": "frozen_for_external_label_blind_scoring",
        "development_case_count": 2, "components": WEIGHTS,
        "reference_values": {name: [0.0, 1.0] for name in WEIGHTS}, "threshold": 0.5,
        "holdout_opened": False, "ground_truth_available_during_external_scoring": False,
    }
    calibrator["calibrator_signature"] = _canonical_sha(calibrator)
    calibrator_path = tmp_path / "calibrator.json"
    _write(calibrator_path, calibrator)
    scores_root = tmp_path / "scores"
    scores_root.mkdir()
    rows = []
    for index, case_id in enumerate(case_ids):
        rows.append({
            "schema": SCORE_SCHEMA, "case_id": case_id,
            "decision": "POSITIVE" if index < 3 else "NEGATIVE",
            "calibrator_signature": calibrator["calibrator_signature"],
            "total_component_seconds": 20.0 + index,
            "time_gate_180_seconds_passed": True,
            "ground_truth_read": False, "metrics_calculated": False, "holdout_opened": False,
        })
    scores_path = scores_root / "scores.jsonl"
    scores_path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    summary = {
        "schema": SCORE_SUMMARY_SCHEMA, "status": "complete_predictions_frozen_labels_still_closed",
        "case_count": count, "case_ids": case_ids, "scores_sha256": module._sha256(scores_path),
        "calibrator_sha256": module._sha256(calibrator_path),
        "calibrator_signature": calibrator["calibrator_signature"],
        "ground_truth_read": False, "metrics_calculated": False, "holdout_opened": False,
    }
    _write(scores_root / "summary.json", summary)
    audit = {
        "schema": AUDIT_SCHEMA, "status": "tumor_positive_registry_filtered",
        "included_tumor_subject_count": count, "excluded_subjects_not_assumed_negative": True,
        "ground_truth_available_to_inference": False, "research_only": True,
        "clinical_use_allowed": False,
    }
    audit_path = tmp_path / "protected/audit.json"
    _write(audit_path, audit)
    prepared = {
        "schema": module.PREPARED_COHORT_SCHEMA, "case_count": count,
        "cases": [{"case_id": case_id} for case_id in case_ids],
        "lesion_masks_copied": False, "pathology_labels_copied": False,
        "holdout_opened": False, "selection_audit_sha256": module._sha256(audit_path),
    }
    prepared_root = tmp_path / "prepared"
    _write(prepared_root / "cohort_manifest.json", prepared)
    return scores_root, calibrator_path, prepared_root, audit_path


def test_positive_evaluation_requires_explicit_ground_truth_authorization(tmp_path: Path):
    with pytest.raises(PipelineError, match="nao foi autorizada"):
        module.evaluate_liverhccseg_v21_positive_arm(
            scored_root=tmp_path / "scores", calibrator_path=tmp_path / "calibrator.json",
            prepared_root=tmp_path / "prepared", protected_selection_audit_path=tmp_path / "audit.json",
            protocol_path=tmp_path / "protocol.json", authorized_protocol_signature="x",
            output_dir=tmp_path / "out", allow_protected_public_ground_truth=False,
        )
    assert not (tmp_path / "out").exists()


def test_positive_only_evaluation_reports_sensitivity_but_not_specificity(tmp_path: Path):
    scores, calibrator, prepared, audit = _fixture(tmp_path)
    protocol_path = tmp_path / "protocol.json"
    protocol = module.freeze_liverhccseg_v21_evaluation_protocol(
        scored_root=scores, calibrator_path=calibrator, prepared_root=prepared,
        output_path=protocol_path, expected_case_count=4,
    )
    result = module.evaluate_liverhccseg_v21_positive_arm(
        scored_root=scores, calibrator_path=calibrator, prepared_root=prepared,
        protocol_path=protocol_path, authorized_protocol_signature=protocol["protocol_signature"],
        protected_selection_audit_path=audit, output_dir=tmp_path / "out",
        allow_protected_public_ground_truth=True, expected_case_count=4,
    )
    assert result["sensitivity"] == 0.75
    assert result["sensitivity_gate_75_passed"] is True
    assert result["specificity"] is None
    assert result["simultaneous_75_75_gate_evaluated"] is False
    assert result["qualified"] is False
    assert result["time_gate_180_seconds_passed"] is True
    assert result["holdout_opened"] is False
    assert (tmp_path / "out/report.md").is_file()


def test_positive_evaluation_rejects_changed_protected_audit(tmp_path: Path):
    scores, calibrator, prepared, audit = _fixture(tmp_path)
    protocol_path = tmp_path / "protocol.json"
    protocol = module.freeze_liverhccseg_v21_evaluation_protocol(
        scored_root=scores, calibrator_path=calibrator, prepared_root=prepared,
        output_path=protocol_path, expected_case_count=4,
    )
    value = json.loads(audit.read_text())
    value["included_tumor_subject_count"] = 3
    _write(audit, value)
    with pytest.raises(PipelineError, match="nao comprova"):
        module.evaluate_liverhccseg_v21_positive_arm(
            scored_root=scores, calibrator_path=calibrator, prepared_root=prepared,
            protocol_path=protocol_path, authorized_protocol_signature=protocol["protocol_signature"],
            protected_selection_audit_path=audit, output_dir=tmp_path / "out",
            allow_protected_public_ground_truth=True, expected_case_count=4,
        )
    assert not (tmp_path / "out").exists()


def test_protocol_freeze_does_not_read_protected_audit(tmp_path: Path):
    scores, calibrator, prepared, audit = _fixture(tmp_path)
    audit.unlink()
    protocol = module.freeze_liverhccseg_v21_evaluation_protocol(
        scored_root=scores, calibrator_path=calibrator, prepared_root=prepared,
        output_path=tmp_path / "protocol.json", expected_case_count=4,
    )
    assert protocol["protected_selection_audit_sha256"]
    assert protocol["protocol_signature"] == module._canonical_sha(
        {key: value for key, value in protocol.items() if key != "protocol_signature"}
    )


def test_positive_evaluation_rejects_signature_not_explicitly_authorized(tmp_path: Path):
    scores, calibrator, prepared, audit = _fixture(tmp_path)
    protocol_path = tmp_path / "protocol.json"
    module.freeze_liverhccseg_v21_evaluation_protocol(
        scored_root=scores, calibrator_path=calibrator, prepared_root=prepared,
        output_path=protocol_path, expected_case_count=4,
    )
    with pytest.raises(PipelineError, match="nao autorizado"):
        module.evaluate_liverhccseg_v21_positive_arm(
            scored_root=scores, calibrator_path=calibrator, prepared_root=prepared,
            protocol_path=protocol_path, authorized_protocol_signature="0" * 64,
            protected_selection_audit_path=audit, output_dir=tmp_path / "out",
            allow_protected_public_ground_truth=True, expected_case_count=4,
        )
    assert not (tmp_path / "out").exists()
