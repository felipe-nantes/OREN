from __future__ import annotations

import json
from pathlib import Path

import pytest

from dtwin.benchmark import lld_mmri_v23_predictions as module
from dtwin.benchmark.openswisshcc_alignment import _sha256
from dtwin.benchmark.openswisshcc_v20_fusion import V11_WEIGHTS
from dtwin.benchmark.public_independent_v21_calibrator import RAW_SIGNAL_SCHEMA
from dtwin.core import PipelineError


CALIBRATOR = Path(
    "casos/qualification/openswisshcc_v1/prepared/development_freezes_v23/"
    "shape_fusion_calibrator_v1.json"
)


def _write_bundle(tmp_path: Path, monkeypatch):
    calibrator_path = CALIBRATOR.resolve()
    calibrator = json.loads(calibrator_path.read_text(encoding="utf-8"))
    case_id = "anon-lld-0000000000000000"
    review_signature = "r" * 64
    protocol = {
        "case_ids": [case_id],
        "case_count": 1,
        "protocol_signature": "p" * 64,
        "calibrator_signature": calibrator["calibrator_signature"],
        "calibrator_sha256": _sha256(calibrator_path),
        "decision_threshold": calibrator["decision_threshold"],
    }
    monkeypatch.setattr(module, "_load_and_validate_protocol", lambda _: (protocol, []))

    raw_root = tmp_path / "raw"
    raw_root.mkdir()
    row = {
        "schema": RAW_SIGNAL_SCHEMA,
        "case_id": case_id,
        "signals": {name: 0.0 for name in V11_WEIGHTS},
        "component_elapsed_seconds": {
            "medgemma_v4": 10.0,
            "medsiglip_v5": 5.0,
            "localizer_v10": 15.0,
        },
        "component_hashes": {},
        "review_signature": review_signature,
        "ground_truth_read": False,
        "metrics_calculated": False,
        "final_decision": None,
        "holdout_opened": False,
        "research_only": True,
        "clinical_use_allowed": False,
        "requires_human_review": True,
    }
    raw_path = raw_root / "raw_signals.jsonl"
    raw_path.write_text(json.dumps(row, sort_keys=True) + "\n", encoding="utf-8")
    (raw_root / "summary.json").write_text(
        json.dumps(
            {
                "schema": module.RAW_SIGNAL_SUMMARY_SCHEMA,
                "status": "complete_raw_signals_no_labels_no_decision",
                "case_count": 1,
                "case_ids": [case_id],
                "protocol_case_count": 1,
                "technical_failure_case_count": 0,
                "technical_failure_case_ids": [],
                "technical_failures_excluded_from_inference": True,
                "technical_failures_count_as_primary_metric_errors": True,
                "signals_sha256": _sha256(raw_path),
                "review_signature": review_signature,
                "ground_truth_read": False,
                "metrics_calculated": False,
                "final_decision": None,
            }
        ),
        encoding="utf-8",
    )

    shape_root = tmp_path / "shape"
    shape_root.mkdir()
    (shape_root / "features.jsonl").write_text(
        json.dumps({"case_id": case_id, "elapsed_seconds": 2.0}) + "\n",
        encoding="utf-8",
    )
    (shape_root / "summary.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(
        module,
        "_load_shape_bundle",
        lambda _root, _case_ids: ({"review_signature": review_signature}, {case_id: 0.5}),
    )
    return {
        "context": {
            "protocol_case_count": 1,
            "case_ids": [case_id],
            "technical_failure_case_count": 0,
            "technical_failure_case_ids": [],
            "technical_failures_count_as_primary_metric_errors": True,
            "review_signature": review_signature,
        },
        "protocol_root": tmp_path / "protocol",
        "calibrator_path": calibrator_path,
        "raw_signals_root": raw_root,
        "shape_root": shape_root,
        "output_root": tmp_path / "predictions",
    }, row


def test_freezes_label_blind_predictions_atomically(monkeypatch, tmp_path: Path):
    kwargs, _ = _write_bundle(tmp_path, monkeypatch)
    result = module.freeze_lld_mmri_v23_predictions(**kwargs)
    output = kwargs["output_root"]
    prediction = json.loads((output / "predictions.jsonl").read_text(encoding="utf-8"))

    assert result["status"] == "frozen_complete_predictions_before_labels"
    assert result["predictions_frozen"] is True
    assert result["protocol_case_count"] == 1
    assert result["technical_failure_case_count"] == 0
    assert result["ground_truth_read"] is False
    assert result["end_to_end_time_evaluated"] is False
    assert result["qualified"] is False
    assert prediction["case_id"] == kwargs["context"]["case_ids"][0]
    assert prediction["prepared_signal_seconds"] == 32.0
    assert prediction["prediction_signature"]
    assert not any(output.parent.glob("._lldv23pred_*"))


def test_rejects_tampered_signal_hash(monkeypatch, tmp_path: Path):
    kwargs, row = _write_bundle(tmp_path, monkeypatch)
    row["signals"][next(iter(V11_WEIGHTS))] = 123.0
    (kwargs["raw_signals_root"] / "raw_signals.jsonl").write_text(
        json.dumps(row, sort_keys=True) + "\n", encoding="utf-8"
    )
    with pytest.raises(PipelineError, match="adulterado"):
        module.freeze_lld_mmri_v23_predictions(**kwargs)


def test_rejects_protected_label_in_signal_record(monkeypatch, tmp_path: Path):
    kwargs, row = _write_bundle(tmp_path, monkeypatch)
    row["label"] = "POSITIVE"
    raw_path = kwargs["raw_signals_root"] / "raw_signals.jsonl"
    raw_path.write_text(json.dumps(row, sort_keys=True) + "\n", encoding="utf-8")
    summary_path = kwargs["raw_signals_root"] / "summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    summary["signals_sha256"] = _sha256(raw_path)
    summary_path.write_text(json.dumps(summary), encoding="utf-8")
    with pytest.raises(PipelineError, match="Registro de sinal"):
        module.freeze_lld_mmri_v23_predictions(**kwargs)
