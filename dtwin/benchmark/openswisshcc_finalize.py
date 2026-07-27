"""Finalização atômica de uma variante técnica aprovada do OpenSwissHCC."""
from __future__ import annotations

import json
import shutil
import uuid
from pathlib import Path
from typing import Any

from dtwin.benchmark.openswisshcc_alignment import (
    _load_json,
    _publish_directory,
    _sha256,
)
from dtwin.benchmark.openswisshcc_freeze import verify_experiment_freeze
from dtwin.benchmark.openswisshcc_review import _candidate
from dtwin.core import PipelineError


FINALIZATION_SCHEMA = "argos-openswisshcc-candidate-finalization-v1"


def _validated_replacement(
    root: Path, case_id: str, expected_config: Path
) -> tuple[dict[str, Any], dict[str, Any]]:
    root = Path(root).resolve()
    case_dir = (root / case_id).resolve()
    if not case_dir.is_relative_to(root) or not case_dir.is_dir():
        raise PipelineError("Diretório da variante aprovada é inseguro ou ausente.")
    candidate = _load_json(case_dir / "candidate_manifest.json")
    if candidate.get("case_id") != case_id:
        raise PipelineError("Variante aprovada pertence a outro caso.")
    if candidate.get("candidate_kind") != "venous_single_phase_fallback":
        raise PipelineError("Variante aprovada não é um fallback venoso.")
    if candidate.get("config_sha256") != _sha256(Path(expected_config).resolve()):
        raise PipelineError("Variante aprovada não corresponde à configuração esperada.")
    if candidate.get("ground_truth_read") is not False:
        raise PipelineError("Variante aprovada viola o isolamento do ground truth.")
    reviewed = _candidate(root, case_id)
    return candidate, reviewed


def finalize_candidate_variant(
    *,
    source_panel_root: Path,
    source_freeze_path: Path,
    replacement_root: Path,
    replacement_case_id: str,
    replacement_config: Path,
    output_root: Path,
    multiphase_config: Path,
    fallback_config: Path,
    expected_case_count: int = 88,
) -> dict[str, Any]:
    """Preserve a coorte e substitua exatamente uma variante aprovada."""
    source_panel_root = Path(source_panel_root).resolve()
    replacement_root = Path(replacement_root).resolve()
    output_root = Path(output_root).resolve()
    if output_root.exists():
        raise PipelineError("Destino final já existe; não será sobrescrito.")
    freeze = verify_experiment_freeze(
        freeze_path=source_freeze_path,
        panel_root=source_panel_root,
        multiphase_config=multiphase_config,
        fallback_config=fallback_config,
        expected_case_count=expected_case_count,
    )
    replacement, replacement_reviewed = _validated_replacement(
        replacement_root, replacement_case_id, replacement_config
    )
    source_by_id = {str(item["case_id"]): item for item in freeze["candidates"]}
    if replacement_case_id not in source_by_id:
        raise PipelineError("Caso substituído não pertence à coorte congelada.")
    if replacement["panel_sha256"] == source_by_id[replacement_case_id]["panel_sha256"]:
        raise PipelineError("Variante aprovada não altera o painel de origem.")

    output_root.parent.mkdir(parents=True, exist_ok=True)
    staging = output_root.with_name(f"._final_{uuid.uuid4().hex[:8]}")
    staging.mkdir()
    try:
        cases: list[dict[str, Any]] = []
        for item in freeze["candidates"]:
            case_id = str(item["case_id"])
            if case_id == replacement_case_id:
                shutil.copytree(replacement_root / case_id, staging / case_id)
                target = replacement_reviewed
                action = "approved_variant_replacement"
            else:
                shutil.copytree(source_panel_root / case_id, staging / case_id)
                target = _candidate(staging, case_id)
                action = "preserved"
                if target["panel_sha256"] != item["panel_sha256"]:
                    raise PipelineError("Caso preservado mudou durante a finalização.")
            cases.append(
                {
                    "case_id": case_id,
                    "action": action,
                    "source_panel_sha256": item["panel_sha256"],
                    "target_panel_sha256": target["panel_sha256"],
                }
            )
        if len([path for path in staging.iterdir() if path.is_dir()]) != expected_case_count:
            raise PipelineError("Finalização não preservou a coorte completa.")
        manifest = {
            "schema": FINALIZATION_SCHEMA,
            "source_experiment_signature": freeze["experiment_signature"],
            "case_count": len(cases),
            "preserved_count": sum(item["action"] == "preserved" for item in cases),
            "replacement_count": sum(
                item["action"] == "approved_variant_replacement" for item in cases
            ),
            "replacement_case_id": replacement_case_id,
            "replacement_config_sha256": _sha256(Path(replacement_config).resolve()),
            "cases": cases,
            "research_only": True,
            "clinical_use_allowed": False,
            "ground_truth_read": False,
            "inference_executed": False,
            "human_approval_required": True,
        }
        (staging / "finalization_manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        _publish_directory(staging, output_root)
        return manifest
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
