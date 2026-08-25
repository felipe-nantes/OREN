"""Smoke dos braços consultivos S6 (REF-05/W-019) da volumetria.

A PHASE_07 justificou deixar a graduação consultiva sem teste; este smoke
fecha a lacuna sem tocar produção: cada braço de _volumetry_quality_assessment,
_technical_volume_range, _load_segmentation_quality e measurement_class ganha
um caso determinístico. Escopo honesto preservado: os asserts verificam a
GRADUAÇÃO TÉCNICA declarada, nunca acurácia anatômica.
"""
from __future__ import annotations

import pytest

from dtwin.core import PipelineError
from dtwin.volumetry import (
    _as_3d,
    _load_segmentation_quality,
    _technical_volume_range,
    _volumetry_quality_assessment,
    measurement_class,
)


@pytest.mark.parametrize(
    ("role", "material", "esperado"),
    [
        ("orgao", "anatomy", "whole_liver"),
        ("lesao", "anatomy", "manual_or_provided_lesion"),
        ("candidato", "anatomy", "automatic_unconfirmed_candidate"),
        ("couinaud_iv", "segment", "couinaud_segment"),
        ("veia_porta_esplenica", "vessel", "vascular_structure"),
        ("portal_vein", "anatomy", "vascular_structure"),
        ("regiao_classificada", "anatomy", "classification_support_region"),
        ("vesicula_biliar", "gallbladder", "anatomical_structure"),
    ],
)
def test_measurement_class_cobre_todos_os_bracos(role, material, esperado):
    assert measurement_class(role, material) == esperado


def _liver_record(usable=True, touches_border=False, fraction=1.0):
    return {
        "technical_quality": {"usable": usable},
        "touches_image_border": touches_border,
        "largest_component_fraction": fraction,
    }


def _receipt(dice=None, triggered=False, secondary=True):
    adaptive = {"triggered": triggered}
    if secondary:
        adaptive["secondary"] = {"volume_ml": 1500.0}
    if dice is not None:
        adaptive["agreement"] = {"dice": dice, "jaccard": dice - 0.05}
    return {"adaptive": adaptive}


def test_graduacao_D_quando_mascara_inutilizavel():
    resultado = _volumetry_quality_assessment(_liver_record(usable=False), None)
    assert (resultado["grade"], resultado["usable"]) == ("D", False)
    assert resultado["reasons"] == ["whole_liver_mask_unusable"]


def test_graduacao_A_com_alta_concordancia_e_sem_ressalvas():
    resultado = _volumetry_quality_assessment(_liver_record(), _receipt(dice=0.95))
    assert (resultado["grade"], resultado["label"]) == ("A", "alta_consistencia_tecnica")
    assert resultado["source_agreement"]["dice"] == 0.95


def test_graduacao_A_rebaixa_para_B_com_ressalva_de_borda():
    resultado = _volumetry_quality_assessment(
        _liver_record(touches_border=True), _receipt(dice=0.95)
    )
    assert resultado["grade"] == "B"
    assert "whole_liver_touches_image_border" in resultado["reasons"]


def test_graduacao_C_com_baixa_concordancia():
    resultado = _volumetry_quality_assessment(_liver_record(), _receipt(dice=0.7))
    assert (resultado["grade"], resultado["label"]) == ("C", "revisao_tecnica_recomendada")
    assert "low_mask_source_agreement" in resultado["reasons"]


def test_graduacao_C_quando_confirmacao_secundaria_indisponivel():
    resultado = _volumetry_quality_assessment(
        _liver_record(), _receipt(triggered=True, secondary=False)
    )
    assert resultado["grade"] == "C"
    assert "secondary_confirmation_unavailable" in resultado["reasons"]


def test_graduacao_B_moderada_e_fragmentacao_vira_C():
    moderado = _volumetry_quality_assessment(_liver_record(), _receipt(dice=0.85))
    assert moderado["grade"] == "B"
    fragmentado = _volumetry_quality_assessment(
        _liver_record(fraction=0.9), _receipt(dice=0.85)
    )
    assert fragmentado["grade"] == "C"
    assert "whole_liver_fragmented" in fragmentado["reasons"]


def test_faixa_tecnica_agrega_fontes_do_adaptativo():
    receipt = {
        "adaptive": {
            "primary": {"volume_ml": 1480.0},
            "secondary": {"volume_ml": 1520.0},
            "baseline": {"volume_ml": 0.0},  # ignorado: nao positivo
        }
    }
    faixa = _technical_volume_range(1500.0, receipt)
    assert (faixa["lower_ml"], faixa["upper_ml"]) == (1480.0, 1520.0)
    assert faixa["source_count"] == 3
    assert faixa["interpretation"] == (
        "technical_mask_variation_not_statistical_confidence_interval"
    )
    assert _technical_volume_range(None, receipt) is None


def test_load_segmentation_quality_bracos_defensivos(tmp_path):
    assert _load_segmentation_quality(None) is None
    assert _load_segmentation_quality({"adaptive": {}}) == {"adaptive": {}}
    assert _load_segmentation_quality(tmp_path / "inexistente.json") is None
    corrompido = tmp_path / "corrompido.json"
    corrompido.write_text("{nao é json", encoding="utf-8")
    assert _load_segmentation_quality(corrompido) is None
    lista = tmp_path / "lista.json"
    lista.write_text("[1, 2]", encoding="utf-8")
    assert _load_segmentation_quality(lista) is None


def test_as_3d_espreme_dimensoes_unitarias_e_rejeita_4d_real():
    import numpy as np
    import SimpleITK as sitk

    base = sitk.GetImageFromArray(np.zeros((8, 8, 8), dtype=np.uint8))
    unitario_4d = sitk.JoinSeries([base])  # (8,8,8,1): dimensão extra unitária
    assert unitario_4d.GetDimension() == 4
    assert _as_3d(unitario_4d, "teste").GetDimension() == 3
    genuino_4d = sitk.JoinSeries([base, base])  # (8,8,8,2): 4-D de verdade
    with pytest.raises(PipelineError, match="3-D"):
        _as_3d(genuino_4d, "teste")
