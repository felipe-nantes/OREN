"""Auditoria sanitizada de tempo do fluxo DICOM operacional do ARGOS.

O artefato produzido por este módulo mede duas fronteiras distintas:

* ``time_to_report``: do início do worker até a existência de um
  ``medgemma_report.json`` validado;
* ``total_with_3d``: a mesma execução incluindo a geração opcional do modelo 3D.

Nenhum label, UID DICOM ou caminho de entrada é aceito pelo schema. O objetivo é
separar evidência de latência operacional de evidência de acurácia clínica.
"""
from __future__ import annotations

import json
import math
import os
from pathlib import Path
from typing import Mapping


SCHEMA = "argos-operational-dicom-timing-v1"
DEFAULT_REPORT_BUDGET_SECONDS = 180.0


def _clean_durations(values: Mapping[str, float]) -> dict[str, float]:
    cleaned: dict[str, float] = {}
    for key, value in values.items():
        number = float(value)
        if not math.isfinite(number) or number < 0:
            raise ValueError(f"Duração inválida em {key!r}: {value!r}")
        cleaned[str(key)] = round(number, 4)
    return cleaned


def build_operational_timing(
    *,
    job_id: str,
    analysis_scenario: str,
    medgemma_config: str,
    medgemma_config_sha256: str,
    started_at_utc: str,
    finished_at_utc: str,
    durations_seconds: Mapping[str, float],
    outcome: str,
    report_available: bool,
    viewer_ready: bool,
    failure_stage: str | None,
    segmentation_device: str | None,
    report_budget_seconds: float = DEFAULT_REPORT_BUDGET_SECONDS,
) -> dict:
    """Monta o manifesto v1 e aplica o gate de 180 s sem arredondar a decisão."""
    durations = _clean_durations(durations_seconds)
    budget = float(report_budget_seconds)
    if not math.isfinite(budget) or budget <= 0:
        raise ValueError("O orçamento de tempo deve ser positivo e finito.")

    time_to_report = durations.get("time_to_report")
    total_with_3d = durations.get("total_with_3d")
    report_gate = (
        bool(report_available and time_to_report <= budget)
        if time_to_report is not None
        else None
    )
    total_gate = (
        bool(report_available and viewer_ready and total_with_3d <= budget)
        if total_with_3d is not None
        else None
    )

    return {
        "schema": SCHEMA,
        "job_id": str(job_id),
        "analysis_scenario": str(analysis_scenario),
        "model": {
            "family": "MedGemma",
            "parameter_scale": "4B",
            "config": str(medgemma_config),
            "config_sha256": str(medgemma_config_sha256),
        },
        "started_at_utc": str(started_at_utc),
        "finished_at_utc": str(finished_at_utc),
        "outcome": str(outcome),
        "failure_stage": failure_stage,
        "segmentation_device": segmentation_device,
        "report_available": bool(report_available),
        "viewer_ready": bool(viewer_ready),
        "durations_seconds": durations,
        "time_budget": {
            "report_max_seconds": budget,
            "time_to_report_seconds": time_to_report,
            "time_to_report_within_budget": report_gate,
            "total_with_3d_seconds": total_with_3d,
            "total_with_3d_within_budget": total_gate,
        },
        "scope": {
            "clock_start": "worker_start_after_upload",
            "time_to_report_end": "validated_medgemma_report_json_available",
            "total_with_3d_end": "viewer_model_attempt_finished",
            "upload_duration_included": False,
            "worker_queue_duration_included": False,
            "medgemma_gateway_lock_wait_included": True,
        },
        "safety": {
            "research_only": True,
            "clinical_use_allowed": False,
            "human_review_required": True,
            "ground_truth_read": False,
            "raw_paths_persisted": False,
            "raw_uids_persisted": False,
        },
    }


def persist_operational_timing(case_dir: Path, payload: Mapping) -> Path:
    """Grava atomicamente o manifesto operacional dentro do diretório do caso."""
    output = Path(case_dir) / "outputs" / "operational_timing.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(f".{output.name}.tmp")
    try:
        temporary.write_text(
            json.dumps(dict(payload), indent=2, ensure_ascii=False, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, output)
    finally:
        temporary.unlink(missing_ok=True)
    return output
