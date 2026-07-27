from __future__ import annotations

import pytest

from dtwin.core import PipelineError
from dtwin.learning import environment


def test_environment_report_blocks_busy_gpu(monkeypatch, tmp_path):
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
