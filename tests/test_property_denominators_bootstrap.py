"""Property tests — denominadores e bootstrap agrupado (PHASE_04_INVARIANTS).

Contratos científicos congelados:

- `ARGOS-SCI-004`: falhas técnicas, timeouts, inconclusivos e respostas
  inválidas **permanecem no denominador principal**; nunca são removidos após
  a execução. É a regra anti-gaming que impede inflar robustez aparente
  descartando os casos difíceis depois de vê-los.
- `ARGOS-SCI-013`: bootstrap **agrupado por paciente** (2000 reamostragens,
  seed 20260724) — reamostra grupos inteiros, nunca casos individuais.

A cobertura prévia (`tests/test_learning_robustness.py`) exercita coortes
fixas. Aqui os invariantes são generalizados por Hypothesis: valem para
qualquer combinação de rótulos, predições, falhas técnicas e tamanhos de
grupo.

TASK-2026-08-18-PH04-INV-05.
"""

from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from dtwin.core import PipelineError
from dtwin.learning.robustness import (
    _metrics_for,
    bootstrap_confidence_interval,
)
from dtwin.learning.schemas import ProtectedTrainingCase


@st.composite
def coorte_com_resultados(draw, min_grupos: int = 2, max_grupos: int = 7):
    """Gera uma coorte avaliada: grupos de paciente com 1..3 exames, cada
    exame com rótulo, predição, possível falha técnica e possível score."""
    n_grupos = draw(st.integers(min_value=min_grupos, max_value=max_grupos))
    linhas: list[dict] = []
    protegidos: dict[str, ProtectedTrainingCase] = {}

    for indice in range(n_grupos):
        grupo = f"paciente_{indice:03d}"
        label = draw(st.sampled_from(["POSITIVE", "NEGATIVE"]))
        for exame in range(draw(st.integers(min_value=1, max_value=3))):
            case_id = f"{grupo}_exame_{exame}"
            protegidos[case_id] = ProtectedTrainingCase(
                case_id=case_id,
                patient_group_id=grupo,
                dataset_id="coorte_sintetica",
                label=label,
            )
            falha = draw(st.booleans())
            linha: dict = {"case_id": case_id, "technical_failure": falha}
            if not falha:
                linha["prediction"] = draw(st.sampled_from(["POSITIVE", "NEGATIVE"]))
                if draw(st.booleans()):
                    linha["score"] = draw(
                        st.floats(min_value=0.0, max_value=1.0, allow_nan=False)
                    )
            linhas.append(linha)
    return linhas, protegidos


# --------------------------------------------------------------------------- #
# ARGOS-SCI-004 — denominadores
# --------------------------------------------------------------------------- #
@settings(max_examples=250, deadline=None)
@given(dados=coorte_com_resultados())
def test_property_nenhum_caso_escapa_da_matriz_de_confusao(dados):
    """ARGOS-SCI-004, o invariante anti-gaming: tp+tn+fp+fn é SEMPRE igual ao
    número de casos avaliados. Nenhum caso — inclusive falha técnica — pode
    sumir do denominador depois da execução."""
    linhas, protegidos = dados
    metricas = _metrics_for(linhas, protegidos)

    total_classificado = metricas["tp"] + metricas["tn"] + metricas["fp"] + metricas["fn"]
    assert total_classificado == len(linhas) == metricas["case_count"], (
        "caso(s) desapareceram do denominador -- viola ARGOS-SCI-004"
    )


@settings(max_examples=250, deadline=None)
@given(dados=coorte_com_resultados())
def test_property_falha_tecnica_conta_como_erro_nunca_como_acerto(dados):
    """ARGOS-SCI-004: uma falha técnica num positivo é FN; num negativo é FP.
    Jamais TP ou TN. Contar falha como acerto seria premiar o sistema por não
    conseguir responder."""
    linhas, protegidos = dados
    metricas = _metrics_for(linhas, protegidos)

    falhas = sum(1 for linha in linhas if linha.get("technical_failure") is True)
    assert metricas["technical_failures"] == falhas

    positivos = {
        cid for cid, caso in protegidos.items() if caso.label == "POSITIVE"
    }
    falhas_positivas = sum(
        1
        for linha in linhas
        if linha.get("technical_failure") is True and linha["case_id"] in positivos
    )
    falhas_negativas = falhas - falhas_positivas

    # As falhas entram inteiramente em FN/FP, então esses contadores nunca
    # podem ser menores que o número de falhas da respectiva polaridade.
    assert metricas["fn"] >= falhas_positivas
    assert metricas["fp"] >= falhas_negativas


