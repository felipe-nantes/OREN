import hashlib
import json
from pathlib import Path

import pytest

from dtwin.benchmark import openswisshcc_v11_fusion as fusion
from dtwin.benchmark.openswisshcc_lesion_localizer import CASE_SCHEMA, TASK
from dtwin.benchmark.openswisshcc_lesion_localizer_chunks import MERGED_RUN_SCHEMA
from dtwin.core import PipelineError


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _sources(tmp_path: Path, count: int = 10):
    case_ids = [f"anon-{index:02d}" for index in range(count)]
    excluded = fusion.EXCLUDED_TECHNICAL_CASE

    localizer = tmp_path / "v10"
    localizer.mkdir()
    for index, case_id in enumerate(case_ids):
        case = localizer / case_id
        case.mkdir()
        manifest = {
            "schema": CASE_SCHEMA,
            "case_id": case_id,
            "status": "candidate_scores_only_no_decision",
            "task": TASK,
            "model_version": "test-localizer",
            "within_90_seconds": True,
            "features": {"total_candidate_volume_mm3": float(index * 10)},
            "ground_truth_lesion_mask_used": False,
            "ground_truth_read": False,
            "metrics_calculated": False,
            "final_decision": None,
        }
        (case / "localizer_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    localizer_summary = {
        "schema": MERGED_RUN_SCHEMA,
        "status": "complete_scores_only_no_decision",
        "case_count": count,
        "case_ids": case_ids,
        "task": TASK,
        "model_version": "test-localizer",
        "selection_signature": "test-selection",
        "all_cases_within_90_seconds": True,
        "max_case_seconds": 5.0,
        "ground_truth_lesion_mask_used": False,
        "ground_truth_read": False,
        "metrics_calculated": False,
        "final_decision": None,
        "research_only": True,
        "clinical_use_allowed": False,
    }
    (localizer / "summary.json").write_text(json.dumps(localizer_summary), encoding="utf-8")

    v4 = tmp_path / "v4"
    v5 = tmp_path / "v5"
    v4.mkdir()
    v5.mkdir()
    panel_sha = "a" * 64
    v4_rows, v5_rows = [], []
    for index, case_id in enumerate([*case_ids, excluded]):
        negative = 0.45 - 0.02 * index
        inconclusive = 0.25 + 0.02 * index
        v4_rows.append({
            "schema": "argos-openswisshcc-choice-score-v1",
            "case_id": case_id,
            "choice_probabilities": {
                "NEGATIVA": negative,
                "INCONCLUSIVA": inconclusive,
                "POSITIVA": 0.30,
            },
            "panel_sha256": panel_sha,
            "elapsed_seconds": 2.0 + index / 10,
            "ground_truth_read": False,
            "research_only": True,
            "clinical_use_allowed": False,
        })
        probabilities = [0.5] * 10 + [0.90 - 0.05 * index]
        v5_rows.append({
            "schema": "argos-openswisshcc-medsiglip-score-v1",
            "case_id": case_id,
            "panel_sha256": panel_sha,
            "elapsed_seconds": 1.0 + index / 10,
            "ground_truth_read": False,
            "research_only": True,
            "clinical_use_allowed": False,
            "score": {
                "scores": [{"positive_probability": value} for value in probabilities],
                "view_order": [*[f"axial_{i:02d}" for i in range(1, 10)], "coronal", "sagittal"],
                "final_decision": None,
                "research_only": True,
                "clinical_use_allowed": False,
            },
        })
    v4_scores = v4 / "scores.jsonl"
    v5_scores = v5 / "scores.jsonl"
    v4_scores.write_text("".join(json.dumps(row) + "\n" for row in v4_rows), encoding="utf-8")
    v5_scores.write_text("".join(json.dumps(row) + "\n" for row in v5_rows), encoding="utf-8")
    (v4 / "summary.json").write_text(json.dumps({
        "schema": "argos-openswisshcc-choice-score-batch-v1",
        "case_count": count + 1,
        "scores_sha256": _sha(v4_scores),
        "ground_truth_read": False,
        "metrics_calculated": False,
        "research_only": True,
        "clinical_use_allowed": False,
    }), encoding="utf-8")
    (v5 / "summary.json").write_text(json.dumps({
        "schema": "argos-openswisshcc-medsiglip-score-batch-v1",
        "case_count": count + 1,
        "scores_sha256": _sha(v5_scores),
        "ground_truth_read": False,
        "metrics_calculated": False,
        "final_decision": None,
        "research_only": True,
        "clinical_use_allowed": False,
    }), encoding="utf-8")
    return v4, v5, localizer, case_ids


def _bundle_and_protocol(tmp_path: Path, count: int = 10):
    v4, v5, v10, case_ids = _sources(tmp_path, count=count)
    bundle = tmp_path / "bundle"
    summary = fusion.build_blind_signal_bundle(
        medgemma_v4_root=v4,
        medsiglip_v5_root=v5,
        localizer_v10_root=v10,
        output_dir=bundle,
        expected_case_count=count,
    )
    protocol_path = tmp_path / "protocol.json"
    protocol = fusion.create_fusion_protocol(
        bundle_root=bundle, output_path=protocol_path, expected_case_count=count
    )
    return bundle, protocol_path, summary, protocol, case_ids


