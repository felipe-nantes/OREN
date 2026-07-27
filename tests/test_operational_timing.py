import json
from pathlib import Path
import subprocess

import numpy as np
import pytest
import SimpleITK as sitk

from dtwin.benchmark.operational_timing import (
    SCHEMA,
    build_operational_timing,
    persist_operational_timing,
)
from webapp import server


def _timing(**overrides):
    values = {
        "job_id": "abc123",
        "analysis_scenario": "fast_pathology",
        "medgemma_config": "configs/medgemma_local_4b_fast_pathology.yaml",
        "medgemma_config_sha256": "a" * 64,
        "started_at_utc": "2026-07-15T10:00:00+00:00",
        "finished_at_utc": "2026-07-15T10:03:00+00:00",
        "durations_seconds": {
            "preparation_and_segmentation": 40.0,
            "medgemma_inference": 130.0,
            "time_to_report": 180.0,
            "total_with_3d": 180.0,
        },
        "outcome": "completed",
        "report_available": True,
        "viewer_ready": True,
        "failure_stage": None,
        "segmentation_device": "gpu",
    }
    values.update(overrides)
    return build_operational_timing(**values)


def test_operational_timing_gate_uses_exact_unrounded_180_seconds():
    exactly = _timing()
    above = _timing(durations_seconds={"time_to_report": 180.0001, "total_with_3d": 180.0001})

    assert exactly["time_budget"]["time_to_report_within_budget"] is True
    assert exactly["time_budget"]["total_with_3d_within_budget"] is True
    assert above["time_budget"]["time_to_report_within_budget"] is False
    assert above["time_budget"]["total_with_3d_within_budget"] is False


def test_operational_timing_without_report_never_passes_budget():
    payload = _timing(
        durations_seconds={"total_with_3d": 12.0},
        outcome="not_completed",
        report_available=False,
        viewer_ready=False,
        failure_stage="preparation_and_segmentation",
    )

    assert payload["time_budget"]["time_to_report_within_budget"] is None
    assert payload["time_budget"]["total_with_3d_within_budget"] is False
    assert payload["safety"]["ground_truth_read"] is False
    assert payload["safety"]["raw_paths_persisted"] is False
    assert payload["safety"]["raw_uids_persisted"] is False


@pytest.mark.parametrize("invalid", [-0.1, float("nan"), float("inf")])
def test_operational_timing_rejects_invalid_durations(invalid):
    with pytest.raises(ValueError, match="Duração inválida"):
        _timing(durations_seconds={"time_to_report": invalid})


def test_operational_timing_is_persisted_atomically(tmp_path):
    payload = _timing()
    output = persist_operational_timing(tmp_path, payload)

    assert output == tmp_path / "outputs" / "operational_timing.json"
    assert json.loads(output.read_text("utf-8"))["schema"] == SCHEMA
    assert not output.with_name(f".{output.name}.tmp").exists()


def _write_segmentation_artifacts(case_dir: Path) -> None:
    case_dir.mkdir(parents=True, exist_ok=True)
    volume = sitk.GetImageFromArray(np.ones((5, 8, 8), dtype=np.float32))
    mask = sitk.GetImageFromArray(np.ones((5, 8, 8), dtype=np.uint8))
    sitk.WriteImage(volume, str(case_dir / "volume.nii.gz"))
    sitk.WriteImage(mask, str(case_dir / "mask_organ.nii.gz"))


def test_individual_dicom_flow_persists_success_timing(monkeypatch, tmp_path):
    workspace = tmp_path / "workspace"
    raw_dir = workspace / "abc123" / "_upload"
    raw_dir.mkdir(parents=True)
    source = raw_dir / "source.dcm"
    source.write_bytes(b"synthetic")
    monkeypatch.setattr(server, "WORKSPACE", workspace)
    monkeypatch.setattr(server, "find_best_series", lambda _root: ([str(source)], 5))

    def fake_segment(_series_dir, case_dir, _device, _timeout, *, fast):
        assert fast is False
        _write_segmentation_artifacts(Path(case_dir))
        return subprocess.CompletedProcess(["segment"], 0, "", "")

    def fake_series_selection(case_dir, _files):
        output = Path(case_dir) / "outputs" / "series_selection.json"
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text("{}", encoding="utf-8")
        return output

    def fake_screening(_cmd, timeout, cwd=None):
        del timeout, cwd
        report = workspace / "abc123" / "case" / "outputs" / "medgemma" / "medgemma_report.json"
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(json.dumps({
            "status": "pending_review",
            "report": {
                "resultado_hipotese": "NEGATIVA",
                "confianca": "moderada",
                "necessidade_de_revisao_humana": True,
            },
            "durations_seconds": {
                "panel_generation": 1.0,
                "rag_retrieval": 0.0,
                "medgemma_inference": 2.0,
                "screening_total": 3.0,
            },
        }), encoding="utf-8")
        return subprocess.CompletedProcess(["screen"], 0, "", "")

    monkeypatch.setattr(server, "_segment", fake_segment)
    monkeypatch.setattr(server, "_persist_series_selection", fake_series_selection)
    monkeypatch.setattr(server, "_run", fake_screening)
    monkeypatch.setattr(server, "_build_model", lambda _case_dir: (True, ""))
    server._jobs["abc123"] = {
        "state": "queued", "step": "recebendo", "progress": 5, "result": None,
    }

    server.process_job(
        "abc123",
        raw_dir,
        server.FAST_PATHOLOGY_MEDGEMMA_CONFIG,
        "fast_pathology",
    )

    job = server._jobs.pop("abc123")
    timing = job["operational_timing"]
    artifact = workspace / "abc123" / job["operational_timing_artifact"]
    assert job["state"] == "done"
    assert job["result"]["status"] == "concluido"
    assert timing["outcome"] == "completed"
    assert timing["report_available"] is True
    assert timing["viewer_ready"] is True
    assert timing["time_budget"]["time_to_report_within_budget"] is True
    assert timing["durations_seconds"]["medgemma_inference"] == 2.0
    assert timing["model"]["parameter_scale"] == "4B"
    assert len(timing["model"]["config_sha256"]) == 64
    assert artifact.is_file()
    assert json.loads(artifact.read_text("utf-8")) == timing


def test_individual_dicom_flow_persists_early_failure_timing(monkeypatch, tmp_path):
    workspace = tmp_path / "workspace"
    raw_dir = workspace / "def456" / "_upload"
    raw_dir.mkdir(parents=True)
    monkeypatch.setattr(server, "WORKSPACE", workspace)
    monkeypatch.setattr(server, "find_best_series", lambda _root: ([], 0))
    server._jobs["def456"] = {
        "state": "queued", "step": "recebendo", "progress": 5, "result": None,
    }

    server.process_job(
        "def456",
        raw_dir,
        server.FAST_PATHOLOGY_MEDGEMMA_CONFIG,
        "fast_pathology",
    )

    job = server._jobs.pop("def456")
    timing = job["operational_timing"]
    assert job["state"] == "done"
    assert job["result"]["status"] == "nao_concluido"
    assert timing["outcome"] == "not_completed"
    assert timing["failure_stage"] == "series_selection_and_copy"
    assert timing["report_available"] is False
    assert "time_to_report" not in timing["durations_seconds"]
    assert (workspace / "def456" / "case" / "outputs" / "operational_timing.json").is_file()
