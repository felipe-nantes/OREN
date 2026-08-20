"""Fail-closed tests for the frozen-candidate loaders (PHASE_07 gap G1/G2).

Every artifact here is synthetic: no protected label source, no real cohort.
The goal is asserting that each anti-leakage guard in
``load_frozen_oof_predictions`` / ``evaluate_robustness`` actually raises.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from dtwin.core import PipelineError
from dtwin.learning.protocol import canonical_sha256, sha256_file
from dtwin.learning.robustness import (
    _json,
    _jsonl,
    _percentile,
    clinical_subtype_map,
    evaluate_robustness,
    load_frozen_oof_predictions,
)


def _write_candidate(root: Path, rows: list[dict], **freeze_overrides) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    predictions = root / "oof_predictions.jsonl"
    predictions.write_text(
        "".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8"
    )
    body = {
        "candidate_id": "synthetic-candidate",
        "oof_predictions_sha256": sha256_file(predictions),
        "held_out_labels_used_for_fit_or_threshold": False,
    }
    body.update(freeze_overrides)
    freeze = {**body, "prediction_signature": canonical_sha256(body)}
    (root / "prediction_freeze.json").write_text(
        json.dumps(freeze), encoding="utf-8"
    )
    return root


def _rows(*specs: tuple[str, str]) -> list[dict]:
    return [
        {
            "case_id": case_id,
            "prediction": prediction,
            "technical_failure": False,
            "score": 0.9 if prediction == "POSITIVE" else 0.1,
        }
        for case_id, prediction in specs
    ]


def test_json_helper_raises_on_missing_and_invalid_file(tmp_path):
    with pytest.raises(PipelineError, match="ausente ou inv"):
        _json(tmp_path / "missing.json", "Artefato")
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    with pytest.raises(PipelineError, match="ausente ou inv"):
        _json(bad, "Artefato")


def test_jsonl_helper_rejects_non_object_rows(tmp_path):
    path = tmp_path / "rows.jsonl"
    path.write_text('{"ok": 1}\n[1, 2]\n', encoding="utf-8")
    with pytest.raises(PipelineError, match="registro inv"):
        _jsonl(path, "Predições")


def test_jsonl_helper_raises_on_missing_file(tmp_path):
    with pytest.raises(PipelineError, match="ausente ou inv"):
        _jsonl(tmp_path / "missing.jsonl", "Predições")


def test_load_frozen_accepts_untampered_candidate(tmp_path):
    root = _write_candidate(tmp_path / "cand", _rows(("a1", "POSITIVE")))
    freeze, rows = load_frozen_oof_predictions(root)
    assert freeze["candidate_id"] == "synthetic-candidate"
    assert rows == _rows(("a1", "POSITIVE"))


def test_load_frozen_rejects_tampered_signature(tmp_path):
    root = _write_candidate(tmp_path / "cand", _rows(("a1", "POSITIVE")))
    freeze = json.loads((root / "prediction_freeze.json").read_text("utf-8"))
    freeze["candidate_id"] = "renamed-after-signing"
    (root / "prediction_freeze.json").write_text(json.dumps(freeze), "utf-8")
    with pytest.raises(PipelineError, match="Assinatura do candidato diverge"):
        load_frozen_oof_predictions(root)


def test_load_frozen_rejects_tampered_predictions(tmp_path):
    root = _write_candidate(tmp_path / "cand", _rows(("a1", "POSITIVE")))
    predictions = root / "oof_predictions.jsonl"
    predictions.write_text(
        predictions.read_text("utf-8").replace("POSITIVE", "NEGATIVE"),
        encoding="utf-8",
    )
    with pytest.raises(PipelineError, match="foram alteradas"):
        load_frozen_oof_predictions(root)


@pytest.mark.parametrize("flag", [True, None, "false"])
def test_load_frozen_requires_explicit_false_holdout_flag(tmp_path, flag):
    # Fail-closed: só o literal False passa; ausência (None) também bloqueia.
    root = _write_candidate(
        tmp_path / "cand",
        _rows(("a1", "POSITIVE")),
        held_out_labels_used_for_fit_or_threshold=flag,
    )
    with pytest.raises(PipelineError, match="holdout"):
        load_frozen_oof_predictions(root)


@pytest.mark.parametrize("leak_key", ["label", "ground_truth"])
def test_load_frozen_rejects_ground_truth_inside_predictions(tmp_path, leak_key):
    rows = _rows(("a1", "POSITIVE"))
    rows[0][leak_key] = "POSITIVE"
    root = _write_candidate(tmp_path / "cand", rows)
    with pytest.raises(PipelineError, match="ground truth"):
        load_frozen_oof_predictions(root)


def test_percentile_of_empty_sample_is_zero():
    assert _percentile([], 0.5) == 0.0


def test_clinical_subtype_map_skips_rows_without_case_id():
    mapping = clinical_subtype_map(
        [{"subtype": "hemangioma"}, {"case_id": "  ", "subtype": "fnh"},
         {"case_id": "a1", "subtype": "HCC "}]
    )
    assert mapping == {"a1": "hcc"}


# --- evaluate_robustness end-to-end sobre artefatos 100% sintéticos ---------


def _write_protocol(workspace: Path) -> Path:
    labels_dir = workspace / "casos" / "qualification"
    labels_dir.mkdir(parents=True)
    (labels_dir / "labels_a.jsonl").write_text(
        json.dumps({"case_id": "a1", "patient_group_id": "pa1",
                    "label": "POSITIVE"}) + "\n"
        + json.dumps({"case_id": "a2", "patient_group_id": "pa2",
                      "label": "NEGATIVE", "subtype": "hemangioma"}) + "\n",
        encoding="utf-8",
    )
    (labels_dir / "labels_b.jsonl").write_text(
        json.dumps({"case_id": "b1", "patient_group_id": "pb1",
                    "label": "POSITIVE"}) + "\n"
        + json.dumps({"case_id": "b2", "patient_group_id": "pb2",
                      "label": "NEGATIVE"}) + "\n",
        encoding="utf-8",
    )
    config = workspace / "training_protocol.yaml"
    config.write_text(
        "protected_label_sources:\n"
        "  - dataset_id: ds_a\n"
        "    path: casos/qualification/labels_a.jsonl\n"
        "  - dataset_id: ds_b\n"
        "    path: casos/qualification/labels_b.jsonl\n",
        encoding="utf-8",
    )
    return config


def test_evaluate_robustness_over_synthetic_candidate(tmp_path):
    config = _write_protocol(tmp_path)
    root = _write_candidate(
        tmp_path / "cand",
        _rows(("a1", "POSITIVE"), ("a2", "NEGATIVE"),
              ("b1", "POSITIVE"), ("b2", "NEGATIVE")),
    )
    report = evaluate_robustness(
        candidate_root=root,
        training_protocol_config_path=config,
        workspace_root=tmp_path,
        n_resamples=25,
        seed=20260724,
    )
    assert report["schema"] == "argos-hybrid-robustness-report-v1"
    assert report["candidate_id"] == "synthetic-candidate"
    assert report["overall"]["case_count"] == 4
    assert set(report["leave_one_dataset_out"]) == {"ds_a", "ds_b"}
    assert report["stability"]["all_datasets_pass_75_75"] is True
    assert report["research_only"] is True
    assert report["clinical_use_allowed"] is False
    body = {k: v for k, v in report.items() if k != "report_signature"}
    assert report["report_signature"] == canonical_sha256(body)


def test_evaluate_robustness_rejects_case_outside_protocol(tmp_path):
    config = _write_protocol(tmp_path)
    root = _write_candidate(
        tmp_path / "cand",
        _rows(("a1", "POSITIVE"), ("intruso", "NEGATIVE")),
    )
    with pytest.raises(PipelineError, match="fora do protocolo protegido"):
        evaluate_robustness(
            candidate_root=root,
            training_protocol_config_path=config,
            workspace_root=tmp_path,
            n_resamples=10,
            seed=1,
        )
