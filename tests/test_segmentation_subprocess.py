from __future__ import annotations

import json
from pathlib import Path

from dtwin.segmentation_subprocess import prepare_totalsegmentator_environment


def _base_environment(weights: Path) -> dict[str, str]:
    weights.mkdir(parents=True)
    return {"TOTALSEG_WEIGHTS_PATH": str(weights)}


def test_runtime_is_isolated_and_reuses_installed_weights(tmp_path: Path):
    weights = tmp_path / "weights"
    runtime = tmp_path / "runtime"
    environment = prepare_totalsegmentator_environment(
        runtime_root=runtime,
        base_environment=_base_environment(weights),
    )

    assert environment["TOTALSEG_HOME_DIR"] == str(runtime.resolve())
    assert environment["TOTALSEG_WEIGHTS_PATH"] == str(weights.resolve())
    assert json.loads((runtime / "config.json").read_text(encoding="utf-8")) == {
        "prediction_counter": 0,
        "send_usage_stats": False,
        "totalseg_id": "argos_webapp_local",
    }


def test_runtime_recovers_nul_corruption_and_preserves_evidence(tmp_path: Path):
    weights = tmp_path / "weights"
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    (runtime / "config.json").write_bytes(b"\x00" * 149)

    prepare_totalsegmentator_environment(
        runtime_root=runtime,
        base_environment=_base_environment(weights),
    )

    assert json.loads((runtime / "config.json").read_text(encoding="utf-8"))[
        "totalseg_id"
    ] == "argos_webapp_local"
    backups = list(runtime.glob("config.invalid.*.bin"))
    assert len(backups) == 1
    assert backups[0].read_bytes() == b"\x00" * 149


def test_runtime_preserves_valid_prediction_counter(tmp_path: Path):
    weights = tmp_path / "weights"
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    (runtime / "config.json").write_text(
        json.dumps({"prediction_counter": 12, "send_usage_stats": True}),
        encoding="utf-8",
    )

    prepare_totalsegmentator_environment(
        runtime_root=runtime,
        base_environment=_base_environment(weights),
    )

    config = json.loads((runtime / "config.json").read_text(encoding="utf-8"))
    assert config["prediction_counter"] == 12
    assert config["send_usage_stats"] is False
