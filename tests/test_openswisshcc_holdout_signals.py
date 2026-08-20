from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from dtwin.benchmark import openswisshcc_holdout_signals as module
from dtwin.benchmark.openswisshcc_alignment import _sha256
from dtwin.benchmark.openswisshcc_holdout import (
    HOLDOUT_AUDIT_SCHEMA,
    HOLDOUT_INPUT_SCHEMA,
)
from dtwin.benchmark.openswisshcc_holdout_panels import COHORT_SCHEMA
from dtwin.benchmark.public_independent_v21_calibrator import (
    SCORE_SCHEMA,
    SCORE_SUMMARY_SCHEMA,
)
from dtwin.core import PipelineError


def _write(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True), encoding="utf-8")


def _context_fixture(tmp_path: Path, monkeypatch):
    panel_root = tmp_path / "panels"
    prepared = tmp_path / "prepared"
    gallery = tmp_path / "gallery"
    panel_root.mkdir()
    gallery.mkdir()
    inputs = prepared / "inputs"
    manifest_rows = []
    cases = []
    case_ids = []
    for index in range(1, 45):
        case_id = f"anon-openswiss-{index:016x}"
        case_ids.append(case_id)
        kind = module.FALLBACK_KIND if index == 28 else "multiphase_rgb"
        panel = panel_root / case_id / "panel.png"
        panel.parent.mkdir()
        panel.write_bytes(f"panel-{index}".encode())
        cases.append(
            {
                "case_id": case_id,
                "candidate_kind": kind,
                "panel": f"{case_id}/panel.png",
                "panel_sha256": _sha256(panel),
            }
        )
        file_rows = []
        for role in ("t1_venous", "liver_mask_venous"):
            path = inputs / case_id / f"{role}.nii.gz"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(f"{role}-{index}".encode())
            file_rows.append(
                {
                    "role": role,
                    "relative_path": f"{case_id}/{role}.nii.gz",
                    "bytes": path.stat().st_size,
                    "sha256": _sha256(path),
                }
            )
        manifest_rows.append(
            {
                "schema": HOLDOUT_INPUT_SCHEMA,
                "split": "holdout_blind",
                "case_id": case_id,
                "files": file_rows,
                "research_only": True,
                "clinical_use_allowed": False,
            }
        )
    manifest_path = prepared / "manifests" / "holdout_inputs.jsonl"
    manifest_path.parent.mkdir(parents=True)
    manifest_path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in manifest_rows),
        encoding="utf-8",
    )
    multiphase = tmp_path / "multiphase.yaml"
    fallback = tmp_path / "fallback.yaml"
    medsiglip = tmp_path / "medsiglip.yaml"
    calibrator = tmp_path / "calibrator.json"
    for path in (multiphase, fallback, medsiglip):
        path.write_text("frozen", encoding="utf-8")
    calibrator.write_text("{}", encoding="utf-8")
    audit = {
        "schema": HOLDOUT_AUDIT_SCHEMA,
        "status": "label_blind_holdout_preparation_verified",
        "labels_read": False,
        "lesion_masks_read": 0,
    }
    audit_path = tmp_path / "audit.json"
    _write(audit_path, audit)
    cohort = {
        "schema": COHORT_SCHEMA,
        "case_count": 44,
        "cases": cases,
        "multiphase_case_count": 43,
        "venous_fallback_case_count": 1,
        "prepared_audit_sha256": _sha256(audit_path),
        "multiphase_config_sha256": _sha256(multiphase),
        "fallback_config_sha256": _sha256(fallback),
        "holdout_ground_truth_opened": False,
        "pathology_labels_used": False,
        "lesion_masks_used": False,
    }
    _write(panel_root / "cohort_manifest.json", cohort)
    review = {"approved_case_ids": case_ids, "review_signature": "r" * 64}
    config = {
        "medgemma": {
            "model_id": "google/medgemma-1.5-4b-it",
            "model_parameter_scale": "4B",
            "model_version": "1.5",
            "response_mode": "choice_classification",
            "max_retries": 0,
            "timeout_seconds": 120,
        },
        "prompt": {"template": "frozen prompt"},
    }
    frozen_calibrator = {
        "calibrator_signature": "c" * 64,
        "decision_rule": "frozen rule",
        "threshold": 0.5,
    }
    monkeypatch.setattr(module, "verify_holdout_uniform9_review", lambda **kwargs: review)
    monkeypatch.setattr(module, "audit_prepared_holdout_label_blind", lambda root: audit)
    monkeypatch.setattr(module, "_validate_config", lambda path, mode: config)
    monkeypatch.setattr(
        module,
        "load_medsiglip_config",
        lambda path: SimpleNamespace(
            model_id="google/medsiglip-448", decision_enabled=False
        ),
    )
    monkeypatch.setattr(module, "_load_calibrator", lambda path: frozen_calibrator)
    monkeypatch.setattr(module, "EXPECTED_CALIBRATOR_SHA256", _sha256(calibrator))
    monkeypatch.setattr(module, "EXPECTED_CALIBRATOR_SIGNATURE", "c" * 64)
    kwargs = {
        "panel_root": panel_root,
        "gallery_root": gallery,
        "review_path": tmp_path / "review.json",
        "prepared_root": prepared,
        "prepared_audit_path": audit_path,
        "multiphase_config_path": multiphase,
        "fallback_config_path": fallback,
        "medsiglip_config_path": medsiglip,
        "calibrator_path": calibrator,
    }
    return kwargs, case_ids


