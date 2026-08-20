"""Revisão humana imutável dos painéis públicos OpenSwissHCC."""
from __future__ import annotations

import hashlib
import json
import os
import uuid
from collections.abc import Iterable
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any

from dtwin.benchmark.openswisshcc_alignment import _load_json, _sha256
from dtwin.core import PipelineError

REVIEW_SCHEMA = "argos-public-liver-mri-panel-review-v1"
REQUIRED_CONFIRMATIONS = (
    "no_visible_phi",
    "multiphase_alignment_acceptable",
    "liver_framing_acceptable",
)
SIGNED_REVIEW_FIELDS = (
    "schema",
    "review_status",
    "reviewer",
    "reviewed_at_utc",
    "confirmations",
    "panel_count",
    "panels",
    "research_only",
    "clinical_use_allowed",
    "ground_truth_read",
    "inference_executed",
)


def _review_signature(payload: dict[str, Any]) -> str:
    signed = {key: payload.get(key) for key in SIGNED_REVIEW_FIELDS}
    return hashlib.sha256(
        json.dumps(signed, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        .encode("utf-8")
    ).hexdigest()


def _candidate(panel_root: Path, case_id: str) -> dict[str, Any]:
    if not case_id.startswith("anon-") or any(char in case_id for char in "/\\"):
        raise PipelineError(f"case_id inválido para revisão: {case_id!r}.")
    root = panel_root.resolve()
    case_dir = (root / case_id).resolve()
    if not case_dir.is_relative_to(root) or not case_dir.is_dir():
        raise PipelineError(f"Painel ausente para revisão: {case_id!r}.")
    manifest = _load_json(case_dir / "candidate_manifest.json")
    if manifest.get("case_id") != case_id:
        raise PipelineError("Manifesto candidato pertence a outro caso.")
    if manifest.get("research_only") is not True or manifest.get("clinical_use_allowed") is not False:
        raise PipelineError("Candidato não preserva as salvaguardas de pesquisa.")
    relative = PurePosixPath(str(manifest.get("panel_filename", "")))
    if relative.is_absolute() or ".." in relative.parts or len(relative.parts) != 1:
        raise PipelineError("Caminho do painel candidato é inseguro.")
    panel = (case_dir / relative.name).resolve()
    if not panel.is_relative_to(case_dir) or not panel.is_file():
        raise PipelineError("Arquivo do painel candidato está ausente ou fora do caso.")
    digest = _sha256(panel)
    if digest != manifest.get("panel_sha256"):
        raise PipelineError("Hash do painel candidato é incompatível.")
    if panel.stat().st_size != manifest.get("panel_bytes"):
        raise PipelineError("Tamanho do painel candidato é incompatível.")
    return {
        "case_id": case_id,
        "candidate_signature": str(manifest.get("candidate_signature", "")),
        "candidate_version": str(manifest.get("candidate_version", "")),
        "panel_filename": relative.name,
        "panel_sha256": digest,
        "panel_bytes": panel.stat().st_size,
    }


def ready_case_ids(panel_root: Path) -> list[str]:
    """Liste somente diretórios candidatos pseudonimizados e completos."""
    root = Path(panel_root).resolve()
    if not root.is_dir():
        raise PipelineError("Diretório de painéis não existe.")
    case_ids = sorted(
        item.name
        for item in root.iterdir()
        if item.is_dir()
        and item.name.startswith("anon-")
        and (item / "candidate_manifest.json").is_file()
    )
    if not case_ids:
        raise PipelineError("Nenhum painel candidato pronto para revisão.")
    return case_ids


def create_panel_review(
    *,
    panel_root: Path,
    case_ids: Iterable[str],
    output_path: Path,
    reviewer: str,
    confirmations: dict[str, bool],
) -> dict[str, Any]:
    """Crie uma aprovação separada, vinculada aos hashes dos painéis existentes."""
    panel_root = Path(panel_root).resolve()
    output_path = Path(output_path).resolve()
    reviewer = reviewer.strip()
    if not reviewer or len(reviewer) > 120:
        raise PipelineError("Identificador do revisor é obrigatório e deve ter até 120 caracteres.")
    if any(confirmations.get(key) is not True for key in REQUIRED_CONFIRMATIONS):
        raise PipelineError("Todas as confirmações visuais obrigatórias devem ser explícitas.")
    selected = sorted(set(case_ids))
    if not selected:
        raise PipelineError("Nenhum caso selecionado para revisão.")
    if output_path.exists():
        raise PipelineError("Manifesto de revisão já existe; não será sobrescrito.")

    panels = [_candidate(panel_root, case_id) for case_id in selected]
    payload = {
        "schema": REVIEW_SCHEMA,
        "review_status": "approved_for_research_inference",
        "reviewer": reviewer,
        "reviewed_at_utc": datetime.now(timezone.utc).isoformat(),
        "confirmations": {key: True for key in REQUIRED_CONFIRMATIONS},
        "panel_count": len(panels),
        "panels": panels,
        "research_only": True,
        "clinical_use_allowed": False,
        "ground_truth_read": False,
        "inference_executed": False,
    }
    payload["review_signature"] = _review_signature(payload)
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


def verify_panel_review(
    *,
    review_path: Path,
    panel_root: Path,
    required_case_ids: Iterable[str] | None = None,
) -> dict[str, Any]:
    """Revalide assinatura e bytes aprovados imediatamente antes da inferência."""
    review = _load_json(Path(review_path).resolve())
    if review.get("schema") != REVIEW_SCHEMA:
        raise PipelineError("Schema do manifesto de revisão é incompatível.")
    if set(review) != set(SIGNED_REVIEW_FIELDS) | {"review_signature"}:
        raise PipelineError("Campos do manifesto de revisão são incompatíveis.")
    if review.get("review_status") != "approved_for_research_inference":
        raise PipelineError("Painéis não estão aprovados para inferência de pesquisa.")
    if review.get("research_only") is not True or review.get("clinical_use_allowed") is not False:
        raise PipelineError("Manifesto de revisão perdeu as salvaguardas de pesquisa.")
    confirmations = review.get("confirmations", {})
    if any(confirmations.get(key) is not True for key in REQUIRED_CONFIRMATIONS):
        raise PipelineError("Manifesto não contém todas as confirmações visuais.")
    panels = review.get("panels")
    if not isinstance(panels, list) or not panels:
        raise PipelineError("Manifesto de revisão não contém painéis.")
    if review.get("panel_count") != len(panels):
        raise PipelineError("Contagem de painéis do manifesto é incompatível.")
    if review.get("ground_truth_read") is not False or review.get("inference_executed") is not False:
        raise PipelineError("Manifesto de revisão viola o isolamento metodológico.")
    case_ids = [str(item.get("case_id", "")) for item in panels]
    if len(case_ids) != len(set(case_ids)):
        raise PipelineError("Manifesto de revisão contém casos duplicados.")
    expected = sorted(set(case_ids if required_case_ids is None else required_case_ids))
    if sorted(case_ids) != expected:
        raise PipelineError("Conjunto de casos revisados não corresponde ao solicitado.")
    current = [_candidate(Path(panel_root), case_id) for case_id in sorted(case_ids)]
    if current != panels:
        raise PipelineError("Painel ou manifesto candidato mudou após a revisão humana.")
    if review.get("review_signature") != _review_signature(review):
        raise PipelineError("Assinatura do manifesto de revisão é incompatível.")
    return review
