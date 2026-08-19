"""Property tests — isolamento por paciente nos splits (PHASE_04_INVARIANTS).

Contrato científico congelado `ARGOS-SCI-003` (nested patient-grouped CV,
outer=5 / inner=4 / seed=20260724, `threshold_selection: inner_oof_only`,
`preprocessing_fit_scope: training_fold_only`) e `ARGOS-SCI-008` (isolamento de
ground truth / anti-gaming).

A cobertura existente (`tests/test_learning_splits.py`,
`tests/test_characterization_nested_splits.py`) exercita coortes FIXAS. Aqui o
invariante é generalizado: para QUALQUER forma de coorte válida — número de
grupos, exames por paciente, balanço de classes — nenhum grupo de paciente
pode cruzar nenhuma fronteira de split. Leakage por grupo é o modo de falha
que infla silenciosamente a estimativa interna do manuscrito; um invariante
que só vale para uma coorte de exemplo não protege contra ele.

TASK-2026-08-18-PH04-INV-04.
"""

from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from dtwin.learning.schemas import ProtectedTrainingCase
from dtwin.learning.splits import build_nested_splits, validate_nested_splits


@st.composite
def coorte_valida(draw):
    """Gera coortes de formas variadas que satisfazem as precondições do
    gerador (grupos suficientes por classe para outer e inner folds).

    Varia deliberadamente: nº de grupos por classe, nº de exames por paciente
    (1..3, simulando pacientes com múltiplos exames) e o balanço entre classes.
    """
    outer = draw(st.integers(min_value=2, max_value=4))
    inner = draw(st.integers(min_value=2, max_value=3))
    # Margem necessária: após retirar o fold externo, cada classe ainda precisa
    # de >= `inner` grupos. O treino externo fica com ~G*(outer-1)/outer grupos
    # por classe, logo G >= inner*outer/(outer-1); o +2 absorve o arredondamento
    # do balanceamento por classe (a atribuição não é perfeitamente uniforme).
    minimo = inner * outer // (outer - 1) + 2
    grupos_pos = draw(st.integers(min_value=minimo, max_value=minimo + 5))
    grupos_neg = draw(st.integers(min_value=minimo, max_value=minimo + 5))

    casos: list[ProtectedTrainingCase] = []
    for label, prefixo, quantidade in (
        ("POSITIVE", "pos", grupos_pos),
        ("NEGATIVE", "neg", grupos_neg),
    ):
        for indice in range(quantidade):
            grupo = f"{prefixo}_paciente_{indice:03d}"
            exames = draw(st.integers(min_value=1, max_value=3))
            for exame in range(exames):
                casos.append(
                    ProtectedTrainingCase(
                        case_id=f"{grupo}_exame_{exame}",
                        patient_group_id=grupo,
                        dataset_id=draw(st.sampled_from(["coorte_a", "coorte_b"])),
                        label=label,
                    )
                )
    return casos, outer, inner


def _grupo_por_caso(casos: list[ProtectedTrainingCase]) -> dict[str, str]:
    return {caso.case_id: caso.patient_group_id for caso in casos}


@settings(max_examples=120, deadline=None)
@given(dados=coorte_valida())
def test_property_nenhum_grupo_de_paciente_cruza_qualquer_fronteira(dados):
    """ARGOS-SCI-003 / ARGOS-SCI-008, o invariante central: em nenhuma
    fronteira — externa (treino×teste) ou interna (treino×validação) — um
    mesmo paciente aparece dos dois lados. Vale para qualquer coorte."""
    casos, outer, inner = dados
    dono = _grupo_por_caso(casos)
    splits = build_nested_splits(casos, outer_folds=outer, inner_folds=inner)

    for fold_externo in splits["outer_folds"]:
        grupos_treino = {dono[c] for c in fold_externo["train_case_ids"]}
        grupos_teste = {dono[c] for c in fold_externo["test_case_ids"]}
        assert not (grupos_treino & grupos_teste), (
            "grupo de paciente cruzou a fronteira EXTERNA: "
            f"{sorted(grupos_treino & grupos_teste)}"
        )
        for fold_interno in fold_externo["inner_folds"]:
            grupos_treino_interno = {dono[c] for c in fold_interno["train_case_ids"]}
            grupos_validacao = {dono[c] for c in fold_interno["validation_case_ids"]}
            assert not (grupos_treino_interno & grupos_validacao), (
                "grupo de paciente cruzou a fronteira INTERNA: "
                f"{sorted(grupos_treino_interno & grupos_validacao)}"
            )