def test_context_preflight_stays_label_blind(tmp_path: Path, monkeypatch):
    kwargs, case_ids = _context_fixture(tmp_path, monkeypatch)
    context = module.verify_holdout_v21_signal_context(**kwargs)
    result = module.context_preflight_summary(context)
    assert context["case_ids"] == case_ids
    assert result["case_count"] == 44
    assert result["models_loaded"] is False
    assert result["labels_read"] is False
    assert result["lesion_masks_read"] == 0


def test_context_fails_closed_before_model_creation_without_review(tmp_path: Path, monkeypatch):
    kwargs, _ = _context_fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(
        module,
        "verify_holdout_uniform9_review",
        lambda **kwargs: (_ for _ in ()).throw(PipelineError("review absent")),
    )
    model_created = False
    with pytest.raises(PipelineError, match="review absent"):
        module.verify_holdout_v21_signal_context(**kwargs)
    assert model_created is False


def test_localizer_manifest_contains_only_venous_and_liver_mask(tmp_path: Path, monkeypatch):
    kwargs, _ = _context_fixture(tmp_path, monkeypatch)
    context = module.verify_holdout_v21_signal_context(**kwargs)
    output = tmp_path / "localizer_inputs.jsonl"
    result = module.build_holdout_v21_localizer_input_manifest(
        context=context, prepared_root=kwargs["prepared_root"], output_path=output
    )
    rows = module._jsonl(output)
    assert result["case_count"] == 44
    assert all({item["role"] for item in row["files"]} == {"t1_venous", "liver_mask_venous"} for row in rows)
    assert all(row["ground_truth_read"] is False for row in rows)
    assert all(row["lesion_mask_available"] is False for row in rows)
    assert all(
        "lesion" not in (item["role"] + " " + item["relative_path"]).lower()
        for row in rows
        for item in row["files"]
    )


class _Scorer:
    model_id = "google/medgemma-1.5-4b-it"
    model_version = "1.5"

    def __init__(self):
        self.calls = []

    def score_panel(self, panel_path: Path, prompt: str):
        self.calls.append((panel_path, prompt))
        return {
            "choice_probabilities": {
                "POSITIVA": 0.2,
                "NEGATIVA": 0.7,
                "INCONCLUSIVA": 0.1,
            }
        }


def test_medgemma_uses_43_multiphase_and_one_fallback_scorer(tmp_path: Path, monkeypatch):
    kwargs, _ = _context_fixture(tmp_path, monkeypatch)
    context = module.verify_holdout_v21_signal_context(**kwargs)
    multiphase = _Scorer()
    fallback = _Scorer()
    result = module.run_holdout_v21_medgemma_scores(
        context=context,
        panel_root=kwargs["panel_root"],
        output_root=tmp_path / "mg",
        multiphase_scorer=multiphase,
        fallback_scorer=fallback,
    )
    assert result["case_count"] == 44
    assert len(multiphase.calls) == 43
    assert len(fallback.calls) == 1
    assert result["final_decision"] is None


class _FailingScorer(_Scorer):
    def score_panel(self, panel_path: Path, prompt: str):
        raise PipelineError("technical failure")


