from __future__ import annotations

import json
from pathlib import Path

import pytest

from dtwin.benchmark import public_independent_v21_calibrator as module
from dtwin.core import PipelineError


def _write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def _calibrator(tmp_path: Path) -> Path:
    payload = {
        "schema": module.CALIBRATOR_SCHEMA,
        "status": "frozen_for_external_label_blind_scoring",
        "development_case_count": 3,
        "components": module.WEIGHTS,
        "reference_values": {
            "medgemma_v4_uncertainty_margin": [-1.0, 0.0, 1.0],
            "medsiglip_v5_inverse_sagittal": [-0.9, -0.5, -0.1],
            "localizer_v10_log_volume": [0.0, 1.0, 2.0],
        },
        "threshold": 0.5,
        "holdout_opened": False,
        "ground_truth_available_during_external_scoring": False,
    }
    payload["calibrator_signature"] = module._canonical_sha(payload)
    path = tmp_path / "calibrator.json"
    _write_json(path, payload)
    return path


def _signals(tmp_path: Path, *, protected: bool = False) -> Path:
    rows = []
    for index, value in enumerate((-1.0, 1.0)):
        row = {
            "schema": module.RAW_SIGNAL_SCHEMA,
            "case_id": f"anon-external-{index}",
            "signals": {
                "medgemma_v4_uncertainty_margin": value,
                "medsiglip_v5_inverse_sagittal": -0.9 if index == 0 else -0.1,
                "localizer_v10_log_volume": float(index * 2),
            },
            "component_elapsed_seconds": {"medgemma": 10.0, "localizer": 20.0},
            "ground_truth_read": False,
            "metrics_calculated": False,
            "final_decision": None,
            "holdout_opened": False,
            "research_only": True,
            "clinical_use_allowed": False,
        }
        if protected and index == 0:
            row["label"] = "POSITIVE"
        rows.append(row)
    path = tmp_path / "signals.jsonl"
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    return path


def test_score_external_signals_is_deterministic_and_label_blind(tmp_path: Path):
    calibrator = _calibrator(tmp_path)
    signals = _signals(tmp_path)
    result = module.score_external_signals(
        calibrator_path=calibrator,
        signals_path=signals,
        output_dir=tmp_path / "out",
        expected_case_count=2,
    )
    assert result["status"] == "complete_predictions_frozen_labels_still_closed"
    assert result["positive_prediction_count"] == 1
    assert result["negative_prediction_count"] == 1
    assert result["all_time_gates_passed"] is True
    scores = [json.loads(line) for line in (tmp_path / "out/scores.jsonl").read_text().splitlines()]
    assert scores[0]["decision"] == "NEGATIVE"
    assert scores[1]["decision"] == "POSITIVE"
    assert all(row["ground_truth_read"] is False for row in scores)


def test_score_external_signals_accepts_canonical_sorted_signal_keys(tmp_path: Path):
    calibrator = _calibrator(tmp_path)
    signals = _signals(tmp_path)
    rows = [json.loads(line) for line in signals.read_text().splitlines()]
    signals.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows), encoding="utf-8"
    )
    result = module.score_external_signals(
        calibrator_path=calibrator, signals_path=signals, output_dir=tmp_path / "out"
    )
    assert result["case_count"] == 2


def test_score_external_signals_rejects_protected_fields(tmp_path: Path):
    with pytest.raises(PipelineError, match="protegido"):
        module.score_external_signals(
            calibrator_path=_calibrator(tmp_path),
            signals_path=_signals(tmp_path, protected=True),
            output_dir=tmp_path / "out",
        )


def test_score_external_signals_rejects_calibrator_tampering(tmp_path: Path):
    path = _calibrator(tmp_path)
    payload = json.loads(path.read_text())
    payload["threshold"] = 0.1
    _write_json(path, payload)
    with pytest.raises(PipelineError, match="adulterado"):
        module.score_external_signals(
            calibrator_path=path,
            signals_path=_signals(tmp_path),
            output_dir=tmp_path / "out",
        )


def test_score_external_signals_enforces_time_gate(tmp_path: Path):
    signals = _signals(tmp_path)
    rows = [json.loads(line) for line in signals.read_text().splitlines()]
    rows[1]["component_elapsed_seconds"] = {"medgemma": 181.0}
    signals.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    result = module.score_external_signals(
        calibrator_path=_calibrator(tmp_path), signals_path=signals, output_dir=tmp_path / "out"
    )
    assert result["all_time_gates_passed"] is False


def test_freeze_uses_existing_threshold_without_reading_labels(tmp_path: Path, monkeypatch):
    rows = [
        {"signals": {name: float(index) for name in module.WEIGHTS}}
        for index in range(3)
    ]
    protocol = {"protocol_signature": "frozen-signature"}
    monkeypatch.setattr(module, "verify_fusion_protocol", lambda **_: (protocol, rows))
    evaluation = {
        "schema": module.EVALUATION_SCHEMA,
        "case_count": 3,
        "components": module.WEIGHTS,
        "protocol_signature": "frozen-signature",
        "apparent_threshold_for_future_calibrator_freeze": 0.52,
        "ground_truth_read": True,
        "metrics_calculated": True,
        "holdout_opened": False,
        "qualified": False,
        "development_gate_passed": False,
        "research_only": True,
        "clinical_use_allowed": False,
        "protected_development_labels_sha256": "a" * 64,
    }
    evaluation_path = tmp_path / "evaluation.json"
    _write_json(evaluation_path, evaluation)
    bundle = tmp_path / "bundle"
    _write_json(bundle / "summary.json", {})
    (bundle / "signals.jsonl").write_text("\n", encoding="utf-8")
    protocol_path = tmp_path / "protocol.json"
    _write_json(protocol_path, protocol)
    result = module.freeze_v11_external_calibrator(
        bundle_root=bundle,
        protocol_path=protocol_path,
        development_evaluation_path=evaluation_path,
        output_path=tmp_path / "calibrator.json",
        expected_case_count=3,
    )
    assert result["threshold"] == 0.52
    assert result["development_gate_passed"] is False
    assert result["holdout_opened"] is False
    assert "label" not in json.dumps(result["reference_values"])
