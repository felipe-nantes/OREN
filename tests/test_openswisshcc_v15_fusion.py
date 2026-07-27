from __future__ import annotations

import json
from pathlib import Path

import pytest

from dtwin.benchmark import openswisshcc_v15_fusion as fusion
from dtwin.core import PipelineError


def _write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True) + "\n", encoding="utf-8")


def _row(index: int, count: int, *, classification: str | None = None) -> dict:
    value = index / max(count - 1, 1)
    raw = classification or ("NEGATIVA" if index < count // 2 else "POSITIVA")
    probabilities = {
        "POSITIVA": 0.8 if raw == "POSITIVA" else 0.1,
        "NEGATIVA": 0.8 if raw == "NEGATIVA" else 0.1,
        "INCONCLUSIVA": 0.8 if raw == "INCONCLUSIVA" else 0.1,
    }
    total = sum(probabilities.values())
    probabilities = {key: item / total for key, item in probabilities.items()}
    return {
        "schema": fusion.BLIND_SIGNAL_SCHEMA,
        "case_id": f"anon-case-{index:03d}",
        "signals": {
            **{name: value for name in fusion.V11_WEIGHTS},
            fusion.V15_SIGNAL: value,
        },
        "v15_choice_probabilities": probabilities,
        "v15_raw_classification": raw,
        "v15_prediction_sha256": f"sha-{index}",
        "ground_truth_read": False,
        "metrics_calculated": False,
        "holdout_opened": False,
        "research_only": True,
        "clinical_use_allowed": False,
        "requires_human_review": True,
    }


def _bundle(tmp_path: Path, *, count: int = 10) -> tuple[Path, Path, list[str]]:
    root = tmp_path / "bundle"
    root.mkdir()
    rows = [_row(index, count) for index in range(count)]
    signals = root / "signals.jsonl"
    signals.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )
    case_ids = [row["case_id"] for row in rows]
    summary = {
        "schema": fusion.BLIND_BUNDLE_SCHEMA,
        "status": "complete_blind_signals_no_decision",
        "case_count": count,
        "case_ids": case_ids,
        "signals": [*fusion.V11_WEIGHTS, fusion.V15_SIGNAL],
        "signals_sha256": fusion._sha256(signals),
        "source_hashes": {"synthetic": "sha"},
        "v11_protocol_signature": "v11",
        "v15_protocol_signature": "v15",
        "log_odds_epsilon": fusion.LOG_ODDS_EPSILON,
        "v11_conservative_seconds": 80.0,
        "v15_observed_max_seconds": 17.0,
        "combined_conservative_seconds": 97.0,
        "time_gate_180_seconds_passed": True,
        "ground_truth_read": False,
        "metrics_calculated": False,
        "final_decision": None,
        "holdout_opened": False,
        "research_only": True,
        "clinical_use_allowed": False,
        "requires_human_review": True,
    }
    _write_json(root / "summary.json", summary)
    protocol_path = tmp_path / "protocol.json"
    fusion.create_fusion_protocol(
        bundle_root=root, output_path=protocol_path, expected_case_count=count
    )
    return root, protocol_path, case_ids


def _labels(tmp_path: Path, case_ids: list[str]) -> Path:
    root = tmp_path / "protected_ground_truth"
    root.mkdir(exist_ok=True)
    path = root / "development_labels.jsonl"
    midpoint = len(case_ids) // 2
    rows = [
        {
            "schema": "argos-openswisshcc-ground-truth-v1",
            "case_id": case_id,
            "public_subject_id": str(index),
            "label": "NEGATIVE" if index < midpoint else "POSITIVE",
            "target_condition": "hcc_presence",
            "label_basis": "public",
            "review_status": "reviewed",
        }
        for index, case_id in enumerate(case_ids)
    ]
    path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )
    return path


