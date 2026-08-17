import os
from pathlib import Path

import pytest

from webapp import server


@pytest.mark.skipif(
    os.name != "nt",
    reason="assert espera separador Windows literal ('case\\\\outputs\\\\...'); em POSIX o servidor produz 'case/outputs/...'",
)
def test_relative_workspace_still_exposes_operational_timing_artifact(monkeypatch, tmp_path):
    """Regressão do smoke real: timing_path é absoluto e WORKSPACE pode ser relativo."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(server, "WORKSPACE", Path("workspace"))
    monkeypatch.setattr(server, "find_best_series", lambda _root: ([], 0))
    job_id = "ab1800000002"
    raw_dir = Path("workspace") / job_id / "_upload"
    raw_dir.mkdir(parents=True)
    server._jobs[job_id] = {
        "state": "queued", "step": "recebendo", "progress": 5, "result": None,
    }

    server.process_job(
        job_id,
        raw_dir,
        server.FAST_PATHOLOGY_MEDGEMMA_CONFIG,
        "fast_pathology",
    )

    job = server._jobs.pop(job_id)
    assert job["operational_timing_artifact"] == "case\\outputs\\operational_timing.json"
    assert job["operational_timing"]["outcome"] == "not_completed"
    assert (
        tmp_path / "workspace" / job_id / job["operational_timing_artifact"]
    ).is_file()
