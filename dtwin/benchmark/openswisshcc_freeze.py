"""Congelamento reproduzível do experimento OpenSwissHCC antes da inferência."""
from __future__ import annotations

import hashlib
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dtwin.benchmark.openswisshcc_alignment import _load_json, _sha256
from dtwin.benchmark.openswisshcc_configs import (
    authorized_config_paths,
    resolve_candidate_config,
)
from dtwin.benchmark.openswisshcc_review import _candidate, ready_case_ids
from dtwin.core import PipelineError
from dtwin.medgemma_client import (
    effective_config_sha256,
    load_screening_config,
)


FREEZE_SCHEMA = "argos-openswisshcc-experiment-freeze-v1"
FREEZE_SIGNED_FIELDS = (
    "schema",
    "experiment_version",
    "case_count",
    "configs",
    "candidates",
    "research_only",
    "clinical_use_allowed",
    "ground_truth_read",
    "inference_executed",
)


def _signature(payload: dict[str, Any]) -> str:
    signed = {key: payload.get(key) for key in FREEZE_SIGNED_FIELDS}
    return hashlib.sha256(
        json.dumps(signed, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        .encode("utf-8")
    ).hexdigest()


def _config_records(
    multiphase_config: Path,
    fallback_config: Path,
    additional_configs: dict[str, Path] | None = None,
) -> tuple[dict[str, dict[str, Any]], dict[str, Path]]:
    paths = authorized_config_paths(
        multiphase_config=multiphase_config,
        fallback_config=fallback_config,
        additional_configs=additional_configs,
    )
    records: dict[str, dict[str, Any]] = {}
    backend_identity: set[tuple[str, str, str]] = set()
    for key, path in paths.items():
        config = load_screening_config(path)
        med = config["medgemma"]
        record = {
            "filename": path.name,
            "raw_sha256": _sha256(path),
            "effective_sha256": effective_config_sha256(config),
            "model_id": med.get("model_id"),
            "model_version": med.get("model_version"),
            "endpoint_url": med.get("endpoint_url"),
            "timeout_seconds": med.get("timeout_seconds"),
            "max_retries": med.get("max_retries"),
            "response_validation_max_retries": med.get("response_validation_max_retries"),
        }
        if record["model_id"] != "google/medgemma-1.5-4b-it":
            raise PipelineError("Congelamento exige exatamente MedGemma 1.5 4B.")
        if int(record["timeout_seconds"] or 0) > 120:
            raise PipelineError("Configuração excede o timeout interno de 120 segundos.")
        if (
            int(record["max_retries"] or 0) != 0
            or int(record["response_validation_max_retries"] or 0) != 0
        ):
            raise PipelineError("Configuração congelada não pode usar retry.")
        backend_identity.add(
            (str(record["model_id"]), str(record["model_version"]), str(record["endpoint_url"]))
        )
        records[key] = record
    if len(backend_identity) != 1:
        raise PipelineError("Configurações congeladas não compartilham modelo e endpoint.")
    return records, paths


def _candidate_records(
    panel_root: Path,
    configs: dict[str, dict[str, Any]],
    config_paths: dict[str, Path],
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for case_id in ready_case_ids(panel_root):
        reviewed_shape = _candidate(panel_root, case_id)
        manifest = _load_json(Path(panel_root) / case_id / "candidate_manifest.json")
        kind = manifest.get("candidate_kind", "multiphase_rgb")
        config_key, _ = resolve_candidate_config(manifest, config_paths)
        config = configs[config_key]
        if manifest.get("research_only") is not True or manifest.get("clinical_use_allowed") is not False:
            raise PipelineError("Candidato perdeu as salvaguardas de pesquisa.")
        records.append(
            {
                **reviewed_shape,
                "candidate_kind": kind,
                "config_raw_sha256": config["raw_sha256"],
                "config_effective_sha256": config["effective_sha256"],
            }
        )
    return records

def create_experiment_freeze(
    *, panel_root: Path, multiphase_config: Path, fallback_config: Path,
    output_path: Path, expected_case_count: int = 88,
    experiment_version: str = "openswisshcc-development-medgemma-4b-v1",
    additional_configs: dict[str, Path] | None = None,
) -> dict[str, Any]:
    """Congele bytes dos painéis e configurações resolvidas sem abrir labels."""
    panel_root = Path(panel_root).resolve()
    output_path = Path(output_path).resolve()
    experiment_version = str(experiment_version).strip()
    if not experiment_version or len(experiment_version) > 120:
        raise PipelineError("experiment_version é inválida.")
    if output_path.exists():
        raise PipelineError("Congelamento já existe; não será sobrescrito.")
    configs, config_paths = _config_records(
        multiphase_config, fallback_config, additional_configs
    )
    candidates = _candidate_records(panel_root, configs, config_paths)
    if len(candidates) != int(expected_case_count):
        raise PipelineError(
            f"Coorte incompleta para congelamento: {len(candidates)} != {expected_case_count}."
        )
    payload = {
        "schema": FREEZE_SCHEMA,
        "experiment_version": experiment_version,
        "case_count": len(candidates),
        "configs": configs,
        "candidates": candidates,
        "research_only": True,
        "clinical_use_allowed": False,
        "ground_truth_read": False,
        "inference_executed": False,
    }
    payload["experiment_signature"] = _signature(payload)
    payload["created_at_utc"] = datetime.now(timezone.utc).isoformat()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_name(f".{output_path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, output_path)
    finally:
        temporary.unlink(missing_ok=True)
    return payload


def verify_experiment_freeze(
    *, freeze_path: Path, panel_root: Path,
    multiphase_config: Path, fallback_config: Path,
    expected_case_count: int = 88,
    additional_configs: dict[str, Path] | None = None,
) -> dict[str, Any]:
    """Recalcule a coorte e os hashes efetivos imediatamente antes da execução."""
    freeze = _load_json(Path(freeze_path).resolve())
    allowed = set(FREEZE_SIGNED_FIELDS) | {"experiment_signature", "created_at_utc"}
    if set(freeze) != allowed or freeze.get("schema") != FREEZE_SCHEMA:
        raise PipelineError("Campos ou schema do congelamento são incompatíveis.")
    if freeze.get("experiment_signature") != _signature(freeze):
        raise PipelineError("Assinatura do congelamento experimental é incompatível.")
    if freeze.get("ground_truth_read") is not False or freeze.get("inference_executed") is not False:
        raise PipelineError("Congelamento viola o isolamento metodológico.")
    configs, config_paths = _config_records(
        multiphase_config, fallback_config, additional_configs
    )
    candidates = _candidate_records(Path(panel_root).resolve(), configs, config_paths)
    if len(candidates) != int(expected_case_count):
        raise PipelineError("Coorte atual não possui a contagem congelada esperada.")
    if freeze.get("case_count") != len(candidates):
        raise PipelineError("Contagem do congelamento é incompatível.")
    if freeze.get("configs") != configs or freeze.get("candidates") != candidates:
        raise PipelineError("Painel, candidato ou configuração efetiva mudou após o congelamento.")
    return freeze
