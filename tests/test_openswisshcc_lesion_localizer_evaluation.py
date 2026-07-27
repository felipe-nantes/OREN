import json
from pathlib import Path

import pytest

from dtwin.benchmark import openswisshcc_lesion_localizer_evaluation as evaluation
from dtwin.benchmark.openswisshcc_lesion_localizer import CASE_SCHEMA, TASK
from dtwin.benchmark.openswisshcc_lesion_localizer_chunks import MERGED_RUN_SCHEMA
from dtwin.core import PipelineError


def _run(tmp_path: Path, count: int = 4) -> Path:
    root = tmp_path / "run"
    root.mkdir()
    case_ids = [f"anon-{index}" for index in range(count)]
    for index, case_id in enumerate(case_ids):
        case = root / case_id
        case.mkdir()
        manifest = {
            "schema": CASE_SCHEMA,
            "case_id": case_id,
            "status": "candidate_scores_only_no_decision",
            "task": TASK,
            "model_version": "test-model",
            "within_90_seconds": True,
            "features": {"total_candidate_volume_mm3": float(index * 10)},
            "ground_truth_lesion_mask_used": False,
            "ground_truth_read": False,
            "metrics_calculated": False,
            "final_decision": None,
        }
        (case / "localizer_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    summary = {
        "schema": MERGED_RUN_SCHEMA,
        "status": "complete_scores_only_no_decision",
        "case_count": count,
        "case_ids": case_ids,
        "task": TASK,
        "model_version": "test-model",
        "selection_signature": "selection",
        "all_cases_within_90_seconds": True,
        "ground_truth_lesion_mask_used": False,
        "ground_truth_read": False,
        "metrics_calculated": False,
        "final_decision": None,
        "research_only": True,
        "clinical_use_allowed": False,
    }
    (root / "summary.json").write_text(json.dumps(summary), encoding="utf-8")
    return root


def _labels(tmp_path: Path, labels: list[str]) -> Path:
    root = tmp_path / "protected_ground_truth"
    root.mkdir()
    path = root / "development_labels.jsonl"
    rows = []
    for index, label in enumerate(labels):
        rows.append({
            "schema": "argos-openswisshcc-ground-truth-v1",
            "case_id": f"anon-{index}",
            "public_subject_id": str(index),
            "label": label,
            "target_condition": "hcc_presence",
            "label_basis": "public",
            "review_status": "reviewed",
        })
    path.write_text("\n".join(json.dumps(row) for row in rows), encoding="utf-8")
    return path


def test_protocol_freezes_one_feature_before_labels(tmp_path):
    run = _run(tmp_path)
    path = tmp_path / "protocol.json"
    protocol = evaluation.create_evaluation_protocol(run_root=run, output_path=path, expected_case_count=4)
    assert protocol["primary_feature"] == evaluation.PRIMARY_FEATURE
    assert protocol["ground_truth_read"] is False
    assert protocol["metrics_calculated"] is False
    assert len(protocol["protocol_signature"]) == 64


def test_evaluation_aborts_before_label_loader_without_explicit_authorization(tmp_path, monkeypatch):
    run = _run(tmp_path)
    protocol_path = tmp_path / "protocol.json"
    evaluation.create_evaluation_protocol(run_root=run, output_path=protocol_path, expected_case_count=4)
    called = False

    def forbidden(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("labels must not be read")

    monkeypatch.setattr(evaluation, "_load_development_labels", forbidden)
    with pytest.raises(PipelineError, match="nao foi autorizada"):
        evaluation.evaluate_full_development(
            run_root=run,
            protocol_path=protocol_path,
            labels_path=tmp_path / "any",
            output_dir=tmp_path / "out",
            expected_case_count=4,
        )
    assert called is False


def test_tampered_run_is_rejected_by_frozen_protocol(tmp_path):
    run = _run(tmp_path)
    protocol_path = tmp_path / "protocol.json"
    evaluation.create_evaluation_protocol(run_root=run, output_path=protocol_path, expected_case_count=4)
    manifest_path = run / "anon-0" / "localizer_manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["features"]["total_candidate_volume_mm3"] = 999
    manifest_path.write_text(json.dumps(manifest))
    with pytest.raises(PipelineError, match="divergiu"):
        evaluation.verify_evaluation_protocol(run_root=run, protocol_path=protocol_path, expected_case_count=4)


def test_authorized_development_evaluation_is_atomic_and_never_qualified(tmp_path):
    run = _run(tmp_path)
    protocol_path = tmp_path / "protocol.json"
    evaluation.create_evaluation_protocol(run_root=run, output_path=protocol_path, expected_case_count=4)
    labels = _labels(tmp_path, ["NEGATIVE", "NEGATIVE", "POSITIVE", "POSITIVE"])
    out = tmp_path / "evaluation"
    result = evaluation.evaluate_full_development(
        run_root=run,
        protocol_path=protocol_path,
        labels_path=labels,
        output_dir=out,
        allow_protected_development_labels=True,
        expected_case_count=4,
    )
    assert result["holdout_opened"] is False
    assert result["qualified"] is False
    assert result["ground_truth_read"] is True
    assert (out / "evaluation.json").is_file()
    assert (out / "case_features.csv").is_file()
