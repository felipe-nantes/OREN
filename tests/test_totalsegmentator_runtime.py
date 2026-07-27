from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from dtwin.benchmark.totalsegmentator_runtime import (
    RUNTIME_GUARD_ID,
    configure_isolated_totalsegmentator_runtime,
)
from dtwin.core import PipelineError


def _weights(tmp_path: Path) -> Path:
    weights = tmp_path / "weights"
    (weights / "Dataset589_ct_mri_liver_lesions_750subj").mkdir(parents=True)
    return weights


def test_isolated_runtime_never_uses_global_config(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("TOTALSEG_HOME_DIR", raising=False)
    monkeypatch.delenv("TOTALSEG_WEIGHTS_PATH", raising=False)
    home = tmp_path / "runtime"
    weights = _weights(tmp_path)
    receipt = configure_isolated_totalsegmentator_runtime(
        home_dir=home, weights_dir=weights, runtime_id="argos_holdout_v21_test"
    )
    config = json.loads((home / "config.json").read_text(encoding="utf-8"))
    assert config == {
        "totalseg_id": "argos_holdout_v21_test",
        "send_usage_stats": False,
        "prediction_counter": 0,
    }
    assert receipt["runtime_guard"] == RUNTIME_GUARD_ID
    assert receipt["global_config_used"] is False
    assert os.environ["TOTALSEG_HOME_DIR"] == str(home.resolve())
    assert os.environ["TOTALSEG_WEIGHTS_PATH"] == str(weights.resolve())


def test_isolated_runtime_preserves_counter(tmp_path: Path):
    home = tmp_path / "runtime"
    home.mkdir()
    (home / "config.json").write_text(
        json.dumps({"totalseg_id": "old", "send_usage_stats": True, "prediction_counter": 9}),
        encoding="utf-8",
    )
    receipt = configure_isolated_totalsegmentator_runtime(
        home_dir=home, weights_dir=_weights(tmp_path), runtime_id="new"
    )
    config = json.loads((home / "config.json").read_text(encoding="utf-8"))
    assert config["prediction_counter"] == 9
    assert config["send_usage_stats"] is False
    assert config["totalseg_id"] == "new"
    assert receipt["prediction_counter_before_run"] == 9


def test_isolated_runtime_recovers_corrupt_config_with_backup(tmp_path: Path):
    home = tmp_path / "runtime"
    home.mkdir()
    (home / "config.json").write_bytes(b"\x00" * 149)
    receipt = configure_isolated_totalsegmentator_runtime(
        home_dir=home, weights_dir=_weights(tmp_path), runtime_id="recovered"
    )
    assert receipt["invalid_isolated_config_recovered"] is True
    assert len(list(home.glob("config.invalid.*.bin"))) == 1
    assert json.loads((home / "config.json").read_text(encoding="utf-8"))["totalseg_id"] == "recovered"


def test_isolated_runtime_requires_dataset589_weights(tmp_path: Path):
    weights = tmp_path / "weights"
    weights.mkdir()
    with pytest.raises(PipelineError, match="Dataset589"):
        configure_isolated_totalsegmentator_runtime(
            home_dir=tmp_path / "runtime", weights_dir=weights, runtime_id="missing"
        )
