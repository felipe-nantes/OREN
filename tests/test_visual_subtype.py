"""Guarda de subtipo e roteamento do modo visual no exame individual.

O ponto sensível: docs/161 mediu que a atribuição de classe é condicionada à
coorte de aquisição. Num exame de origem não vista, o modelo coloca quase toda a
massa nas classes `*_unspecified`, e o argmax entre as quatro classes nomeadas
seria um subtipo inventado sobre ~1% de evidência. Estes testes travam esse
comportamento.
"""
from __future__ import annotations

import pytest

from dtwin.learning.visual_inference import (
    NAMED_LESION_CLASSES,
    NAMED_LESION_MASS_FLOOR,
    resolve_subtype,
)
from webapp.server import _subtype_fields


def test_subtipo_nomeado_quando_a_massa_esta_nas_classes_conhecidas():
    massa = {"fnh": 0.05, "hcc": 0.80, "hemangioma": 0.06, "hepatic_cyst": 0.04,
             "negative_unspecified": 0.03, "positive_unspecified": 0.02}
    r = resolve_subtype(massa)
    assert r["determined"] is True
    assert r["subtype"] == "hcc"
    assert r["subtype_confidence"] == pytest.approx(0.80 / 0.95)


def test_subtipo_recusado_quando_a_massa_vai_para_unspecified():
    # Perfil observado em coortes de outra origem (docs/161: 1,43% e 1,47%).
    massa = {"fnh": 0.004, "hcc": 0.002, "hemangioma": 0.003, "hepatic_cyst": 0.005,
             "negative_unspecified": 0.55, "positive_unspecified": 0.436}
    r = resolve_subtype(massa)
    assert r["determined"] is False
    assert r["subtype"] is None
    assert r["named_lesion_mass"] < NAMED_LESION_MASS_FLOOR
    assert "origem de aquisição" in r["reason"]


def test_limiar_e_uma_fronteira_estrita():
    exatamente_no_piso = {n: NAMED_LESION_MASS_FLOOR / len(NAMED_LESION_CLASSES)
                          for n in NAMED_LESION_CLASSES}
    exatamente_no_piso["negative_unspecified"] = 1.0 - NAMED_LESION_MASS_FLOOR
    assert resolve_subtype(exatamente_no_piso)["determined"] is True

    abaixo = dict(exatamente_no_piso)
    abaixo["fnh"] -= 1e-6
    assert resolve_subtype(abaixo)["determined"] is False


def test_negativo_com_lesao_benigna_ainda_nomeia_o_achado():
    """Triagem negativa NÃO é fígado sem lesão: só o CHC é positivo aqui.

    Caso real observado no benchmark cego (ARGOS-BLIND-0016, verdade FNH): a
    triagem deu NEGATIVA, corretamente, e o modelo identificou FNH com 97,6%.
    Descartar isso perderia informação e afirmaria algo falso.
    """
    subtipo = resolve_subtype({"fnh": 0.9, "negative_unspecified": 0.1})
    campos = _subtype_fields(subtipo, positiva=False)
    assert campos["subtype_determined"] is True
    assert campos["subtype"] == "fnh"
    assert campos["subtype_is_screening_target"] is False
    assert campos["subtype_unavailable_reason"] is None


def test_negativo_cuja_classe_mais_provavel_e_o_alvo_e_sinalizado():
    """Se a triagem diz negativo mas a classe mais provável é CHC, as duas
    leituras discordam e nenhuma pode ser apresentada como conclusão."""
    subtipo = resolve_subtype({"hcc": 0.8, "fnh": 0.15, "negative_unspecified": 0.05})
    campos = _subtype_fields(subtipo, positiva=False)
    assert campos["subtype_is_screening_target"] is True
    assert "discordam" in campos["subtype_unavailable_reason"]


def test_positivo_indeterminado_explica_o_motivo():
    subtipo = resolve_subtype({"fnh": 0.01, "hcc": 0.01,
                               "positive_unspecified": 0.98})
    campos = _subtype_fields(subtipo, positiva=True)
    assert campos["subtype_determined"] is False
    assert campos["subtype_label"] is None
    assert campos["subtype_unavailable_reason"]


def test_positivo_determinado_traz_rotulo_legivel():
    subtipo = resolve_subtype({"hcc": 0.7, "fnh": 0.2, "hemangioma": 0.05,
                               "hepatic_cyst": 0.03, "negative_unspecified": 0.02})
    campos = _subtype_fields(subtipo, positiva=True)
    assert campos["subtype"] == "hcc"
    assert "hepatocelular" in campos["subtype_label"].lower()
    assert campos["subtype_is_screening_target"] is True
    assert 0.0 < campos["subtype_confidence"] <= 1.0


def test_modo_visual_e_reconhecido_no_exame_individual():
    from webapp.server import _is_visual_scenario

    assert _is_visual_scenario("hybrid_supervised") is True
    assert _is_visual_scenario("volumetric_rag") is False