def test_protocol_freezes_one_equal_reader_primary_and_secondary_cannot_replace_it(tmp_path):
    bundle, protocol_path, _ = _bundle(tmp_path)
    protocol, rows = fusion.verify_fusion_protocol(
        bundle_root=bundle, protocol_path=protocol_path, expected_case_count=10
    )
    assert len(rows) == 10
    assert protocol["single_predeclared_primary_fusion"] is True
    assert protocol["primary_readers"] == {
        "v11_fold_local_weighted_ecdf": 0.5,
        "v15_volume_log_odds_fold_local_ecdf": 0.5,
    }
    assert protocol["secondary_diagnostics_cannot_replace_primary"] is True
    assert protocol["ground_truth_read"] is False
    assert protocol["holdout_opened"] is False


def test_protocol_detects_tampered_signal_hash(tmp_path):
    bundle, protocol_path, _ = _bundle(tmp_path)
    with (bundle / "signals.jsonl").open("a", encoding="utf-8") as handle:
        handle.write("{}\n")
    with pytest.raises(PipelineError, match="Bundle combinado v15 invalido"):
        fusion.verify_fusion_protocol(
            bundle_root=bundle, protocol_path=protocol_path, expected_case_count=10
        )


def test_protocol_detects_tampered_signature(tmp_path):
    bundle, protocol_path, _ = _bundle(tmp_path)
    protocol = json.loads(protocol_path.read_text(encoding="utf-8"))
    protocol["primary_readers"]["v11_fold_local_weighted_ecdf"] = 0.6
    _write_json(protocol_path, protocol)
    with pytest.raises(PipelineError, match="Protocolo v15 invalido"):
        fusion.verify_fusion_protocol(
            bundle_root=bundle, protocol_path=protocol_path, expected_case_count=10
        )


def test_evaluation_aborts_before_reading_labels_without_v15_authorization(tmp_path, monkeypatch):
    bundle, protocol_path, _ = _bundle(tmp_path)

    def forbidden(*_args, **_kwargs):
        raise AssertionError("protected labels must remain closed")

    monkeypatch.setattr(fusion, "_load_development_labels", forbidden)
    with pytest.raises(PipelineError, match="nao foi autorizada"):
        fusion.evaluate_fusion_development(
            bundle_root=bundle,
            protocol_path=protocol_path,
            labels_path=tmp_path / "not-readable",
            output_dir=tmp_path / "evaluation",
            expected_case_count=10,
        )


def test_authorized_synthetic_evaluation_is_nested_atomic_and_holdout_closed(tmp_path):
    bundle, protocol_path, case_ids = _bundle(tmp_path)
    output = tmp_path / "evaluation"
    result = fusion.evaluate_fusion_development(
        bundle_root=bundle,
        protocol_path=protocol_path,
        labels_path=_labels(tmp_path, case_ids),
        output_dir=output,
        allow_protected_development_labels=True,
        expected_case_count=10,
    )
    assert result["primary_loocv_metrics"]["sensitivity"] >= 0.75
    assert result["primary_loocv_metrics"]["specificity"] >= 0.75
    assert result["repeated_stratified_5fold"]["runs_passing_75_75"] == 50
    assert result["development_gate_passed"] is True
    assert result["holdout_opened"] is False
    assert result["qualified"] is False
    assert (output / "evaluation.json").is_file()
    assert (output / "case_features.csv").is_file()


def test_raw_inconclusive_counts_as_error_for_both_classes():
    rows = [_row(0, 2, classification="INCONCLUSIVA"), _row(1, 2, classification="INCONCLUSIVA")]
    metrics = fusion._raw_categorical_metrics(rows, [False, True])
    assert metrics["tn"] == 0
    assert metrics["tp"] == 0
    assert metrics["fp"] == 1
    assert metrics["fn"] == 1
    assert metrics["inconclusive_count"] == 2
    assert metrics["inconclusive_counted_as_error"] is True


