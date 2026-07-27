"""Remediação técnica pré-inferência dos candidatos OpenSwissHCC."""
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
from dtwin.benchmark.openswisshcc_fallback import (
    REVIEW_FALLBACK_REASON,
    render_venous_fallback_candidate,
)
from dtwin.benchmark.openswisshcc_freeze import verify_experiment_freeze
from dtwin.core import PipelineError


TRIAGE_SCHEMA = "argos-openswisshcc-technical-triage-v1"
REMEDIATION_SCHEMA = "argos-openswisshcc-technical-remediation-v1"
ALLOWED_CODES = frozenset({"M", "C", "I"})
RENDER_FALLBACK_CODES = frozenset({"M", "C"})


def load_review_triage(path: Path) -> dict[str, Any]:
    """Valide a declaração técnica humana sem aceitar informação diagnóstica."""
    payload = _load_json(Path(path).resolve())
    required = {
        "schema",
        "reviewer_source",
        "case_count",
        "cases",
        "research_only",
        "clinical_use_allowed",
        "ground_truth_read",
        "inference_executed",
    }
    if not isinstance(payload, dict) or set(payload) != required:
        raise PipelineError("Campos da triagem técnica são incompatíveis.")
    if payload.get("schema") != TRIAGE_SCHEMA:
        raise PipelineError("Schema da triagem técnica é incompatível.")
    if not str(payload.get("reviewer_source", "")).strip():
        raise PipelineError("Triagem técnica sem origem humana declarada.")
    if (
        payload.get("research_only") is not True
        or payload.get("clinical_use_allowed") is not False
        or payload.get("ground_truth_read") is not False
        or payload.get("inference_executed") is not False
    ):
        raise PipelineError("Triagem técnica viola as salvaguardas metodológicas.")
    cases = payload.get("cases")
    if not isinstance(cases, list) or payload.get("case_count") != len(cases):
        raise PipelineError("Contagem da triagem técnica é incompatível.")
    seen: set[str] = set()
    for item in cases:
        if not isinstance(item, dict) or set(item) != {"case_id", "codes", "note"}:
            raise PipelineError("Entrada da triagem técnica possui campos inválidos.")
        case_id = str(item.get("case_id", ""))
        if not case_id.startswith("anon-openswiss-") or case_id in seen:
            raise PipelineError("case_id inválido ou duplicado na triagem técnica.")
        seen.add(case_id)
        codes = item.get("codes")
        if (
            not isinstance(codes, list)
            or not codes
            or len(codes) != len(set(codes))
            or not set(codes).issubset(ALLOWED_CODES)
        ):
            raise PipelineError(f"Códigos técnicos inválidos no caso {case_id}.")
        if len(str(item.get("note", ""))) > 240:
            raise PipelineError("Nota técnica excede 240 caracteres.")
    return payload


def _action(codes: set[str]) -> str:
    if codes & RENDER_FALLBACK_CODES:
        return "venous_review_fallback"
    if codes == {"I"}:
        return "restored_source_candidate_retained"
    return "unchanged"


