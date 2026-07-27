"""Orquestrador sequencial e isolado da inferência OpenSwissHCC revisada."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Callable

from dtwin.benchmark.openswisshcc_alignment import _load_json, _sha256
from dtwin.benchmark.openswisshcc_configs import (
    authorized_config_paths,
    resolve_candidate_config,
)
from dtwin.benchmark.openswisshcc_freeze import verify_experiment_freeze
from dtwin.benchmark.openswisshcc_review import verify_panel_review
from dtwin.core import PipelineError
from dtwin.medgemma_client import (
    create_medgemma_client,
    effective_config_sha256,
    load_screening_config,
)


def _config_for_candidate(
    candidate: dict[str, Any],
    multiphase_config: Path,
    fallback_config: Path,
    additional_configs: dict[str, Path] | None = None,
) -> Path:
    paths = authorized_config_paths(
        multiphase_config=multiphase_config,
        fallback_config=fallback_config,
        additional_configs=additional_configs,
    )
    return resolve_candidate_config(candidate, paths)[1]

def _write_atomic(path: Path, payload: object) -> None:
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _cleanup_staging(output_root: Path, case_id: str) -> None:
    root = output_root.resolve()
    for path in root.glob(f".{case_id}.staging.*"):
        resolved = path.resolve()
        if resolved.is_relative_to(root) and resolved.is_dir():
            shutil.rmtree(resolved, ignore_errors=True)


def _default_runner(command: list[str], *, timeout: float, cwd: Path) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return subprocess.run(
        command,
        cwd=cwd,
        env=env,
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
    )


def run_reviewed_inference_batch(
    *, panel_root: Path, review_path: Path, freeze_path: Path, output_root: Path,
    multiphase_config: Path, fallback_config: Path,
    additional_configs: dict[str, Path] | None = None,
    case_ids: list[str] | None = None, expected_case_count: int = 88,
    case_timeout_seconds: float = 180.0, cwd: Path | None = None,
    runner: Callable[..., subprocess.CompletedProcess] = _default_runner,
    client_factory: Callable[[dict[str, Any]], Any] = create_medgemma_client,
) -> dict[str, Any]:
    """Execute casos aprovados sem abrir ou receber qualquer ground truth."""
    if not 0 < float(case_timeout_seconds) <= 180:
        raise PipelineError("case_timeout_seconds deve estar em (0, 180].")
    panel_root = Path(panel_root).resolve()
    review_path = Path(review_path).resolve()
    freeze_path = Path(freeze_path).resolve()
    output_root = Path(output_root).resolve()
    multiphase_config = Path(multiphase_config).resolve()
    fallback_config = Path(fallback_config).resolve()
    registry = authorized_config_paths(
        multiphase_config=multiphase_config,
        fallback_config=fallback_config,
        additional_configs=additional_configs,
    )
    additional_configs = {
        key: path
        for key, path in registry.items()
        if key not in {"multiphase_rgb", "venous_single_phase_fallback"}
    }
    cwd = Path(cwd or Path.cwd()).resolve()
    if output_root.exists():
        raise PipelineError("Diretório da rodada já existe; não será sobrescrito.")

    freeze = verify_experiment_freeze(
        freeze_path=freeze_path,
        panel_root=panel_root,
        multiphase_config=multiphase_config,
        fallback_config=fallback_config,
        expected_case_count=expected_case_count,
        additional_configs=additional_configs,
    )
    review = verify_panel_review(review_path=review_path, panel_root=panel_root)
    approved_ids = [str(item["case_id"]) for item in review["panels"]]
    frozen_ids = [str(item["case_id"]) for item in freeze["candidates"]]
    if sorted(approved_ids) != sorted(frozen_ids):
        raise PipelineError("Aprovação humana e congelamento não cobrem a mesma coorte.")
    selected = sorted(set(case_ids if case_ids is not None else approved_ids))
    if not selected or set(selected) - set(approved_ids):
        raise PipelineError("Seleção contém caso vazio ou não aprovado.")

    config_paths: dict[str, Path] = {}
    effective_hashes: dict[str, str] = {}
    backend_identity: set[tuple[str, str, str, str]] = set()
    for case_id in selected:
        candidate = _load_json(panel_root / case_id / "candidate_manifest.json")
        config_path = _config_for_candidate(
            candidate, multiphase_config, fallback_config, additional_configs
        )
        if _sha256(config_path) != candidate.get("config_sha256"):
            raise PipelineError(f"Hash da configuração diverge no caso {case_id}.")
        config = load_screening_config(config_path)
        effective = effective_config_sha256(config)
        config_paths[case_id] = config_path
        effective_hashes[config_path.name] = effective
        med = config["medgemma"]
        backend_identity.add(
            (
                str(med.get("model_id")),
                str(med.get("model_version")),
                str(med.get("endpoint_url")),
                str(med.get("healthcheck_url")),
            )
        )
    if len(backend_identity) != 1:
        raise PipelineError("Configurações do lote não apontam para o mesmo backend/modelo.")
    health = client_factory(load_screening_config(config_paths[selected[0]])).check_ready()
    if health.get("model_id") != "google/medgemma-1.5-4b-it":
        raise PipelineError("Preflight não confirmou MedGemma 1.5 4B.")

    output_root.mkdir(parents=True)
    records: list[dict[str, Any]] = []
    for index, case_id in enumerate(selected, start=1):
        started = time.monotonic()
        command = [
            sys.executable, "-B", "-m", "tools.infer_openswisshcc_case",
            "--case-id", case_id,
            "--panels", str(panel_root),
            "--review", str(review_path),
            "--freeze", str(freeze_path),
            "--out", str(output_root),
            "--config", str(config_paths[case_id]),
            "--multiphase-config", str(multiphase_config),
            "--fallback-config", str(fallback_config),
            "--expected-case-count", str(int(expected_case_count)),
            "--max-case-seconds", str(float(case_timeout_seconds)),
        ]
        for key, path in sorted(additional_configs.items()):
            command.extend(["--extra-config", f"{key}={path}"])
        try:
            completed = runner(command, timeout=float(case_timeout_seconds), cwd=cwd)
            elapsed = time.monotonic() - started
            if completed.returncode != 0:
                detail = (completed.stderr or completed.stdout or "").strip()
                record = {
                    "case_id": case_id,
                    "status": "technical_failure",
                    "elapsed_seconds": round(elapsed, 4),
                    "error": detail[-2000:],
                }
            else:
                case_dir = output_root / case_id
                report_path = case_dir / "medgemma_report.json"
                manifest_path = case_dir / "inference_manifest.json"
                if not report_path.is_file() or not manifest_path.is_file():
                    raise PipelineError("Subprocesso não publicou os artefatos obrigatórios.")
                manifest = _load_json(manifest_path)
                if manifest.get("case_id") != case_id or manifest.get("ground_truth_read") is not False:
                    raise PipelineError("Manifesto de inferência do caso é incompatível.")
                if _sha256(report_path) != manifest.get("report_sha256"):
                    raise PipelineError("Hash do relatório final é incompatível.")
                record = {
                    "case_id": case_id,
                    "status": "success_pending_human_review",
                    "prediction": manifest.get("prediction"),
                    "elapsed_seconds": round(elapsed, 4),
                    "model_elapsed_seconds": manifest.get("elapsed_seconds"),
                    "within_time_limit": elapsed <= float(case_timeout_seconds),
                    "report_sha256": manifest.get("report_sha256"),
                    "effective_config_sha256": manifest.get("effective_config_sha256"),
                }
        except subprocess.TimeoutExpired:
            elapsed = time.monotonic() - started
            _cleanup_staging(output_root, case_id)
            record = {
                "case_id": case_id,
                "status": "timeout",
                "elapsed_seconds": round(elapsed, 4),
                "within_time_limit": False,
                "error": f"Subprocesso excedeu {case_timeout_seconds:.3f} segundos.",
            }
        except Exception as exc:
            elapsed = time.monotonic() - started
            _cleanup_staging(output_root, case_id)
            record = {
                "case_id": case_id,
                "status": "technical_failure",
                "elapsed_seconds": round(elapsed, 4),
                "error": str(exc)[:2000],
            }
        records.append(record)
        print(json.dumps({"index": index, "total": len(selected), **record}, ensure_ascii=False, sort_keys=True), flush=True)

    counts: dict[str, int] = {}
    for record in records:
        counts[str(record["status"])] = counts.get(str(record["status"]), 0) + 1
    summary = {
        "schema": "argos-openswisshcc-inference-batch-v1",
        "status": "completed_pending_human_review",
        "case_count": len(records),
        "status_counts": counts,
        "case_timeout_seconds": float(case_timeout_seconds),
        "review_signature": review["review_signature"],
        "experiment_signature": freeze["experiment_signature"],
        "effective_config_sha256": effective_hashes,
        "backend_health": {
            "status": health.get("status"),
            "model_id": health.get("model_id"),
            "model_version": health.get("model_version"),
            "contract": health.get("contract"),
        },
        "ground_truth_read": False,
        "metrics_calculated": False,
        "research_only": True,
        "clinical_use_allowed": False,
        "requires_human_review": True,
        "records": records,
    }
    _write_atomic(output_root / "inference_summary.json", summary)
    return summary
