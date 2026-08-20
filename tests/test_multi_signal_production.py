from __future__ import annotations

import json
from pathlib import Path

import joblib
import numpy as np
import pytest

from dtwin.core import PipelineError
from dtwin.learning import multi_signal_production as production
from dtwin.learning.protocol import canonical_sha256, sha256_file


class _LinearStub:
    def predict_proba(self, matrix):
        values = np.asarray(matrix)[:, 0]
        positive = 1.0 / (1.0 + np.exp(-values))
        return np.column_stack([1.0 - positive, positive])


def _bundle(root: Path) -> None:
    root.mkdir()
    model_path = root / "production_model.joblib"
    joblib.dump(_LinearStub(), model_path)
    body = {
        "schema": production.BUNDLE_SCHEMA,
        "signals": ["a", "b"],
        "signal_contracts": {
            "a": {"base_bundle_signature": "base-a"},
            "b": {"base_bundle_signature": "base-b"},
        },
        "missing_signal_policy": "zero_margin_with_indicator",
        "decision_threshold": 0.5,
        "training_case_ids": ["train-a"],
        "model_sha256": sha256_file(model_path),
    }
    manifest = {**body, "bundle_signature": canonical_sha256(body)}
    (root / "bundle_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")


def _base_predictions(root: Path, bundle_signature: str, scores: dict[str, float]) -> None:
    root.mkdir()
    rows = [{
        "case_id": case_id, "score": score, "threshold": 0.5,
        "technical_failure": False, "prediction": "POSITIVE" if score >= 0.5 else "NEGATIVE",
    } for case_id, score in scores.items()]
    rows_path = root / "predictions.jsonl"
    rows_path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    body = {
        "bundle_signature": bundle_signature,
        "predictions_sha256": sha256_file(rows_path),
    }
    freeze = {**body, "prediction_signature": canonical_sha256(body)}
    (root / "prediction_freeze.json").write_text(json.dumps(freeze), encoding="utf-8")


def test_external_fusion_is_signed_and_label_blind(tmp_path: Path) -> None:
    bundle = tmp_path / "bundle"
    _bundle(bundle)
    a, b = tmp_path / "a", tmp_path / "b"
    _base_predictions(a, "base-a", {"ext-1": 0.8, "ext-2": 0.2})
    _base_predictions(b, "base-b", {"ext-1": 0.7, "ext-2": 0.3})
    freeze = production.predict_external_fusion(
        bundle_root=bundle, signal_prediction_roots={"a": a, "b": b},
        output_root=tmp_path / "out",
    )
    rows = [json.loads(line) for line in (tmp_path / "out" / "predictions.jsonl").read_text().splitlines()]
    assert freeze["case_count"] == 2
    assert freeze["training_case_overlap"] == 0
    assert all("label" not in row and "ground_truth" not in row for row in rows)


def test_external_fusion_rejects_wrong_base_bundle(tmp_path: Path) -> None:
    bundle = tmp_path / "bundle"
    _bundle(bundle)
    a, b = tmp_path / "a", tmp_path / "b"
    _base_predictions(a, "wrong", {"ext-1": 0.8})
    _base_predictions(b, "base-b", {"ext-1": 0.7})
    with pytest.raises(PipelineError, match="outro bundle"):
        production.predict_external_fusion(
            bundle_root=bundle, signal_prediction_roots={"a": a, "b": b},
            output_root=tmp_path / "out",
        )


def test_fusion_bundle_detects_model_tampering(tmp_path: Path) -> None:
    bundle = tmp_path / "bundle"
    _bundle(bundle)
    with (bundle / "production_model.joblib").open("ab") as stream:
        stream.write(b"tamper")
    with pytest.raises(PipelineError, match="alterado"):
        production.load_fusion_production_bundle(bundle)