def build_remediated_candidates(
    *,
    source_panel_root: Path,
    source_freeze_path: Path,
    input_root: Path,
    output_root: Path,
    triage_path: Path,
    multiphase_config: Path,
    original_fallback_config: Path,
    review_fallback_config: Path,
    profile_path: Path,
    expected_case_count: int = 88,
) -> dict[str, Any]:
    """Crie uma coorte v2 atômica, sem excluir casos e sem abrir labels."""
    source_panel_root = Path(source_panel_root).resolve()
    output_root = Path(output_root).resolve()
    input_root = Path(input_root).resolve()
    triage_path = Path(triage_path).resolve()
    review_fallback_config = Path(review_fallback_config).resolve()
    profile_path = Path(profile_path).resolve()
    if output_root.exists():
        raise PipelineError("Destino da remediação já existe; não será sobrescrito.")

    freeze = verify_experiment_freeze(
        freeze_path=Path(source_freeze_path),
        panel_root=source_panel_root,
        multiphase_config=Path(multiphase_config),
        fallback_config=Path(original_fallback_config),
        expected_case_count=expected_case_count,
    )
    triage = load_review_triage(triage_path)
    if len(triage["cases"]) >= expected_case_count:
        raise PipelineError("Triagem não pode substituir a revisão integral da coorte.")
    triaged = {str(item["case_id"]): item for item in triage["cases"]}
    frozen = {str(item["case_id"]): item for item in freeze["candidates"]}
    unknown = sorted(set(triaged) - set(frozen))
    if unknown:
        raise PipelineError(f"Triagem contém casos fora do freeze: {unknown}.")

    output_root.parent.mkdir(parents=True, exist_ok=True)
    # Nome curto: o renderer cria outro staging e o PIL no Windows ainda pode
    # encontrar o limite clássico de comprimento de caminho.
    staging = output_root.with_name(f"._rem_{uuid.uuid4().hex[:8]}")
    staging.mkdir()
    try:
        actions: list[dict[str, Any]] = []
        for frozen_item in freeze["candidates"]:
            case_id = str(frozen_item["case_id"])
            entry = triaged.get(case_id)
            codes = set(entry["codes"]) if entry else set()
            action = _action(codes)
            source_dir = (source_panel_root / case_id).resolve()
            if not source_dir.is_relative_to(source_panel_root) or not source_dir.is_dir():
                raise PipelineError(f"Diretório fonte inseguro ou ausente: {case_id}.")

            if action == "venous_review_fallback":
                candidate = render_venous_fallback_candidate(
                    case_id=case_id,
                    input_root=input_root,
                    output_root=staging,
                    config_path=review_fallback_config,
                    profile_path=profile_path,
                    fallback_reason=REVIEW_FALLBACK_REASON,
                )
            else:
                shutil.copytree(source_dir, staging / case_id)
                candidate = _load_json(staging / case_id / "candidate_manifest.json")

            if candidate.get("case_id") != case_id:
                raise PipelineError("Remediação produziu manifesto de outro caso.")
            panel = staging / case_id / str(candidate.get("panel_filename", ""))
            if not panel.is_file() or _sha256(panel) != candidate.get("panel_sha256"):
                raise PipelineError("Remediação produziu painel ausente ou hash incompatível.")
            if action == "unchanged" and candidate.get("panel_sha256") != frozen_item.get("panel_sha256"):
                raise PipelineError("Caso não triado mudou durante a remediação.")
            actions.append(
                {
                    "case_id": case_id,
                    "codes": sorted(codes),
                    "action": action,
                    "source_candidate_kind": frozen_item.get("candidate_kind"),
                    "source_panel_sha256": frozen_item.get("panel_sha256"),
                    "target_candidate_kind": candidate.get("candidate_kind", "multiphase_rgb"),
                    "target_panel_sha256": candidate.get("panel_sha256"),
                }
            )

        case_dirs = [item for item in staging.iterdir() if item.is_dir()]
        if len(case_dirs) != expected_case_count or len(actions) != expected_case_count:
            raise PipelineError("Remediação não preservou a coorte completa.")
        summary = {
            "unchanged": sum(item["action"] == "unchanged" for item in actions),
            "restored_source_candidate_retained": sum(
                item["action"] == "restored_source_candidate_retained" for item in actions
            ),
            "venous_review_fallback": sum(
                item["action"] == "venous_review_fallback" for item in actions
            ),
        }
        manifest = {
            "schema": REMEDIATION_SCHEMA,
            "source_experiment_signature": freeze["experiment_signature"],
            "case_count": len(actions),
            "triage_case_count": len(triaged),
            "triage_sha256": _sha256(triage_path),
            "review_fallback_config_sha256": _sha256(review_fallback_config),
            "summary": summary,
            "actions": actions,
            "research_only": True,
            "clinical_use_allowed": False,
            "ground_truth_read": False,
            "inference_executed": False,
            "requires_full_human_review": True,
        }
        (staging / "remediation_manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        _publish_directory(staging, output_root)
        return manifest
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise

