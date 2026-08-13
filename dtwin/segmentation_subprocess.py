"""Execução compartilhada da segmentação isolada do cwd transacional no Windows."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path


def _atomic_json(path: Path, value: dict[str, object]) -> None:
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex[:8]}.tmp")
    try:
        temporary.write_text(
            json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def prepare_totalsegmentator_environment(
    *, runtime_root: Path | None = None, base_environment: dict[str, str] | None = None
) -> dict[str, str]:
    """Return a crash-resilient, isolated TotalSegmentator environment.

    TotalSegmentator updates ``config.json`` in place. An abrupt Windows shutdown
    can therefore leave the global file filled with NUL bytes and make every
    subsequent segmentation fail while parsing JSON. ARGOS repairs an isolated
    runtime before every invocation and reuses only the installed model weights.
    """

    environment = dict(base_environment or os.environ)
    global_home = Path.home() / ".totalsegmentator"
    weights = Path(
        environment.get("TOTALSEG_WEIGHTS_PATH")
        or global_home / "nnunet" / "results"
    ).resolve()
    if not weights.is_dir():
        raise RuntimeError(f"Pesos do TotalSegmentator nao encontrados: {weights}")

    home = Path(
        runtime_root
        or environment.get("ARGOS_TOTALSEG_RUNTIME_DIR")
        or (Path(tempfile.gettempdir()) / "argos_totalsegmentator_runtime")
    ).resolve()
    home.mkdir(parents=True, exist_ok=True)
    config_path = home / "config.json"
    counter = 0
    valid = False
    if config_path.exists():
        try:
            current = json.loads(config_path.read_text(encoding="utf-8"))
            valid = isinstance(current, dict)
            current_counter = current.get("prediction_counter", 0) if valid else 0
            if isinstance(current_counter, int) and not isinstance(current_counter, bool):
                counter = max(0, current_counter)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            valid = False
        if not valid:
            backup = home / f"config.invalid.{uuid.uuid4().hex[:8]}.bin"
            shutil.copyfile(config_path, backup)

    _atomic_json(
        config_path,
        {
            "totalseg_id": "argos_webapp_local",
            "send_usage_stats": False,
            "prediction_counter": counter,
        },
    )
    environment["TOTALSEG_HOME_DIR"] = str(home)
    environment["TOTALSEG_WEIGHTS_PATH"] = str(weights)
    return environment


def run_segmentation_subprocess(
    *,
    dicom_dir: Path,
    case_dir: Path,
    profile_path: Path,
    device: str,
    fast: bool,
    timeout_seconds: int,
    python_executable: str | None = None,
) -> subprocess.CompletedProcess:
    repo = Path(__file__).resolve().parents[1]
    launcher_root = Path(tempfile.gettempdir()) / "dtwin_segmentation"
    launcher_root.mkdir(parents=True, exist_ok=True)
    launcher = launcher_root / "seg_worker.py"
    shutil.copyfile(Path(__file__).with_name("seg_worker.py"), launcher)
    command = [
        python_executable or sys.executable,
        str(launcher),
        str(repo),
        str(Path(profile_path).resolve()),
        str(Path(dicom_dir).resolve()),
        str(Path(case_dir).resolve()),
        device,
        "1" if fast else "0",
    ]
    environment = prepare_totalsegmentator_environment()
    return subprocess.run(
        command,
        cwd=launcher_root,
        env=environment,
        capture_output=True,
        text=True,
        timeout=int(timeout_seconds),
        check=False,
    )


def segmentation_error(process: subprocess.CompletedProcess) -> str:
    for line in (process.stdout or "").splitlines() + (process.stderr or "").splitlines():
        if "PREP_FAIL:" in line:
            return line.split("PREP_FAIL:", 1)[1].strip()
    text = (process.stderr or process.stdout or "").strip()
    return text[-1000:] if text else f"código de saída {process.returncode}"
