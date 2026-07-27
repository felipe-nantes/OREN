"""Isolated TotalSegmentator runtime configuration for reproducible benchmarks."""
from __future__ import annotations

import json
import os
import uuid
from pathlib import Path
from typing import Any

from dtwin.core import PipelineError


RUNTIME_GUARD_ID = "totalsegmentator_isolated_runtime_v1"


def _atomic_json(path: Path, value: dict[str, Any]) -> None:
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex[:8]}.tmp")
    try:
        temporary.write_text(
            json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def configure_isolated_totalsegmentator_runtime(
    *, home_dir: Path, weights_dir: Path, runtime_id: str
) -> dict[str, Any]:
    """Avoid the mutable global config while reusing installed weights read-only."""

    home = Path(home_dir).resolve()
    weights = Path(weights_dir).resolve()
    runtime_id = str(runtime_id).strip()
    if not runtime_id or len(runtime_id) > 80:
        raise PipelineError("ID do runtime isolado TotalSegmentator invalido.")
    if not weights.is_dir() or not any(weights.glob("Dataset589*")):
        raise PipelineError("Pesos Dataset589 do localizador nao foram encontrados.")
    home.mkdir(parents=True, exist_ok=True)
    config_path = home / "config.json"
    recovered_invalid = False
    prediction_counter = 0
    if config_path.exists():
        try:
            current = json.loads(config_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            current = None
        if isinstance(current, dict):
            current_counter = current.get("prediction_counter", 0)
            if (
                isinstance(current_counter, int)
                and not isinstance(current_counter, bool)
                and current_counter >= 0
            ):
                prediction_counter = current_counter
        else:
            backup = home / f"config.invalid.{uuid.uuid4().hex[:8]}.bin"
            try:
                backup.write_bytes(config_path.read_bytes())
            except OSError as exc:
                raise PipelineError("Nao foi possivel preservar config isolado invalido.") from exc
            recovered_invalid = True
    config = {
        "totalseg_id": runtime_id,
        "send_usage_stats": False,
        "prediction_counter": prediction_counter,
    }
    _atomic_json(config_path, config)
    os.environ["TOTALSEG_HOME_DIR"] = str(home)
    os.environ["TOTALSEG_WEIGHTS_PATH"] = str(weights)
    return {
        "runtime_guard": RUNTIME_GUARD_ID,
        "home_dir": str(home),
        "weights_dir": str(weights),
        "config_path": str(config_path),
        "runtime_id": runtime_id,
        "prediction_counter_before_run": prediction_counter,
        "invalid_isolated_config_recovered": recovered_invalid,
        "global_config_used": False,
        "send_usage_stats": False,
    }