def test_medgemma_intermediate_failure_does_not_publish_partial_batch(tmp_path: Path, monkeypatch):
    kwargs, _ = _context_fixture(tmp_path, monkeypatch)
    context = module.verify_holdout_v21_signal_context(**kwargs)
    output = tmp_path / "mg"
    with pytest.raises(PipelineError, match="technical failure"):
        module.run_holdout_v21_medgemma_scores(
            context=context,
            panel_root=kwargs["panel_root"],
            output_root=output,
            multiphase_scorer=_FailingScorer(),
            fallback_scorer=_Scorer(),
        )
    assert not output.exists()


def test_prediction_freeze_signs_hashes_with_labels_closed(tmp_path: Path, monkeypatch):
    kwargs, case_ids = _context_fixture(tmp_path, monkeypatch)
    context = module.verify_holdout_v21_signal_context(**kwargs)
    raw = tmp_path / "raw"
    raw.mkdir()
    raw_signals = raw / "raw_signals.jsonl"
    raw_signals.write_text("".join(json.dumps({"case_id": case}) + "\n" for case in case_ids), encoding="utf-8")
    _write(
        raw / "summary.json",
        {
            "schema": module.RAW_SIGNAL_SUMMARY_SCHEMA,
            "status": "complete_raw_signals_no_labels_no_decision",
            "case_ids": case_ids,
            "review_signature": context["review_signature"],
            "ground_truth_read": False,
        },
    )
    scores = tmp_path / "scores"
    scores.mkdir()
    scores_path = scores / "scores.jsonl"
    score_rows = [
        {
            "schema": SCORE_SCHEMA,
            "case_id": case,
            "decision": "POSITIVE" if index < 20 else "NEGATIVE",
            "calibrator_signature": "c" * 64,
            "total_component_seconds": 100.0,
            "time_gate_180_seconds_passed": True,
            "ground_truth_read": False,
            "metrics_calculated": False,
            "holdout_opened": False,
            "research_only": True,
            "clinical_use_allowed": False,
        }
        for index, case in enumerate(case_ids)
    ]
    scores_path.write_text(
        "".join(json.dumps(row) + "\n" for row in score_rows), encoding="utf-8"
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
            "calibrator_sha256": _sha256(context["calibrator_path"]),
            "calibrator_signature": "c" * 64,
            "positive_prediction_count": 20,
            "negative_prediction_count": 24,
            "all_time_gates_passed": True,
            "ground_truth_read": False,
            "metrics_calculated": False,
            "holdout_opened": False,
        },
    )
    output = tmp_path / "prediction_freeze.json"
    result = module.freeze_holdout_v21_predictions(
        context=context, raw_signal_root=raw, score_root=scores, output_path=output
    )
    assert result["status"] == "predictions_and_final_protocol_frozen_labels_closed"
    assert result["holdout_ground_truth_opened"] is False
    assert len(result["protocol_signature"]) == 64
    verified = module.verify_holdout_v21_prediction_freeze(
        context=context,
        raw_signal_root=raw,
        score_root=scores,
        freeze_path=output,
        expected_protocol_signature=result["protocol_signature"],
    )
    assert verified == result


def test_prediction_freeze_rejects_score_tampering(tmp_path: Path, monkeypatch):
    kwargs, case_ids = _context_fixture(tmp_path, monkeypatch)
    context = module.verify_holdout_v21_signal_context(**kwargs)
    raw = tmp_path / "raw"
    scores = tmp_path / "scores"
    raw.mkdir()
    scores.mkdir()
    (raw / "raw_signals.jsonl").write_text("{}\n", encoding="utf-8")
    _write(
        raw / "summary.json",
        {
            "schema": module.RAW_SIGNAL_SUMMARY_SCHEMA,
            "status": "complete_raw_signals_no_labels_no_decision",
            "case_ids": case_ids,
            "review_signature": context["review_signature"],
            "ground_truth_read": False,
        },
    )
    (scores / "scores.jsonl").write_text("{}\n", encoding="utf-8")
    _write(scores / "summary.json", {"schema": SCORE_SUMMARY_SCHEMA})
    with pytest.raises(PipelineError, match="freeze recusado"):
        module.freeze_holdout_v21_predictions(
            context=context,
            raw_signal_root=raw,
            score_root=scores,
            output_path=tmp_path / "freeze.json",
        )
