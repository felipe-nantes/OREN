from __future__ import annotations

import json
from pathlib import Path

import pytest

from dtwin.benchmark import public_independent_v21_negative_evaluation as module
from dtwin.benchmark.public_independent_cohort import LABELS_SCHEMA
from dtwin.benchmark.public_independent_v21_calibrator import (
    CALIBRATOR_SCHEMA,
    SCORE_SCHEMA,
    SCORE_SUMMARY_SCHEMA,
    WEIGHTS,
)
from dtwin.core import PipelineError


def _write(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def _fixture(tmp_path: Path, count: int = 4):
    case_ids = [f"anon-public-{index}" for index in range(count)]
    calibrator = {
        "schema": CALIBRATOR_SCHEMA,
        "status": "frozen_for_external_label_blind_scoring",
        "development_case_count": 2, "components": WEIGHTS,
        "reference_values": {name: [0.0, 1.0] for name in WEIGHTS},
        "threshold": 0.5, "holdout_opened": False,
        "ground_truth_available_during_external_scoring": False,
    }
    calibrator["calibrator_signature"] = module._canonical_sha(calibrator)
    calibrator_path = tmp_path / "calibrator.json"
    _write(calibrator_path, calibrator)
    scored = tmp_path / "scores"
    scored.mkdir()
    rows = []
    for index, case_id in enumerate(case_ids):
        rows.append({
            "schema": SCORE_SCHEMA, "case_id": case_id,
            "decision": "NEGATIVE" if index < 3 else "POSITIVE",
            "calibrator_signature": calibrator["calibrator_signature"],
            "total_component_seconds": 20.0 + index,
            "time_gate_180_seconds_passed": True,
            "ground_truth_read": False, "metrics_calculated": False,
            "holdout_opened": False,
        })
    scores_path = scored / "scores.jsonl"
    scores_path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    summary = {
        "schema": SCORE_SUMMARY_SCHEMA,
        "status": "complete_predictions_frozen_labels_still_closed",
        "case_count": count, "case_ids": case_ids,
        "scores_sha256": module._sha256(scores_path),
        "calibrator_sha256": module._sha256(calibrator_path),
        "calibrator_signature": calibrator["calibrator_signature"],
        "ground_truth_read": False, "metrics_calculated": False,
        "holdout_opened": False,
    }
    _write(scored / "summary.json", summary)

    bundle = tmp_path / "bundle"
    labels_path = bundle / "protected_ground_truth/protected_labels.jsonl"
    labels_path.parent.mkdir(parents=True)
    labels = [{
        "schema": LABELS_SCHEMA, "case_id": case_id, "label": "negative",
        "dataset_id": "chaos_mri", "target_condition": "focal_liver_lesion_suspicion",
        "research_only": True, "clinical_use_allowed": False,
    } for case_id in case_ids]
    labels.append({
        "schema": LABELS_SCHEMA, "case_id": "anon-public-positive-extra",
        "label": "positive", "dataset_id": "liverhccseg",
        "target_condition": "focal_liver_lesion_suspicion",
        "research_only": True, "clinical_use_allowed": False,
    })
    labels_path.write_text("".join(json.dumps(row) + "\n" for row in labels), encoding="utf-8")
    public_protocol = {
        "schema": module.PUBLIC_PROTOCOL_SCHEMA,
        "cohort_id": "public", "case_count": len(labels),
        "protected_labels_sha256": module._sha256(labels_path),
        "ground_truth_read_during_inference": False, "holdout_opened": False,
    }
    public_protocol["protocol_signature"] = module._public_canonical_hash(public_protocol)
    _write(bundle / "cohort_protocol.json", public_protocol)
    prepared = {
        "schema": module.PREPARED_COHORT_SCHEMA, "case_count": count,
        "cases": [{"case_id": case_id} for case_id in case_ids],
        "lesion_masks_copied": False, "pathology_labels_copied": False,
        "ground_truth_class_read": False, "combined_primary_metric_allowed": False,
        "holdout_opened": False,
        "source_public_protocol_signature": public_protocol["protocol_signature"],
    }
    prepared_root = tmp_path / "prepared"
    _write(prepared_root / "cohort_manifest.json", prepared)
    return scored, calibrator_path, prepared_root, bundle, labels_path


def test_negative_evaluation_requires_explicit_ground_truth_authorization(tmp_path: Path):
    with pytest.raises(PipelineError, match="nao foi autorizada"):
        module.evaluate_chaos_v21_negative_arm(
            scored_root=tmp_path / "scores", calibrator_path=tmp_path / "calibrator.json",
            prepared_root=tmp_path / "prepared", public_bundle_root=tmp_path / "bundle",
            protocol_path=tmp_path / "protocol.json", authorized_protocol_signature="x",
            output_dir=tmp_path / "out", allow_protected_public_ground_truth=False,
        )


def test_negative_only_evaluation_reports_specificity_but_not_sensitivity(tmp_path: Path):
    scored, calibrator, prepared, bundle, _labels = _fixture(tmp_path)
    protocol_path = tmp_path / "protocol.json"
    protocol = module.freeze_chaos_v21_evaluation_protocol(
        scored_root=scored, calibrator_path=calibrator, prepared_root=prepared,
        public_bundle_root=bundle, output_path=protocol_path, expected_case_count=4,
    )
    result = module.evaluate_chaos_v21_negative_arm(
        scored_root=scored, calibrator_path=calibrator, prepared_root=prepared,
        public_bundle_root=bundle, protocol_path=protocol_path,
        authorized_protocol_signature=protocol["protocol_signature"],
        output_dir=tmp_path / "out", allow_protected_public_ground_truth=True,
        expected_case_count=4,
    )
    assert result["specificity"] == 0.75
    assert result["specificity_gate_75_passed"] is True
    assert result["sensitivity"] is None
    assert result["combined_primary_metric_allowed"] is False
    assert result["qualified"] is False
    assert result["time_gate_180_seconds_passed"] is True
    assert result["holdout_opened"] is False


def test_protocol_freeze_hashes_but_does_not_parse_protected_labels(tmp_path: Path):
    scored, calibrator, prepared, bundle, labels = _fixture(tmp_path)
    labels.write_text("not-json-and-still-protected\n", encoding="utf-8")
    public = json.loads((bundle / "cohort_protocol.json").read_text())
    public["protected_labels_sha256"] = module._sha256(labels)
    public.pop("protocol_signature")
    public["protocol_signature"] = module._public_canonical_hash(public)
    _write(bundle / "cohort_protocol.json", public)
    prepared_payload = json.loads((prepared / "cohort_manifest.json").read_text())
    prepared_payload["source_public_protocol_signature"] = public["protocol_signature"]
    _write(prepared / "cohort_manifest.json", prepared_payload)
    protocol = module.freeze_chaos_v21_evaluation_protocol(
        scored_root=scored, calibrator_path=calibrator, prepared_root=prepared,
        public_bundle_root=bundle, output_path=tmp_path / "protocol.json",
        expected_case_count=4,
    )
    assert protocol["protected_labels_sha256"] == module._sha256(labels)


def test_negative_evaluation_rejects_unapproved_signature(tmp_path: Path):
    scored, calibrator, prepared, bundle, _labels = _fixture(tmp_path)
    protocol_path = tmp_path / "protocol.json"
    module.freeze_chaos_v21_evaluation_protocol(
        scored_root=scored, calibrator_path=calibrator, prepared_root=prepared,
        public_bundle_root=bundle, output_path=protocol_path, expected_case_count=4,
    )
    with pytest.raises(PipelineError, match="nao autorizado"):
        module.evaluate_chaos_v21_negative_arm(
            scored_root=scored, calibrator_path=calibrator, prepared_root=prepared,
            public_bundle_root=bundle, protocol_path=protocol_path,
            authorized_protocol_signature="0" * 64, output_dir=tmp_path / "out",
            allow_protected_public_ground_truth=True, expected_case_count=4,
        )


def test_negative_evaluation_rejects_non_negative_selected_label(tmp_path: Path):
    scored, calibrator, prepared, bundle, labels = _fixture(tmp_path)
    protocol_path = tmp_path / "protocol.json"
    protocol = module.freeze_chaos_v21_evaluation_protocol(
        scored_root=scored, calibrator_path=calibrator, prepared_root=prepared,
        public_bundle_root=bundle, output_path=protocol_path, expected_case_count=4,
    )
    rows = [json.loads(line) for line in labels.read_text().splitlines()]
    rows[0]["label"] = "positive"
    labels.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    with pytest.raises(PipelineError, match="protegido|publico"):
        module.evaluate_chaos_v21_negative_arm(
            scored_root=scored, calibrator_path=calibrator, prepared_root=prepared,
            public_bundle_root=bundle, protocol_path=protocol_path,
            authorized_protocol_signature=protocol["protocol_signature"],
            output_dir=tmp_path / "out", allow_protected_public_ground_truth=True,
            expected_case_count=4,
        )
