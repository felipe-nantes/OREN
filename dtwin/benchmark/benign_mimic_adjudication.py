"""Auditável second-stage adjudication for HCC versus benign liver mimics.

This module intentionally consumes only two already validated MedGemma report
envelopes.  It never reads benchmark labels or lesion masks and it does not
invent a diagnosis from free text.  The output is an experimental research
decision that still requires human review.
"""
from __future__ import annotations

import json
import hashlib
from pathlib import Path
from typing import Any

from dtwin.core import PipelineError, now_utc, sha256_of
from dtwin.medgemma_screening import _write_json_atomic


SCHEMA = "argos-hcc-benign-mimic-adjudication-v1"
TARGET = "lesao_focal_hepatica_suspeita"
VALID_STATES = {"POSITIVA", "NEGATIVA", "INCONCLUSIVA"}
CONFIDENT_NEGATIVE = {"moderada", "alta"}


def _canonical_sha(value: dict[str, Any]) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _read_envelope(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PipelineError(f"{label} ausente ou inválido.") from exc
    if not isinstance(value, dict):
        raise PipelineError(f"{label} deve ser um objeto JSON.")
    return value


def _report(envelope: dict[str, Any], label: str, *, require_v2: bool) -> dict[str, Any]:
    report = envelope.get("report")
    if not isinstance(report, dict) or report.get("resultado_hipotese") not in VALID_STATES:
        raise PipelineError(f"{label} sem relatório MedGemma válido.")
    if envelope.get("regulatory_mode") != "RESEARCH" or envelope.get("requires_human_review") is not True:
        raise PipelineError(f"{label} não preserva salvaguardas de pesquisa.")
    if envelope.get("lesion_pre_marked") is not False:
        raise PipelineError(f"{label} não demonstra ausência de lesão pré-marcada.")
    if not require_v2:
        return report
    required = {
        "alvo_da_triagem",
        "ha_lesao_focal_suspeita",
        "ha_variante_anatomica_benigna",
        "ha_pseudolesao_ou_artefato",
        "tipo_alteracao_nao_alvo",
        "justificativa_da_separacao",
    }
    if not required <= set(report):
        raise PipelineError(f"{label} não tem schema pathology-target v2 completo.")
    if report["alvo_da_triagem"] != TARGET:
        raise PipelineError(f"{label} possui alvo de triagem incompatível.")
    if not isinstance(report["ha_lesao_focal_suspeita"], bool):
        raise PipelineError(f"{label} tem flag de lesão focal inválida.")
    if report["resultado_hipotese"] == "POSITIVA" and report["ha_lesao_focal_suspeita"] is not True:
        raise PipelineError(f"{label} positiva sem lesão focal suspeita.")
    return report


def adjudicate_hcc_vs_benign_mimic(
    *, first_pass_path: Path, discriminator_path: Path, output_path: Path
) -> dict[str, Any]:
    """Apply the frozen conservative rule to two reports of the same panel set.

    A second read never upgrades an initial negative.  It can clear an initial
    positive only when it is a complete pathology-target v2 report, explicitly
    has no suspicious focal lesion and is at least moderately confident.  A
    disagreement remains inconclusive, which is intentionally conservative for
    benchmark metrics.
    """
    first_pass_path = Path(first_pass_path).resolve()
    discriminator_path = Path(discriminator_path).resolve()
    output_path = Path(output_path).resolve()
    if output_path.exists():
        raise PipelineError("Adjudicação HCC/benigno já existe; sobrescrita recusada.")
    first = _read_envelope(first_pass_path, "Relatório de primeira passagem")
    second = _read_envelope(discriminator_path, "Relatório discriminador")
    if first.get("case_id") != second.get("case_id") or not first.get("case_id"):
        raise PipelineError("Relatórios de casos distintos não podem ser adjudicados.")
    if first.get("input_panel_set_sha256") != second.get("input_panel_set_sha256"):
        raise PipelineError("A releitura não usou exatamente o mesmo conjunto de painéis.")
    if first.get("screening_config_sha256") == second.get("screening_config_sha256"):
        raise PipelineError("A releitura deve usar configuração/prompt distinto da primeira passagem.")
    primary = _report(first, "Relatório de primeira passagem", require_v2=False)
    discriminator = _report(second, "Relatório discriminador", require_v2=True)
    primary_state = primary["resultado_hipotese"]
    second_state = discriminator["resultado_hipotese"]
    cleared_by_second_read = False
    if primary_state == "NEGATIVA":
        final_state, rule = "NEGATIVA", "preserve_initial_negative"
    elif primary_state == "INCONCLUSIVA":
        final_state, rule = "INCONCLUSIVA", "preserve_initial_inconclusive"
    elif second_state == "POSITIVA":
        final_state, rule = "POSITIVA", "both_reads_positive"
    elif second_state == "INCONCLUSIVA":
        final_state, rule = "INCONCLUSIVA", "positive_then_discriminator_inconclusive"
    elif (
        discriminator["ha_lesao_focal_suspeita"] is False
        and discriminator.get("confianca") in CONFIDENT_NEGATIVE
    ):
        final_state, rule = "NEGATIVA", "positive_cleared_by_confident_no_focal_lesion_second_read"
        cleared_by_second_read = True
    else:
        final_state, rule = "INCONCLUSIVA", "positive_then_low_confidence_negative_second_read"
    base = {
        "schema": SCHEMA,
        "case_id": first["case_id"],
        "status": "pending_human_review",
        "regulatory_mode": "RESEARCH",
        "target_condition": TARGET,
        "first_pass": {
            "report_sha256": sha256_of(first_pass_path),
            "screening_config_sha256": first["screening_config_sha256"],
            "decision": primary_state,
        },
        "benign_mimic_discriminator": {
            "report_sha256": sha256_of(discriminator_path),
            "screening_config_sha256": second["screening_config_sha256"],
            "decision": second_state,
            "confidence": discriminator.get("confianca"),
            "has_suspicious_focal_lesion": discriminator["ha_lesao_focal_suspeita"],
            "has_benign_anatomic_variant": discriminator["ha_variante_anatomica_benigna"],
            "has_pseudolesion_or_artifact": discriminator["ha_pseudolesao_ou_artefato"],
            "non_target_alteration_type": discriminator["tipo_alteracao_nao_alvo"],
        },
        "final_decision": final_state,
        "aggregation_rule": rule,
        "cleared_by_second_read": cleared_by_second_read,
        "ground_truth_read": False,
        "lesion_masks_read": 0,
        "lesion_masks_used": False,
        "research_only": True,
        "clinical_use_allowed": False,
        "requires_human_review": True,
        "created_at": now_utc(),
    }
    result = {**base, "adjudication_signature": _canonical_sha(base)}
    output_path.parent.mkdir(parents=True, exist_ok=True)
    _write_json_atomic(output_path, result)
    return result


__all__ = ["SCHEMA", "adjudicate_hcc_vs_benign_mimic"]
