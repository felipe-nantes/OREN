from __future__ import annotations

import subprocess
from pathlib import Path

from dtwin.candidate_subprocess import run_candidate_subprocess


def test_candidate_subprocess_uses_crash_resilient_totalsegmentator_runtime(
    tmp_path: Path, monkeypatch
):
    weights = tmp_path / "weights"
    weights.mkdir()
    runtime = tmp_path / "runtime"
    monkeypatch.setenv("TOTALSEG_WEIGHTS_PATH", str(weights))
    monkeypatch.setenv("ARGOS_TOTALSEG_RUNTIME_DIR", str(runtime))
    captured = {}

    def fake_run(command, **kwargs):
        captured.update(kwargs)
        return subprocess.CompletedProcess(command, 0, "CANDIDATE_OK", "")

    monkeypatch.setattr(subprocess, "run", fake_run)
    run_candidate_subprocess(
        case_dir=tmp_path / "case",
        request_path=tmp_path / "request.json",
        device="gpu",
        timeout_seconds=10,
        python_executable="python",
    )

    assert captured["env"]["TOTALSEG_HOME_DIR"] == str(runtime.resolve())
    assert (runtime / "config.json").is_file()
