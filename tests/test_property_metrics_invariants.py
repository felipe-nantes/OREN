"""Property tests — estatística de proporções e denominadores (PHASE_04).

Contratos científicos congelados:

- `ARGOS-SCI-013`: intervalo de confiança de proporções por **Wilson 95%**
  (não normal/Wald), bootstrap agrupado por paciente, AUC como secundário.
- `ARGOS-SCI-004`: falhas técnicas, timeouts, respostas inválidas e
  inconclusivos **permanecem no denominador principal** — nunca são removidos
  após a execução para inflar robustez aparente.

O Wilson é escolhido justamente porque o intervalo de Wald degenera nos
extremos (p=0 ou p=1 produzem largura zero, e proporções pequenas produzem
limite inferior negativo). Os testes abaixo fixam essas propriedades, que são
a razão de o contrato existir — não apenas a fórmula.

TASK-2026-08-18-PH04-INV-04.
"""

from __future__ import annotations

import math

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from dtwin.benchmark.metrics import wilson_interval


@settings(max_examples=300, deadline=None)
@given(
    total=st.integers(min_value=1, max_value=5000),
    fracao=st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
)
def test_property_wilson_sempre_dentro_de_zero_um_e_ordenado(total, fracao):
    """ARGOS-SCI-013: um IC de proporção nunca pode sair de [0, 1] nem ter
    limite inferior acima do superior. É exatamente onde o intervalo de Wald
    falha para proporções extremas."""
    sucessos = min(total, max(0, round(fracao * total)))
    intervalo = wilson_interval(sucessos, total)

    assert intervalo is not None
    assert 0.0 <= intervalo["low"] <= 1.0
    assert 0.0 <= intervalo["high"] <= 1.0
    assert intervalo["low"] <= intervalo["high"]


@settings(max_examples=200, deadline=None)
@given(total=st.integers(min_value=1, max_value=5000))
def test_property_wilson_nao_degenera_nos_extremos(total):
    """ARGOS-SCI-013, a propriedade que motiva escolher Wilson: com 0 ou 100%
    de sucesso o intervalo continua tendo largura > 0 — reconhece a incerteza
    da amostra finita, ao contrário do Wald, que colapsa para [0,0] / [1,1]."""
    zero = wilson_interval(0, total)
    cheio = wilson_interval(total, total)

    assert zero["low"] == 0.0
    assert zero["high"] > 0.0, "Wilson colapsou em p=0 -- comportamento de Wald"
    assert cheio["high"] == 1.0
    assert cheio["low"] < 1.0, "Wilson colapsou em p=1 -- comportamento de Wald"


@settings(max_examples=200, deadline=None)
@given(
    total=st.integers(min_value=2, max_value=2000),
    fracao=st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
)
def test_property_wilson_contem_a_proporcao_observada(total, fracao):
    """ARGOS-SCI-013: o intervalo tem de conter a proporção pontual observada
    (com folga do arredondamento de 4 casas aplicado pela implementação)."""
    sucessos = min(total, max(0, round(fracao * total)))
    proporcao = sucessos / total
    intervalo = wilson_interval(sucessos, total)

    assert intervalo["low"] <= proporcao + 1e-4
    assert intervalo["high"] >= proporcao - 1e-4


@settings(max_examples=150, deadline=None)
@given(
    total=st.integers(min_value=10, max_value=400),
    fracao=st.floats(min_value=0.1, max_value=0.9, allow_nan=False),
)
def test_property_mais_amostras_nao_alargam_o_intervalo(total, fracao):
    """ARGOS-SCI-013: mantida a proporção, quadruplicar o n não pode ALARGAR
    o intervalo. Protege contra uma troca de fórmula que perdesse a
    dependência correta de n."""
    sucessos = max(1, min(total - 1, round(fracao * total)))
    pequeno = wilson_interval(sucessos, total)
    grande = wilson_interval(sucessos * 4, total * 4)

    largura_pequena = pequeno["high"] - pequeno["low"]
    largura_grande = grande["high"] - grande["low"]
    assert largura_grande <= largura_pequena + 1e-4


def test_wilson_recusa_denominador_vazio_em_vez_de_inventar_intervalo():
    """ARGOS-SCI-004/013: sem denominador não existe estimativa. A função
    devolve None explicitamente em vez de fabricar um intervalo."""
    assert wilson_interval(0, 0) is None
    assert wilson_interval(5, 0) is None
    assert wilson_interval(0, -1) is None


@pytest.mark.parametrize("confianca", [0.0, 1.0, -0.1, 1.5])
def test_wilson_rejeita_nivel_de_confianca_invalido(confianca):
    with pytest.raises(ValueError):
        wilson_interval(1, 10, confidence=confianca)


@settings(max_examples=120, deadline=None)
@given(
    total=st.integers(min_value=5, max_value=1000),
    fracao=st.floats(min_value=0.05, max_value=0.95, allow_nan=False),
)
def test_property_confianca_maior_produz_intervalo_maior(total, fracao):
    """ARGOS-SCI-013: 99% tem de ser ao menos tão largo quanto 95%. Um
    intervalo que ignorasse o nível de confiança passaria despercebido sem
    esta propriedade."""
    sucessos = max(1, min(total - 1, round(fracao * total)))
    noventa_e_cinco = wilson_interval(sucessos, total, confidence=0.95)
    noventa_e_nove = wilson_interval(sucessos, total, confidence=0.99)

    largura_95 = noventa_e_cinco["high"] - noventa_e_cinco["low"]
    largura_99 = noventa_e_nove["high"] - noventa_e_nove["low"]
    assert largura_99 >= largura_95 - 1e-4


@pytest.mark.parametrize(
    "sucessos, total, low_esperado, high_esperado",
    [
        # Valores conferidos contra uma reimplementação independente da fórmula
        # de Wilson (score interval), incluindo os extremos onde o Wald falha.
        (81, 263, 0.255289, 0.366210),
        (0, 50, 0.000000, 0.071348),
        (50, 50, 0.928652, 1.000000),
        (1, 10, 0.017876, 0.404150),
        (500, 1000, 0.469070, 0.530930),
    ],
)
def test_wilson_bate_com_calculo_independente(sucessos, total, low_esperado, high_esperado):
    """Âncora numérica: evita que as propriedades acima sejam satisfeitas por
    uma fórmula errada porém internamente consistente. Os valores vêm de uma
    reimplementação independente do score interval de Wilson, não da própria
    implementação sob teste."""
    intervalo = wilson_interval(sucessos, total, confidence=0.95)
    assert math.isclose(intervalo["low"], low_esperado, abs_tol=1e-4)
    assert math.isclose(intervalo["high"], high_esperado, abs_tol=1e-4)