@settings(max_examples=200, deadline=None)
@given(dados=coorte_com_resultados())
def test_property_converter_acerto_em_falha_nunca_melhora_a_metrica(dados):
    """ARGOS-SCI-004 na prática: transformar um caso que acertou numa falha
    técnica só pode PIORAR (ou manter) sensibilidade e especificidade. Se
    melhorasse, haveria incentivo a declarar falha nos casos difíceis."""
    linhas, protegidos = dados
    antes = _metrics_for(linhas, protegidos)

    # encontra o primeiro caso que acertou e o converte em falha técnica
    convertidas = []
    ja_converteu = False
    for linha in linhas:
        copia = dict(linha)
        if not ja_converteu and copia.get("technical_failure") is not True:
            label = protegidos[copia["case_id"]].label
            acertou = (
                (copia.get("prediction") == "POSITIVE" and label == "POSITIVE")
                or (copia.get("prediction") == "NEGATIVE" and label == "NEGATIVE")
            )
            if acertou:
                copia["technical_failure"] = True
                copia.pop("prediction", None)
                ja_converteu = True
        convertidas.append(copia)

    if not ja_converteu:
        return  # coorte sem nenhum acerto; nada a converter

    depois = _metrics_for(convertidas, protegidos)
    assert depois["sensitivity"] <= antes["sensitivity"] + 1e-9
    assert depois["specificity"] <= antes["specificity"] + 1e-9


@settings(max_examples=200, deadline=None)
@given(dados=coorte_com_resultados())
def test_property_sensibilidade_e_especificidade_ficam_em_zero_um(dados):
    linhas, protegidos = dados
    metricas = _metrics_for(linhas, protegidos)
    assert 0.0 <= metricas["sensitivity"] <= 1.0
    assert 0.0 <= metricas["specificity"] <= 1.0
    assert 0.0 <= metricas["balanced_accuracy"] <= 1.0


@settings(max_examples=200, deadline=None)
@given(dados=coorte_com_resultados())
def test_property_gate_75_75_reflete_exatamente_as_metricas(dados):
    """ARGOS-SCI-005: o gate operacional 0,75/0,75 não pode divergir das
    métricas que ele mesmo resume."""
    linhas, protegidos = dados
    metricas = _metrics_for(linhas, protegidos)
    esperado = metricas["sensitivity"] >= 0.75 and metricas["specificity"] >= 0.75
    assert metricas["passed_75_75"] is esperado


# --------------------------------------------------------------------------- #
# ARGOS-SCI-013 — bootstrap agrupado por paciente
# --------------------------------------------------------------------------- #
@settings(max_examples=40, deadline=None)
@given(dados=coorte_com_resultados())
def test_property_bootstrap_reporta_contagem_de_grupos_nao_de_casos(dados):
    """ARGOS-SCI-013: a unidade de reamostragem é o PACIENTE. O relatório tem
    de expor a contagem de grupos, não a de exames — é o que permite auditar
    que a reamostragem não foi feita por caso."""
    linhas, protegidos = dados
    resultado = bootstrap_confidence_interval(linhas, protegidos, n_resamples=25)

    grupos_reais = {caso.patient_group_id for caso in protegidos.values()}
    assert resultado["patient_group_count"] == len(grupos_reais)
    assert resultado["patient_group_count"] <= len(linhas)


@settings(max_examples=40, deadline=None)
@given(dados=coorte_com_resultados())
def test_property_intervalos_do_bootstrap_sao_ordenados_e_limitados(dados):
    """ARGOS-SCI-013: os IC95 do bootstrap são proporções — ordenados e
    dentro de [0, 1], para qualquer coorte."""
    linhas, protegidos = dados
    resultado = bootstrap_confidence_interval(linhas, protegidos, n_resamples=25)

    for chave in ("sensitivity_bootstrap_ci95", "specificity_bootstrap_ci95"):
        baixo, alto = resultado[chave]
        assert 0.0 <= baixo <= 1.0, f"{chave} fora de [0,1]"
        assert 0.0 <= alto <= 1.0, f"{chave} fora de [0,1]"
        assert baixo <= alto, f"{chave} com limites invertidos"


@settings(max_examples=30, deadline=None)
@given(dados=coorte_com_resultados())
def test_property_bootstrap_e_reprodutivel_e_registra_a_procedencia(dados):
    """ARGOS-SCI-013: mesma seed e mesma coorte produzem o mesmo IC, e o
    resultado carrega seed e n_resamples — sem isso o número publicado não é
    reproduzível a partir do artefato."""
    linhas, protegidos = dados
    primeiro = bootstrap_confidence_interval(linhas, protegidos, n_resamples=25, seed=20260724)
    segundo = bootstrap_confidence_interval(linhas, protegidos, n_resamples=25, seed=20260724)

    assert primeiro == segundo
    assert primeiro["seed"] == 20260724
    assert primeiro["n_resamples"] == 25


def test_bootstrap_recusa_coorte_sem_nenhum_grupo():
    """ARGOS-SCI-013: sem grupo de paciente não há unidade de reamostragem —
    falha explícita em vez de intervalo fabricado."""
    with pytest.raises(PipelineError, match="grupo de paciente"):
        bootstrap_confidence_interval([], {}, n_resamples=10)


def test_bootstrap_usa_o_default_congelado_de_2000_reamostragens():
    """ARGOS-SCI-013 congela `patient_grouped_bootstrap_resamples: 2000`.
    Mudar o default silenciosamente alteraria a largura dos IC publicados."""
    import inspect

    assinatura = inspect.signature(bootstrap_confidence_interval)
    assert assinatura.parameters["n_resamples"].default == 2000
    assert assinatura.parameters["seed"].default == 20260724
