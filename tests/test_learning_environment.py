from __future__ import annotations

from types import SimpleNamespace

import pytest

from dtwin.core import PipelineError
from dtwin.learning import environment


def _mock_disk(monkeypatch, free_gib: float) -> None:
    # O relatório mede o disco REAL via shutil.disk_usage; sem este mock o
    # teste unitário herda o estado da máquina (TEST-01/W-011: a "falha
    # ambiental de GPU" dos portões disparava também com C: abaixo de 20 GiB).
    gib = 1024**3
    monkeypatch.setattr(
        environment.shutil,
        "disk_usage",
        lambda _root: SimpleNamespace(
            total=500 * gib, used=int((500 - free_gib) * gib), free=int(free_gib * gib)
        ),
    )


def test_environment_report_blocks_busy_gpu(monkeypatch, tmp_path):
    _mock_disk(monkeypatch, free_gib=400.0)
    monkeypatch.setattr(
        environment,
        "module_versions",
        lambda names: {name: "test" for name in names},
    )
    monkeypatch.setattr(
        environment,
        "query_gpu",
        lambda: environment.GpuStatus(
            name="GPU",
            memory_total_mib=8192,
            memory_used_mib=7900,
            memory_free_mib=292,
            driver_version="test",
        ),
    )
    report = environment.build_environment_report(tmp_path)
    assert report["training_ready"] is False
    assert any("gpu_busy" in value for value in report["blockers"])
    with pytest.raises(PipelineError, match="não está pronto"):
        environment.require_training_ready(report)


def test_environment_report_accepts_free_gpu(monkeypatch, tmp_path):
    _mock_disk(monkeypatch, free_gib=400.0)
    monkeypatch.setattr(
        environment,
        "module_versions",
        lambda names: {name: "test" for name in names},
    )
    monkeypatch.setattr(
        environment,
        "query_gpu",
        lambda: environment.GpuStatus(
            name="GPU",
            memory_total_mib=8192,
            memory_used_mib=512,
            memory_free_mib=7680,
            driver_version="test",
        ),
    )
    report = environment.build_environment_report(tmp_path)
    assert report["training_ready"] is True
    environment.require_training_ready(report)


def test_environment_report_detects_missing_module(monkeypatch, tmp_path):
    _mock_disk(monkeypatch, free_gib=400.0)
    monkeypatch.setattr(
        environment,
        "module_versions",
        lambda names: {
            name: (None if name == "sklearn" else "test") for name in names
        },
    )
    monkeypatch.setattr(
        environment,
        "query_gpu",
        lambda: environment.GpuStatus(
            name="GPU",
            memory_total_mib=8192,
            memory_used_mib=0,
            memory_free_mib=8192,
            driver_version="test",
        ),
    )
    report = environment.build_environment_report(tmp_path)
    assert "missing_training_modules:sklearn" in report["blockers"]


def test_environment_report_blocks_insufficient_disk(monkeypatch, tmp_path):
    _mock_disk(monkeypatch, free_gib=environment.DISK_MINIMUM_FREE_GIB - 1.0)
    monkeypatch.setattr(
        environment,
        "module_versions",
        lambda names: {name: "test" for name in names},
    )
    monkeypatch.setattr(
        environment,
        "query_gpu",
        lambda: environment.GpuStatus(
            name="GPU",
            memory_total_mib=8192,
            memory_used_mib=512,
            memory_free_mib=7680,
            driver_version="test",
        ),
    )
    report = environment.build_environment_report(tmp_path)
    assert report["training_ready"] is False
    assert report["blockers"] == ["insufficient_disk_space"]
    with pytest.raises(PipelineError, match="não está pronto"):
        environment.require_training_ready(report)
