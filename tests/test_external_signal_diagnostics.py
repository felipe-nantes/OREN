from __future__ import annotations

import json

import pytest

from dtwin.core import PipelineError
from dtwin.learning import external_signal_diagnostics as diagnostics
from dtwin.learning.protocol import canonical_sha256, sha256_file


def _root(tmp_path):
    root = tmp_path / "predictions"
    root.mkdir()
    rows = [
        {"case_id": "p", "score": .8, "threshold": .5, "prediction": "POSITIVE", "technical_failure": False},
        {"case_id": "n", "score": .2, "threshold": .5, "prediction": "NEGATIVE", "technical_failure": False},
    ]
    path = root / "predictions.jsonl"
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    body = {"predictions_sha256": sha256_file(path)}
    freeze = {**body, "prediction_signature": canonical_sha256(body)}
    (root / "prediction_freeze.json").write_text(json.dumps(freeze), encoding="utf-8")
    return root


def test_oracle_is_explicitly_non_deployable():
    rows = [
        {"case_id": "p", "score": .8, "technical_failure": False},
        {"case_id": "n", "score": .2, "technical_failure": False},
    ]
    result = diagnostics._oracle(rows, {"p": "POSITIVE", "n": "NEGATIVE"})
    assert result["feasible_75_75_threshold_count"] > 0
    assert result["retrospective_only_not_deployable"] is True


def test_diagnostic_rejects_tampered_predictions(tmp_path):
    root = _root(tmp_path)
    with (root / "predictions.jsonl").open("a", encoding="utf-8") as stream:
        stream.write("{}\n")
    with pytest.raises(PipelineError, match="alteradas"):
        diagnostics._load_prediction_root(root)
