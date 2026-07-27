from __future__ import annotations

import json
from pathlib import Path

import pytest

from dtwin.benchmark import lld_mmri_v23_direct_timing as module
from dtwin.benchmark.lld_mmri_v23_predictions import PREDICTION_SCHEMA, RUN_SCHEMA
from dtwin.benchmark.openswisshcc_alignment import _sha256
from dtwin.benchmark.openswisshcc_v20_fusion import _canonical_sha
from dtwin.core import PipelineError


def _frozen(tmp_path: Path, monkeypatch):
    case_id = "anon-lld-0000000000000000"
    protocol = {
        "case_ids": [case_id], "case_count": 1,
        "protocol_signature": "p" * 64, "calibrator_signature": "c" * 64,
    }
    root = tmp_path / "predictions"; root.mkdir()
    base = {
        "schema": PREDICTION_SCHEMA, "case_id": case_id,
        "prediction": "POSITIVE", "score": 0.8,
        "protocol_signature": protocol["protocol_signature"],
        "calibrator_signature": protocol["calibrator_signature"],
        "ground_truth_read": False, "metrics_calculated": False,
    }
    row = dict(base); row["prediction_signature"] = _canonical_sha(base)
    path = root / "predictions.jsonl"
    path.write_text(json.dumps(row, sort_keys=True) + "\n", encoding="utf-8")
    summary_base = {
        "schema": RUN_SCHEMA, "status": "frozen_complete_predictions_before_labels",
        "protocol_case_count": 1,
        "case_count": 1, "case_ids": [case_id],
        "technical_failure_case_count": 0,
        "technical_failure_case_ids": [],
        "technical_failures_excluded_from_inference": True,
        "technical_failures_count_as_primary_metric_errors": True,
        "predictions_sha256": _sha256(path),
        "protocol_signature": protocol["protocol_signature"],
        "calibrator_signature": protocol["calibrator_signature"],
        "predictions_frozen": True, "ground_truth_read": False,
        "metrics_calculated": False, "qualified": False,
    }
    summary = dict(summary_base); summary["run_signature"] = _canonical_sha(summary_base)
    (root / "summary.json").write_text(json.dumps(summary), encoding="utf-8")
    monkeypatch.setattr(module, "_load_and_validate_protocol", lambda _: (protocol, []))
    return protocol, root, row


def _receipt(case_id: str, row: dict):
    return {
        "runner_id": module.RUNNER_ID,
        "case_id": case_id,
        "prediction_signature": row["prediction_signature"],
        "prediction": row["prediction"],
        "stages": {name: {"status": "complete"} for name in module.REQUIRED_STAGES},
        "ground_truth_read": False,
        "lesion_masks_read": 0,
    }


def test_direct_timing_requires_exact_prediction_reproduction(monkeypatch, tmp_path: Path):
    protocol, predictions, row = _frozen(tmp_path, monkeypatch)
    output = tmp_path / "timing"
    result = module.measure_lld_mmri_v23_direct_reproduction(
        protocol_root=tmp_path / "protocol",
        frozen_prediction_root=predictions,
        output_root=output,
        run_case=lambda case_id: _receipt(case_id, row),
    )
    case = json.loads((output / "cases.jsonl").read_text(encoding="utf-8"))
    assert result["case_ids"] == protocol["case_ids"]
    assert result["continuous_wall_clock"] is True
    assert result["component_sum_only"] is False
    assert result["all_predictions_exactly_reproduced"] is True
    assert result["all_inference_eligible_cases_within_180_seconds"] is True
    assert result["all_cases_within_180_seconds"] is True
    assert case["case_timing_signature"]


def test_direct_timing_rejects_changed_prediction(monkeypatch, tmp_path: Path):
    _, predictions, row = _frozen(tmp_path, monkeypatch)
    def changed(case_id):
        receipt = _receipt(case_id, row)
        receipt["prediction"] = "NEGATIVE"
        return receipt
    with pytest.raises(PipelineError, match="nao reproduziu"):
        module.measure_lld_mmri_v23_direct_reproduction(
            protocol_root=tmp_path / "protocol",
            frozen_prediction_root=predictions,
            output_root=tmp_path / "timing",
            run_case=changed,
        )