def test_fold_scores_use_training_reference_not_test_distribution():
    rows = [_row(index, 4) for index in range(4)]
    rows[3]["signals"][fusion.V15_SIGNAL] = 999.0
    score = fusion._fold_scores(rows, [0, 1, 2], [3], mode="v15")[0]
    assert score == 1.0
    assert fusion._fold_scores(rows, [0, 1, 2], [0], mode="v15")[0] < score


def test_blind_bundle_rejects_protected_label_field(tmp_path):
    bundle, _, _ = _bundle(tmp_path)
    rows = [json.loads(line) for line in (bundle / "signals.jsonl").read_text().splitlines()]
    rows[0]["label"] = "POSITIVE"
    (bundle / "signals.jsonl").write_text(
        "".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8"
    )
    summary = json.loads((bundle / "summary.json").read_text())
    summary["signals_sha256"] = fusion._sha256(bundle / "signals.jsonl")
    _write_json(bundle / "summary.json", summary)
    with pytest.raises(PipelineError, match="Registro combinado v15 invalido"):
        fusion._validate_blind_bundle(bundle, 10)


def test_blind_bundle_rejects_duplicate_case_id(tmp_path):
    bundle, _, _ = _bundle(tmp_path)
    rows = [json.loads(line) for line in (bundle / "signals.jsonl").read_text().splitlines()]
    rows[-1]["case_id"] = rows[0]["case_id"]
    (bundle / "signals.jsonl").write_text(
        "".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8"
    )
    summary = json.loads((bundle / "summary.json").read_text())
    summary["signals_sha256"] = fusion._sha256(bundle / "signals.jsonl")
    summary["case_ids"][-1] = summary["case_ids"][0]
    _write_json(bundle / "summary.json", summary)
    with pytest.raises(PipelineError, match="duplicados"):
        fusion._validate_blind_bundle(bundle, 10)


def test_build_bundle_joins_sources_without_ground_truth(tmp_path, monkeypatch):
    count = 4
    case_ids = [f"anon-case-{index:03d}" for index in range(count)]
    v11_root = tmp_path / "v11"
    v15_root = tmp_path / "v15"
    v11_protocol_path = tmp_path / "v11-protocol.json"
    v15_protocol_path = tmp_path / "v15-protocol.json"
    for path in [v11_root / "summary.json", v11_protocol_path, v15_root / "progress.json", v15_root / "summary.json", v15_protocol_path]:
        _write_json(path, {"source": path.name})
    v11_rows = [
        {"case_id": case_id, "signals": {name: index / count for name in fusion.V11_WEIGHTS}}
        for index, case_id in enumerate(case_ids)
    ]
    predictions = []
    for index, case_id in enumerate(case_ids):
        pred_path = v15_root / "predictions" / f"{case_id}.json"
        _write_json(pred_path, {"case_id": case_id})
        predictions.append(
            {
                "case_id": case_id,
                "choice_probabilities": {"POSITIVA": 0.6, "NEGATIVA": 0.3, "INCONCLUSIVA": 0.1},
                "classification": "POSITIVA",
            }
        )
    monkeypatch.setattr(
        fusion,
        "verify_v11_fusion_protocol",
        lambda **_kwargs: ({"protocol_signature": "v11", "observed_conservative_seconds": 80.0}, v11_rows),
    )
    monkeypatch.setattr(
        fusion,
        "_validate_volume_score_run",
        lambda **_kwargs: ({"protocol_signature": "v15"}, {"request_seconds_max": 17.0}, predictions),
    )
    output = tmp_path / "combined"
    summary = fusion.build_blind_fusion_bundle(
        v11_bundle_root=v11_root,
        v11_protocol_path=v11_protocol_path,
        v15_run_root=v15_root,
        v15_protocol_path=v15_protocol_path,
        output_root=output,
        expected_case_count=count,
    )
    rows = [json.loads(line) for line in (output / "signals.jsonl").read_text().splitlines()]
    assert summary["case_count"] == count
    assert summary["combined_conservative_seconds"] == 97.0
    assert all("label" not in row for row in rows)
    assert all(row["ground_truth_read"] is False for row in rows)

