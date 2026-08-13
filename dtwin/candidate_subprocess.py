"""Isolated Windows launcher for candidate localization."""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from .segmentation_subprocess import prepare_totalsegmentator_environment


def run_candidate_subprocess(
    *,
    case_dir: Path,
    request_path: Path,
    device: str,
    timeout_seconds: int,
    python_executable: str | None = None,
) -> subprocess.CompletedProcess:
    repo = Path(__file__).resolve().parents[1]
    launcher_root = Path(tempfile.gettempdir()) / "dtwin_candidate"
    launcher_root.mkdir(parents=True, exist_ok=True)
    launcher = launcher_root / "candidate_worker.py"
    shutil.copyfile(Path(__file__).with_name("candidate_worker.py"), launcher)
    environment = prepare_totalsegmentator_environment()
    return subprocess.run(
        [
            python_executable or sys.executable,
            str(launcher),
            str(repo),
            str(Path(case_dir).resolve()),
            device,
            str(Path(request_path).resolve()),
        ],
        cwd=launcher_root,
        env=environment,
        capture_output=True,
        text=True,
        timeout=int(timeout_seconds),
        check=False,
    )


def candidate_error(process: subprocess.CompletedProcess) -> str:
    for line in (process.stdout or "").splitlines() + (process.stderr or "").splitlines():
        if "CANDIDATE_FAIL:" in line:
            return line.split("CANDIDATE_FAIL:", 1)[1].strip()
    text = (process.stderr or process.stdout or "").strip()
    return text[-1000:] if text else f"código de saída {process.returncode}"