def _labels(tmp_path: Path, case_ids: list[str]) -> Path:
    root = tmp_path / "protected_ground_truth"
    root.mkdir()
    path = root / "development_labels.jsonl"
    midpoint = len(case_ids) // 2
    rows = [{
        "schema": "argos-openswisshcc-ground-truth-v1",
        "case_id": case_id,
        "public_subject_id": str(index),
        "label": "NEGATIVE" if index < midpoint else "POSITIVE",
        "target_condition": "hcc_presence",
        "label_basis": "public",
        "review_status": "reviewed",
    } for index, case_id in enumerate(case_ids)]
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    return path


def test_blind_bundle_has_three_signals_no_decision_and_conservative_time(tmp_path):
    bundle, _, summary, _, _ = _bundle_and_protocol(tmp_path)
    rows = [json.loads(line) for line in (bundle / "signals.jsonl").read_text().splitlines()]
    assert summary["status"] == "complete_blind_signals_no_decision"
    assert summary["time_gate_180_seconds_passed"] is True
    assert summary["conservative_sum_of_component_max_seconds"] < 180
    assert summary["ground_truth_read"] is False
    assert summary["holdout_opened"] is False
    assert list(rows[0]["signals"]) == list(fusion.WEIGHTS)
    assert "label" not in rows[0]
    assert rows[0]["final_decision"] is None


def test_protocol_freezes_one_primary_fusion_and_fixed_weights(tmp_path):
    _, _, _, protocol, _ = _bundle_and_protocol(tmp_path)
    assert protocol["single_predeclared_primary_fusion"] is True
    assert protocol["components"] == fusion.WEIGHTS
    assert protocol["transform"].startswith("training_only")
    assert protocol["ground_truth_read"] is False
    assert len(protocol["protocol_signature"]) == 64


def test_bundle_rejects_label_contamination_before_publication(tmp_path):
    v4, v5, v10, _ = _sources(tmp_path)
    rows = [json.loads(line) for line in (v4 / "scores.jsonl").read_text().splitlines()]
    rows[0]["label"] = "POSITIVE"
    scores = v4 / "scores.jsonl"
    scores.write_text("".join(json.dumps(row) + "\n" for row in rows))
    summary = json.loads((v4 / "summary.json").read_text())
    summary["scores_sha256"] = _sha(scores)
    (v4 / "summary.json").write_text(json.dumps(summary))
    with pytest.raises(PipelineError, match="v4 invalido"):
        fusion.build_blind_signal_bundle(
            medgemma_v4_root=v4, medsiglip_v5_root=v5, localizer_v10_root=v10,
            output_dir=tmp_path / "out", expected_case_count=10,
        )


def test_bundle_rejects_unexpected_case_exclusion(tmp_path):
    v4, v5, v10, _ = _sources(tmp_path)
    with pytest.raises(PipelineError, match="coorte e a exclusao"):
        fusion.build_blind_signal_bundle(
            medgemma_v4_root=v4, medsiglip_v5_root=v5, localizer_v10_root=v10,
            output_dir=tmp_path / "out", expected_case_count=10,
            excluded_case_id="anon-other-exclusion",
        )


def test_tampered_bundle_is_rejected_by_frozen_protocol(tmp_path):
    bundle, protocol_path, _, _, _ = _bundle_and_protocol(tmp_path)
    rows = (bundle / "signals.jsonl").read_text().splitlines()
    first = json.loads(rows[0])
    first["signals"]["localizer_v10_log_volume"] = 999.0
    rows[0] = json.dumps(first)
    (bundle / "signals.jsonl").write_text("\n".join(rows) + "\n")
    with pytest.raises(PipelineError, match="invalido ou adulterado"):
        fusion.verify_fusion_protocol(
            bundle_root=bundle, protocol_path=protocol_path, expected_case_count=10
        )


def test_evaluation_aborts_before_reading_labels_without_new_authorization(tmp_path, monkeypatch):
    bundle, protocol_path, _, _, _ = _bundle_and_protocol(tmp_path)
    called = False

    def forbidden(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("protected labels must remain closed")

    monkeypatch.setattr(fusion, "_load_development_labels", forbidden)
    with pytest.raises(PipelineError, match="v11 nao foi autorizada"):
        fusion.evaluate_fusion_development(
            bundle_root=bundle,
            protocol_path=protocol_path,
            labels_path=tmp_path / "not-readable",
            output_dir=tmp_path / "evaluation",
            expected_case_count=10,
        )
    assert called is False


def test_authorized_synthetic_evaluation_is_nested_atomic_and_holdout_closed(tmp_path):
    bundle, protocol_path, _, _, case_ids = _bundle_and_protocol(tmp_path)
    result = fusion.evaluate_fusion_development(
        bundle_root=bundle,
        protocol_path=protocol_path,
        labels_path=_labels(tmp_path, case_ids),
        output_dir=tmp_path / "evaluation",
        allow_protected_development_labels=True,
        expected_case_count=10,
    )
    assert result["primary_loocv_metrics"]["sensitivity"] >= 0.75
    assert result["primary_loocv_metrics"]["specificity"] >= 0.75
    assert result["repeated_stratified_5fold"]["runs_passing_75_75"] == 50
    assert result["development_gate_passed"] is True
    assert result["qualified"] is False
    assert result["holdout_opened"] is False
    assert (tmp_path / "evaluation" / "evaluation.json").is_file()
    assert (tmp_path / "evaluation" / "case_features.csv").is_file()


def test_ecdf_uses_only_supplied_reference():
    assert fusion._ecdf(2.0, [1.0, 2.0, 3.0]) == pytest.approx(0.5)
    assert fusion._ecdf(4.0, [1.0, 2.0, 3.0]) == 1.0
    assert fusion._ecdf(0.0, [1.0, 2.0, 3.0]) == 0.0