@settings(max_examples=120, deadline=None)
@given(dados=coorte_valida())
def test_property_cada_exame_aparece_exatamente_uma_vez_no_teste_externo(dados):
    """ARGOS-SCI-003: a predição out-of-fold externa cobre a coorte inteira
    sem repetição -- é o que torna a estimativa honesta e o denominador
    reconciliável com ARGOS-SCI-002."""
    casos, outer, inner = dados
    splits = build_nested_splits(casos, outer_folds=outer, inner_folds=inner)

    testes = [c for fold in splits["outer_folds"] for c in fold["test_case_ids"]]
    assert len(testes) == len(set(testes)), "exame apareceu em mais de um teste externo"
    assert set(testes) == {caso.case_id for caso in casos}, (
        "cobertura externa não bate com a coorte"
    )


@settings(max_examples=120, deadline=None)
@given(dados=coorte_valida())
def test_property_folds_internos_particionam_exatamente_o_treino_externo(dados):
    """ARGOS-SCI-003 (`preprocessing_fit_scope: training_fold_only`): o ciclo
    interno enxerga exatamente o treino externo -- nunca um exame de teste,
    nunca um exame de fora da coorte."""
    casos, outer, inner = dados
    splits = build_nested_splits(casos, outer_folds=outer, inner_folds=inner)

    for fold_externo in splits["outer_folds"]:
        treino_externo = set(fold_externo["train_case_ids"])
        teste_externo = set(fold_externo["test_case_ids"])
        for fold_interno in fold_externo["inner_folds"]:
            treino_interno = set(fold_interno["train_case_ids"])
            validacao = set(fold_interno["validation_case_ids"])
            assert treino_interno | validacao == treino_externo, (
                "fold interno não cobre exatamente o treino externo"
            )
            assert not ((treino_interno | validacao) & teste_externo), (
                "fold interno enxergou exame do teste externo -- leakage"
            )


@settings(max_examples=120, deadline=None)
@given(dados=coorte_valida())
def test_property_artefato_de_splits_nao_carrega_nenhum_label(dados):
    """ARGOS-SCI-008: o artefato de splits é consumido por etapas que não
    podem ver ground truth. Nenhum label pode vazar para dentro dele, em
    nenhuma coorte."""
    casos, outer, inner = dados
    splits = build_nested_splits(casos, outer_folds=outer, inner_folds=inner)

    serializado = repr(splits)
    assert "POSITIVE" not in serializado
    assert "NEGATIVE" not in serializado


@settings(max_examples=60, deadline=None)
@given(dados=coorte_valida())
def test_property_geracao_e_deterministica_para_a_mesma_seed(dados):
    """ARGOS-SCI-003 (`seed: 20260724` congelada): a mesma coorte e a mesma
    seed produzem exatamente os mesmos folds -- requisito de reprodutibilidade
    do ledger da Etapa C."""
    casos, outer, inner = dados
    primeiro = build_nested_splits(casos, outer_folds=outer, inner_folds=inner, seed=20260724)
    segundo = build_nested_splits(casos, outer_folds=outer, inner_folds=inner, seed=20260724)
    assert primeiro == segundo


@settings(max_examples=60, deadline=None)
@given(dados=coorte_valida())
def test_property_o_validador_aceita_o_que_o_gerador_produz(dados):
    """Consistência interna: `validate_nested_splits` é o guardião usado por
    consumidores; ele nunca pode rejeitar um artefato legítimo do gerador."""
    casos, outer, inner = dados
    splits = build_nested_splits(casos, outer_folds=outer, inner_folds=inner)
    validate_nested_splits(splits)  # não deve levantar


def test_validador_detecta_leakage_de_grupo_injetado_manualmente():
    """Poder discriminador do guardião: um artefato adulterado — mesmo exame
    no treino e no teste externo — tem de ser recusado."""
    from dtwin.core import PipelineError

    casos = [
        ProtectedTrainingCase(
            case_id=f"{prefixo}_{i}_e0",
            patient_group_id=f"{prefixo}_{i}",
            dataset_id="coorte_a",
            label=label,
        )
        for label, prefixo in (("POSITIVE", "pos"), ("NEGATIVE", "neg"))
        for i in range(6)
    ]
    splits = build_nested_splits(casos, outer_folds=3, inner_folds=2)

    # injeta leakage: um exame do teste também no treino do mesmo fold
    contaminado = splits["outer_folds"][0]["test_case_ids"][0]
    splits["outer_folds"][0]["train_case_ids"].append(contaminado)

    with pytest.raises(PipelineError, match="[Vv]azamento"):
        validate_nested_splits(splits)
