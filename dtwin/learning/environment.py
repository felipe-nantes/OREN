"""Read-only environment preflight for supervised ARGOS experiments."""
from __future__ import annotations

import importlib
import json
import platform
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dtwin.core import PipelineError


REQUIRED_TRAINING_MODULES = ("joblib", "pandas", "sklearn")
GPU_MINIMUM_FREE_MIB = 6144
DISK_MINIMUM_FREE_GIB = 20.0


@dataclass(frozen=True)
class GpuStatus:
    name: str
    memory_total_mib: int
    memory_used_mib: int
    memory_free_mib: int
    driver_version: str

    def to_json(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "memory_total_mib": self.memory_total_mib,
            "memory_used_mib": self.memory_used_mib,
            "memory_free_mib": self.memory_free_mib,
            "driver_version": self.driver_version,
        }


def module_versions(
    names: tuple[str, ...] = REQUIRED_TRAINING_MODULES,
) -> dict[str, str | None]:
    result: dict[str, str | None] = {}
    for name in names:
        try:
            module = importlib.import_module(name)
        except ImportError:
            result[name] = None
        else:
            result[name] = str(getattr(module, "__version__", "unknown"))
    return result


def query_gpu() -> GpuStatus | None:
    executable = shutil.which("nvidia-smi")
    if executable is None:
        return None
    command = [
        executable,
        "--query-gpu=name,memory.total,memory.used,memory.free,driver_version",
        "--format=csv,noheader,nounits",
    ]
    try:
        completed = subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    line = next(
        (item.strip() for item in completed.stdout.splitlines() if item.strip()),
        "",
    )
    parts = [part.strip() for part in line.split(",")]
    if len(parts) != 5:
        return None
    try:
        return GpuStatus(
            name=parts[0],
            memory_total_mib=int(parts[1]),
            memory_used_mib=int(parts[2]),
            memory_free_mib=int(parts[3]),
            driver_version=parts[4],
        )
    except ValueError:
        return None


def build_environment_report(workspace_root: Path) -> dict[str, Any]:
    root = Path(workspace_root).resolve()
    usage = shutil.disk_usage(root)
    versions = module_versions(
        REQUIRED_TRAINING_MODULES + ("torch", "transformers")
    )
    gpu = query_gpu()
    blockers: list[str] = []
    missing = [
        name
        for name in REQUIRED_TRAINING_MODULES
        if versions.get(name) is None
    ]
    if missing:
        blockers.append(f"missing_training_modules:{','.join(missing)}")
    free_gib = usage.free / (1024**3)
    if free_gib < DISK_MINIMUM_FREE_GIB:
        blockers.append("insufficient_disk_space")
    if gpu is None:
        blockers.append("nvidia_gpu_unavailable")
    elif gpu.memory_free_mib < GPU_MINIMUM_FREE_MIB:
        blockers.append(
            "gpu_busy_stop_medgemma_before_training_or_embedding_extraction"
        )
    report = {
        "schema": "argos-hybrid-training-environment-v1",
        "python": {
            "version": platform.python_version(),
            "executable": sys.executable,
            "implementation": platform.python_implementation(),
        },
        "platform": platform.platform(),
        "workspace_root": str(root),
        "disk": {
            "free_gib": round(free_gib, 3),
            "minimum_free_gib": DISK_MINIMUM_FREE_GIB,
        },
        "modules": versions,
        "gpu": gpu.to_json() if gpu else None,
        "gpu_minimum_free_mib": GPU_MINIMUM_FREE_MIB,
        "training_ready": not blockers,
        "blockers": blockers,
        "notes": [
            "Only one GPU-heavy model may be resident at a time.",
            "Stop the MedGemma gateway before training or embedding extraction.",
            "This preflight does not download models or mutate the environment.",
        ],
    }
    return report


def require_training_ready(report: dict[str, Any]) -> None:
    if report.get("training_ready") is not True:
        raise PipelineError(
            "Ambiente não está pronto para treino: "
            + json.dumps(report.get("blockers") or [], ensure_ascii=False)
        )
