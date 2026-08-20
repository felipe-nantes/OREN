"""Durable, GPU-only MRSegmentator runner for the frozen CHAOS comparison."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
import uuid
from pathlib import Path
from typing import Any

import numpy as np
import SimpleITK as sitk

from dtwin.core import PipelineError, now_utc, sha256_of
from dtwin.segmentation_contract import same_geometry, validate_visualization_mask

RUN_SCHEMA = "argos-mrsegmentator-chaos-gpu-run-v2"
CASE_SCHEMA = "argos-mrsegmentator-chaos-gpu-case-v2"
LIVER_LABEL = 5


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


def _checkpoint(path: Path, rows: list[dict[str, Any]]) -> None:
    payload = "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex[:8]}.tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    # Parse before publishing so a truncated generation can never replace the checkpoint.
    try:
        parsed = [json.loads(line) for line in temporary.read_text(encoding="utf-8").splitlines()]
    except (OSError, json.JSONDecodeError) as exc:
        temporary.unlink(missing_ok=True)
        raise PipelineError("Checkpoint MRSegmentator invalido antes da publicacao.") from exc
    if len(parsed) != len(rows):
        temporary.unlink(missing_ok=True)
        raise PipelineError("Checkpoint MRSegmentator truncado.")
    backup = path.with_name("checkpoint_cases.backup.jsonl")
    if path.is_file():
        shutil.copyfile(path, backup)
    os.replace(temporary, path)


def extract_liver_label(
    labelmap_path: Path | str, source_path: Path | str, output_path: Path | str
) -> dict[str, Any]:
    labelmap_path = Path(labelmap_path).resolve()
    source_path = Path(source_path).resolve()
    output_path = Path(output_path).resolve()
    try:
        labelmap = sitk.ReadImage(str(labelmap_path))
        source = sitk.ReadImage(str(source_path))
    except Exception as exc:
        raise PipelineError(f"Falha ao ler saida MRSegmentator: {exc}") from exc
    liver = sitk.Cast(labelmap == LIVER_LABEL, sitk.sitkUInt8)
    resampled = not same_geometry(liver, source)
    if resampled:
        liver = sitk.Resample(
            liver,
            source,
            sitk.Transform(),
            sitk.sitkNearestNeighbor,
            0,
            sitk.sitkUInt8,
        )
    voxels = int((sitk.GetArrayViewFromImage(liver) > 0).sum())
    if voxels == 0:
        raise PipelineError("MRSegmentator nao produziu voxels de figado (rotulo 5).")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_name(f".{output_path.name}.{uuid.uuid4().hex[:8]}.tmp.nii.gz")
    try:
        sitk.WriteImage(liver, str(temporary), useCompression=True)
        os.replace(temporary, output_path)
    finally:
        temporary.unlink(missing_ok=True)
    quality = validate_visualization_mask(output_path, source_path)
    return {
        "label_value": LIVER_LABEL,
        "resampled_to_source_grid": resampled,
        **quality,
    }


def gpu_memory_used_mb() -> int | None:
    try:
        completed = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=memory.used",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            check=True,
            timeout=10,
        )
        values = [int(line.strip()) for line in completed.stdout.splitlines() if line.strip()]
        return max(values) if values else None
    except (OSError, ValueError, subprocess.SubprocessError):
        return None


def cuda_preflight(python_exe: Path | str) -> dict[str, Any]:
    command = [
        str(Path(python_exe).resolve()),
        "-c",
        (
            "import json,torch; print(json.dumps({"
            "'torch':torch.__version__,'cuda_available':torch.cuda.is_available(),"
            "'cuda_version':torch.version.cuda,'device':"
            "torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,"
            "'vram_bytes':torch.cuda.get_device_properties(0).total_memory "
            "if torch.cuda.is_available() else None}))"
        ),
    ]
    try:
        completed = subprocess.run(command, capture_output=True, text=True, check=True, timeout=30)
        value = json.loads(completed.stdout.strip().splitlines()[-1])
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError, IndexError) as exc:
        raise PipelineError(f"Preflight CUDA do MRSegmentator falhou: {exc}") from exc
    if value.get("cuda_available") is not True or not value.get("device"):
        raise PipelineError("Ambiente isolado MRSegmentator nao possui CUDA funcional.")
    return value


def _terminate_tree(process: subprocess.Popen[Any]) -> None:
    if process.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            capture_output=True,
            check=False,
        )
    else:
        process.kill()


def _publish_directory(staging: Path, output: Path, *, attempts: int = 6) -> None:
    """Tolerate short-lived Windows handles after the final model subprocess."""

    last_error: OSError | None = None
    for attempt in range(attempts):
        try:
            os.replace(staging, output)
            return
        except PermissionError as exc:
            last_error = exc
            if attempt + 1 < attempts:
                time.sleep(0.5 * (attempt + 1))
    raise PipelineError(
        "Windows manteve um handle no staging; dados concluidos foram preservados para retomada."
    ) from last_error


def run_case(
    *,
    source: Path,
    case_id: str,
    mrsegmentator_exe: Path,
    staging: Path,
    timeout_seconds: int,
) -> dict[str, Any]:
    raw_dir = staging / "raw" / case_id
    raw_dir.mkdir(parents=True, exist_ok=True)
    stdout_path = staging / "logs" / f"{case_id}.stdout.log"
    stderr_path = staging / "logs" / f"{case_id}.stderr.log"
    stdout_path.parent.mkdir(parents=True, exist_ok=True)
    command = [
        str(mrsegmentator_exe),
        "-i",
        str(source),
        "-o",
        str(raw_dir),
        "--fast",
        "--batchsize",
        "1",
        "--nproc",
        "1",
        "--nproc_export",
        "1",
        "--no_tqdm",
        "--log_level",
        "WARNING",
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
                raise PipelineError(f"MRSegmentator excedeu timeout de {timeout_seconds}s.")
            current = gpu_memory_used_mb()
            if current is not None:
                peak_memory = current if peak_memory is None else max(peak_memory, current)
            time.sleep(0.5)
    elapsed = time.perf_counter() - started
    if process.returncode != 0:
        detail = stderr_path.read_text(encoding="utf-8", errors="replace")[-1200:]
        raise PipelineError(f"MRSegmentator falhou ({process.returncode}): {detail}")
    expected = raw_dir / f"{source.stem.replace('.nii', '')}_seg.nii.gz"
    if not expected.is_file():
        raise PipelineError("MRSegmentator terminou sem produzir labelmap.")
    mask = staging / "masks" / f"{case_id}.nii.gz"
    mask_result = extract_liver_label(expected, source, mask)
    return {
        "schema": CASE_SCHEMA,
        "case_id": case_id,
        "status": "completed",
        "source_sha256": sha256_of(source),
        "raw_labelmap_sha256": sha256_of(expected),
        "raw_labelmap_name": expected.name,
        "mask_sha256": sha256_of(mask),
        "mask": mask_result,
        "elapsed_seconds": round(float(elapsed), 6),
        "gpu_memory_baseline_mb": baseline_memory,
        "gpu_memory_peak_mb": peak_memory,
        "gpu_memory_delta_mb": (
            peak_memory - baseline_memory
            if peak_memory is not None and baseline_memory is not None
            else None
        ),
        "mode": "fast_single_fold_gpu",
        "timeout_seconds": int(timeout_seconds),
    }


def run_cohort(
    *,
    cohort_root: Path | str,
    output_root: Path | str,
    mrsegmentator_exe: Path | str,
    python_exe: Path | str,
    timeout_seconds: int = 180,
    source_name: str = "t1_in.nii.gz",
) -> dict[str, Any]:
    cohort = Path(cohort_root).resolve()
    output = Path(output_root).resolve()
    executable = Path(mrsegmentator_exe).resolve()
    if not cohort.is_dir() or not executable.is_file():
        raise PipelineError("Coorte ou executavel MRSegmentator ausente.")
    if output.exists():
        raise PipelineError("Saida MRSegmentator final ja existe; sobrescrita recusada.")
    if timeout_seconds < 30:
        raise PipelineError("Timeout MRSegmentator excessivamente curto.")
    cases = sorted(path for path in cohort.iterdir() if path.is_dir())
    if not source_name or Path(source_name).name != source_name:
        raise PipelineError("Nome da fonte MRSegmentator invalido.")
    sources = [(case.name, case / source_name) for case in cases]
    if not sources or any(not source.is_file() for _, source in sources):
        raise PipelineError("Coorte CHAOS incompleta para MRSegmentator.")
    cuda = cuda_preflight(python_exe)
    staging = output.with_name(f".{output.name}.incomplete")
    staging.mkdir(parents=True, exist_ok=True)
    context_path = staging / "run_context.json"
    context = {
        "schema": RUN_SCHEMA,
        "case_ids": [case_id for case_id, _ in sources],
        "case_count": len(sources),
        "mode": "fast_single_fold_gpu",
        "liver_label": LIVER_LABEL,
        "timeout_seconds": int(timeout_seconds),
        "source_name": source_name,
        "cuda": cuda,
        "ground_truth_read": False,
        "lesion_masks_read": 0,
        "production_files_written": False,
    }
    if context_path.is_file():
        if json.loads(context_path.read_text(encoding="utf-8")) != context:
            raise PipelineError("Checkpoint MRSegmentator pertence a outro protocolo.")
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
        raise PipelineError("Ordem do checkpoint MRSegmentator invalida.")
    for row in rows:
        mask = staging / "masks" / f"{row['case_id']}.nii.gz"
        if row.get("status") != "completed" or not mask.is_file() or sha256_of(mask) != row.get("mask_sha256"):
            raise PipelineError("Checkpoint MRSegmentator adulterado ou incompleto.")
    for case_id, source in sources[len(rows) :]:
        row = run_case(
            source=source,
            case_id=case_id,
            mrsegmentator_exe=executable,
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
    _publish_directory(staging, output)
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
        raise PipelineError("Execucao MRSegmentator ausente ou invalida.") from exc
    if context.get("schema") != RUN_SCHEMA or summary.get("schema") != RUN_SCHEMA:
        raise PipelineError("Schema da execucao MRSegmentator invalido.")
    if len(rows) != context.get("case_count") or len(rows) != summary.get("completed_cases"):
        raise PipelineError("Contagem MRSegmentator divergente.")
    if sha256_of(root / "checkpoint_cases.jsonl") != summary.get("checkpoint_sha256"):
        raise PipelineError("Checkpoint MRSegmentator adulterado.")
    for row in rows:
        mask = root / "masks" / f"{row['case_id']}.nii.gz"
        raw_name = str(row.get("raw_labelmap_name") or "t1_in_seg.nii.gz")
        raw = root / "raw" / str(row["case_id"]) / raw_name
        if not mask.is_file() or not raw.is_file():
            raise PipelineError("Artefato MRSegmentator ausente.")
        if sha256_of(mask) != row.get("mask_sha256") or sha256_of(raw) != row.get("raw_labelmap_sha256"):
            raise PipelineError("Hash MRSegmentator divergente.")
    return summary


__all__ = [
    "RUN_SCHEMA",
    "CASE_SCHEMA",
    "LIVER_LABEL",
    "extract_liver_label",
    "cuda_preflight",
    "run_case",
    "run_cohort",
    "verify_run",
    "_publish_directory",
]
