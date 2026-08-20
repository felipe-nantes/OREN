"""Durable full-resolution TotalSegmentator liver runner for offline cohorts."""
from __future__ import annotations

import json
import os
import subprocess
import time
import uuid
from pathlib import Path
from typing import Any

import numpy as np

from dtwin.benchmark.mrsegmentator_chaos_runner import (
    _checkpoint,
    _terminate_tree,
    cuda_preflight,
    gpu_memory_used_mb,
)
from dtwin.core import PipelineError, now_utc, sha256_of
from dtwin.segmentation_contract import validate_visualization_mask

RUN_SCHEMA = "argos-totalsegmentator-liver-cohort-gpu-run-v2"
CASE_SCHEMA = "argos-totalsegmentator-liver-cohort-gpu-case-v2"


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex[:8]}.tmp")
    try:
        with temporary.open("w", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def run_case(
    *,
    source: Path,
    case_id: str,
    python_exe: Path,
    worker: Path,
    staging: Path,
    timeout_seconds: int,
) -> dict[str, Any]:
    mask = staging / "masks" / f"{case_id}.nii.gz"
    mask.parent.mkdir(parents=True, exist_ok=True)
    receipt = staging / "receipts" / f"{case_id}.json"
    receipt.parent.mkdir(parents=True, exist_ok=True)
    stdout_path = staging / "logs" / f"{case_id}.stdout.log"
    stderr_path = staging / "logs" / f"{case_id}.stderr.log"
    stdout_path.parent.mkdir(parents=True, exist_ok=True)
    command = [
        str(python_exe),
        str(worker),
        "--source",
        str(source),
        "--output",
        str(mask),
        "--receipt",
        str(receipt),
        "--label",
        "liver",
        "--device",
        "gpu",
    ]
    baseline_memory = gpu_memory_used_mb()
    peak_memory = baseline_memory
    started = time.perf_counter()
    with stdout_path.open("w", encoding="utf-8") as stdout, stderr_path.open(
        "w", encoding="utf-8"
    ) as stderr:
        process = subprocess.Popen(command, stdout=stdout, stderr=stderr, cwd=staging.parent)
        while process.poll() is None:
            elapsed = time.perf_counter() - started
            if elapsed > timeout_seconds:
                _terminate_tree(process)
                process.wait(timeout=30)
                mask.unlink(missing_ok=True)
                receipt.unlink(missing_ok=True)
                raise PipelineError(f"total_mr excedeu timeout de {timeout_seconds}s.")
            current = gpu_memory_used_mb()
            if current is not None:
                peak_memory = current if peak_memory is None else max(peak_memory, current)
            time.sleep(0.5)
    elapsed = time.perf_counter() - started
    if process.returncode != 0:
        detail = stderr_path.read_text(encoding="utf-8", errors="replace")[-1200:]
        raise PipelineError(f"total_mr falhou ({process.returncode}): {detail}")
    if not mask.is_file() or not receipt.is_file():
        raise PipelineError("total_mr terminou sem mascara ou recibo.")
    try:
        worker_receipt = json.loads(receipt.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PipelineError("Recibo total_mr invalido.") from exc
    quality = validate_visualization_mask(mask, source)
    return {
        "schema": CASE_SCHEMA,
        "case_id": case_id,
        "status": "completed",
        "source_sha256": sha256_of(source),
        "mask_sha256": sha256_of(mask),
        "receipt_sha256": sha256_of(receipt),
        "mask": quality,
        "worker_receipt": worker_receipt,
        "elapsed_seconds": round(float(elapsed), 6),
        "gpu_memory_baseline_mb": baseline_memory,
        "gpu_memory_peak_mb": peak_memory,
        "gpu_memory_delta_mb": (
            peak_memory - baseline_memory
            if peak_memory is not None and baseline_memory is not None
            else None
        ),
        "mode": "total_mr_roi_liver_full_resolution_gpu",
        "timeout_seconds": int(timeout_seconds),
    }


def run_cohort(
    *,
    cohort_root: Path | str,
    output_root: Path | str,
    python_exe: Path | str,
    worker: Path | str,
    source_name: str,
    timeout_seconds: int = 180,
) -> dict[str, Any]:
    cohort = Path(cohort_root).resolve()
    output = Path(output_root).resolve()
    python = Path(python_exe).resolve()
    worker_path = Path(worker).resolve()
    if not cohort.is_dir() or not python.is_file() or not worker_path.is_file():
        raise PipelineError("Coorte, Python ou worker total_mr ausente.")
    if output.exists():
        raise PipelineError("Saida total_mr final ja existe; sobrescrita recusada.")
    if not source_name or Path(source_name).name != source_name:
        raise PipelineError("Nome da fonte total_mr invalido.")
    if timeout_seconds < 30:
        raise PipelineError("Timeout total_mr excessivamente curto.")
    cases = sorted(path for path in cohort.iterdir() if path.is_dir())
    sources = [(case.name, case / source_name) for case in cases]
    if not sources or any(not source.is_file() for _, source in sources):
        raise PipelineError("Coorte incompleta para total_mr.")
    cuda = cuda_preflight(python)
    staging = output.with_name(f".{output.name}.incomplete")
    staging.mkdir(parents=True, exist_ok=True)
    context_path = staging / "run_context.json"
    context = {
        "schema": RUN_SCHEMA,
        "case_ids": [case_id for case_id, _ in sources],
        "case_count": len(sources),
        "source_name": source_name,
        "mode": "total_mr_roi_liver_full_resolution_gpu",
        "timeout_seconds": int(timeout_seconds),
        "cuda": cuda,
        "ground_truth_read": False,
        "lesion_masks_read": 0,
        "production_files_written": False,
    }
    if context_path.is_file():
        if json.loads(context_path.read_text(encoding="utf-8")) != context:
            raise PipelineError("Checkpoint total_mr pertence a outro protocolo.")
    else:
        _atomic_json(context_path, context)
    checkpoint_path = staging / "checkpoint_cases.jsonl"
    if checkpoint_path.is_file():
        rows = [
            json.loads(line)
            for line in checkpoint_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    else:
        rows: list[dict[str, Any]] = []
        checkpoint_path.write_text("", encoding="utf-8")
    if [row.get("case_id") for row in rows] != context["case_ids"][: len(rows)]:
        raise PipelineError("Ordem do checkpoint total_mr invalida.")
    for row in rows:
        mask = staging / "masks" / f"{row['case_id']}.nii.gz"
        receipt = staging / "receipts" / f"{row['case_id']}.json"
        if (
            row.get("status") != "completed"
            or not mask.is_file()
            or not receipt.is_file()
            or sha256_of(mask) != row.get("mask_sha256")
            or sha256_of(receipt) != row.get("receipt_sha256")
        ):
            raise PipelineError("Checkpoint total_mr adulterado ou incompleto.")
    for case_id, source in sources[len(rows) :]:
        row = run_case(
            source=source,
            case_id=case_id,
            python_exe=python,
            worker=worker_path,
            staging=staging,
            timeout_seconds=timeout_seconds,
        )
        rows.append(row)
        _checkpoint(checkpoint_path, rows)
    elapsed_values = [float(row["elapsed_seconds"]) for row in rows]
    summary = {
        **context,
        "completed_utc": now_utc(),
        "completed_cases": len(rows),
        "technical_failures": 0,
        "median_elapsed_seconds": round(float(np.median(elapsed_values)), 6),
        "maximum_elapsed_seconds": round(float(max(elapsed_values)), 6),
        "maximum_gpu_memory_peak_mb": max(
            int(row["gpu_memory_peak_mb"])
            for row in rows
            if row["gpu_memory_peak_mb"] is not None
        ),
        "checkpoint_sha256": sha256_of(checkpoint_path),
    }
    _atomic_json(staging / "run_summary.json", summary)
    os.replace(staging, output)
    return summary


def verify_run(output_root: Path | str) -> dict[str, Any]:
    root = Path(output_root).resolve()
    try:
        context = json.loads((root / "run_context.json").read_text(encoding="utf-8"))
        summary = json.loads((root / "run_summary.json").read_text(encoding="utf-8"))
        rows = [
            json.loads(line)
            for line in (root / "checkpoint_cases.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    except (OSError, json.JSONDecodeError) as exc:
        raise PipelineError("Execucao total_mr ausente ou invalida.") from exc
    if context.get("schema") != RUN_SCHEMA or summary.get("schema") != RUN_SCHEMA:
        raise PipelineError("Schema da execucao total_mr invalido.")
    if len(rows) != context.get("case_count") or len(rows) != summary.get("completed_cases"):
        raise PipelineError("Contagem total_mr divergente.")
    if sha256_of(root / "checkpoint_cases.jsonl") != summary.get("checkpoint_sha256"):
        raise PipelineError("Checkpoint total_mr adulterado.")
    for row in rows:
        mask = root / "masks" / f"{row['case_id']}.nii.gz"
        receipt = root / "receipts" / f"{row['case_id']}.json"
        if not mask.is_file() or not receipt.is_file():
            raise PipelineError("Artefato total_mr ausente.")
        if sha256_of(mask) != row.get("mask_sha256") or sha256_of(receipt) != row.get("receipt_sha256"):
            raise PipelineError("Hash total_mr divergente.")
    return summary


__all__ = ["RUN_SCHEMA", "CASE_SCHEMA", "run_case", "run_cohort", "verify_run"]
