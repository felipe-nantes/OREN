"""Execução compartilhada da segmentação isolada do cwd transacional no Windows."""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


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
    return subprocess.run(
        command,
        cwd=launcher_root,
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
