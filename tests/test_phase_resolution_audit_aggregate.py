"""Testes do agregador de auditoria de resolução de fase (ROB-08/W-039).

Os campos aditivos do item 14 (ambiguous_text_roles /
unselected_eligible_dynamic_series) eram gravados por manifesto e nunca
agregados. O agregador é leitura pura — estes testes pinam o contrato.
"""
from __future__ import annotations

from dtwin.learning.raw_dicom_phase_resolver import aggregate_phase_resolution_audit


def _manifesto(method="dicom_text_semantics", confidence=0.9, ambiguas=0, nao_sel=0):
    return {
        "schema": "argos-raw-dicom-phase-resolution-v1",
        "method": method,
        "confidence": confidence,
        "series_with_ambiguous_text_roles": ambiguas,
        "unselected_eligible_dynamic_series": nao_sel,
    }


def test_agregado_vazio_e_bem_definido():
    resumo = aggregate_phase_resolution_audit([])
    assert resumo["cases_total"] == 0
    assert resumo["methods"] == {}
    assert resumo["confidence_min"] is None
    assert resumo["confidence_mean"] is None
    assert resumo["series_with_ambiguous_text_roles_total"] == 0
    assert resumo["research_only"] is True
    assert resumo["clinical_use_allowed"] is False


def test_agrega_metodos_confianca_e_contagens():
    resumo = aggregate_phase_resolution_audit([
        _manifesto(confidence=1.0),
        _manifesto(method="post_contrast_order", confidence=0.6, ambiguas=2, nao_sel=1),
        _manifesto(confidence=0.8, ambiguas=1),
    ])
    assert resumo["cases_total"] == 3
    assert resumo["methods"] == {"dicom_text_semantics": 2, "post_contrast_order": 1}
    assert resumo["confidence_min"] == 0.6
    assert abs(resumo["confidence_mean"] - 0.8) < 1e-12
    assert resumo["series_with_ambiguous_text_roles_total"] == 3
    assert resumo["cases_with_ambiguous_text_roles"] == 2
    assert resumo["unselected_eligible_dynamic_series_total"] == 1
    assert resumo["cases_with_unselected_eligible_dynamic_series"] == 1


def test_manifesto_sem_campos_de_auditoria_conta_como_zero():
    # manifestos anteriores ao item 14 nao tem os campos; o agregador nao quebra
    resumo = aggregate_phase_resolution_audit([
        {"method": "dicom_text_semantics", "confidence": 1.0},
    ])
    assert resumo["cases_total"] == 1
    assert resumo["series_with_ambiguous_text_roles_total"] == 0
    assert resumo["cases_with_unselected_eligible_dynamic_series"] == 0