def test_direct_timing_requires_all_stage_receipts(monkeypatch, tmp_path: Path):
    _, predictions, row = _frozen(tmp_path, monkeypatch)
    def incomplete(case_id):
        receipt = _receipt(case_id, row)
        receipt["stages"].pop("medgemma")
        return receipt
    with pytest.raises(PipelineError, match="nao reproduziu"):
        module.measure_lld_mmri_v23_direct_reproduction(
            protocol_root=tmp_path / "protocol",
            frozen_prediction_root=predictions,
            output_root=tmp_path / "timing",
            run_case=incomplete,
        )


def test_direct_timing_runs_only_eligible_cases_and_binds_failures(
    monkeypatch, tmp_path: Path
):
    protocol, predictions, row = _frozen(tmp_path, monkeypatch)
    failure_id = "anon-lld-9999999999999999"
    protocol["case_ids"].append(failure_id)
    protocol["case_count"] = 2
    summary_path = predictions / "summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    summary.pop("run_signature")
    summary.update(
        protocol_case_count=2,
        technical_failure_case_count=1,
        technical_failure_case_ids=[failure_id],
    )
    summary["run_signature"] = _canonical_sha(summary)
    summary_path.write_text(json.dumps(summary), encoding="utf-8")
    called = []

    def run(case_id):
        called.append(case_id)
        return _receipt(case_id, row)

    result = module.measure_lld_mmri_v23_direct_reproduction(
        protocol_root=tmp_path / "protocol",
        frozen_prediction_root=predictions,
        output_root=tmp_path / "timing",
        run_case=run,
    )
    assert called == [row["case_id"]]
    assert result["protocol_case_count"] == 2
    assert result["technical_failure_case_count"] == 1
    assert result["technical_failure_case_ids"] == [failure_id]
    assert result["all_inference_eligible_cases_within_180_seconds"] is True


def test_direct_timing_resumes_after_interruption_without_repeating_case(
    monkeypatch, tmp_path: Path
):
    protocol, predictions, first_row = _frozen(tmp_path, monkeypatch)
    second_id = "anon-lld-0000000000000001"
    second_base = {
        key: value
        for key, value in first_row.items()
        if key != "prediction_signature"
    }
    second_base["case_id"] = second_id
    second_row = dict(second_base)
    second_row["prediction_signature"] = _canonical_sha(second_base)
    predictions_path = predictions / "predictions.jsonl"
    predictions_path.write_text(
        json.dumps(first_row, sort_keys=True)
        + "\n"
        + json.dumps(second_row, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )
    protocol["case_ids"] = [first_row["case_id"], second_id]
    protocol["case_count"] = 2
    summary_path = predictions / "summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    summary.pop("run_signature")
    summary.update(
        protocol_case_count=2,
        case_count=2,
        case_ids=protocol["case_ids"],
        predictions_sha256=_sha256(predictions_path),
    )
    summary["run_signature"] = _canonical_sha(summary)
    summary_path.write_text(json.dumps(summary), encoding="utf-8")
    by_id = {first_row["case_id"]: first_row, second_id: second_row}
    first_calls = []

    def interrupted(case_id):
        first_calls.append(case_id)
        if case_id == second_id:
            raise RuntimeError("synthetic power loss")
        return _receipt(case_id, by_id[case_id])

    output = tmp_path / "timing"
    with pytest.raises(RuntimeError, match="synthetic power loss"):
        module.measure_lld_mmri_v23_direct_reproduction(
            protocol_root=tmp_path / "protocol",
            frozen_prediction_root=predictions,
            output_root=output,
            run_case=interrupted,
        )
    incomplete = tmp_path / ".timing.incomplete"
    checkpoint = module._load_checkpoint(incomplete / "checkpoint_cases.jsonl")
    assert [row["case_id"] for row in checkpoint] == [first_row["case_id"]]
    assert not output.exists()

    resumed_calls = []

    def resumed(case_id):
        resumed_calls.append(case_id)
        return _receipt(case_id, by_id[case_id])

    result = module.measure_lld_mmri_v23_direct_reproduction(
        protocol_root=tmp_path / "protocol",
        frozen_prediction_root=predictions,
        output_root=output,
        run_case=resumed,
    )
    assert result["case_count"] == 2
    assert resumed_calls == [second_id]
    assert not incomplete.exists()
