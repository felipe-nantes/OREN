"""Characterization: gerador de splits aninhados (PHASE_03, OBSERVED_BEHAVIOR).

Complementa tests/test_learning_splits.py fixando comportamentos ainda não
protegidos. Não afirma correção; se algo aqui quebrar, o desenho de CV mudou —
consulte .fable/HUMAN_GATES.md (HG-07) e o contrato congelado ARGOS-SCI-003
antes de aceitar a mudança.
"""

from __future__ import annotations

import pytest

from dtwin.core import PipelineError
from dtwin.learning.schemas import ProtectedTrainingCase
from dtwin.learning.splits import build_nested_splits


def _caso(case_id: str, grupo: str, label: str) -> ProtectedTrainingCase:
    return ProtectedTrainingCase(
        case_id=case_id,
        patient_group_id=grupo,
        dataset_id="sintetico",
        label=label,
    )


def _coorte_sintetica(grupos_por_label: int = 10) -> list[ProtectedTrainingCase]:
    casos: list[ProtectedTrainingCase] = []
    for label, prefixo in (("POSITIVE", "pos"), ("NEGATIVE", "neg")):
        for indice in range(grupos_por_label):
            grupo = f"{prefixo}_grupo_{indice:02d}"
            casos.append(_caso(f"{grupo}_a", grupo, label))
            if indice % 3 == 0:  # alguns pacientes com 2 exames
                casos.append(_caso(f"{grupo}_b", grupo, label))
    return casos


def _grupo_do_caso(casos: list[ProtectedTrainingCase]) -> dict[str, str]:
    return {caso.case_id: caso.patient_group_id for caso in casos}


def test_observed_grupo_de_paciente_nunca_cruza_fronteira_interna():
    """OBSERVED_BEHAVIOR: o agrupamento por paciente vale também nos folds
    internos (treino interno × validação), não só na fronteira externa."""
    casos = _coorte_sintetica()
    dono = _grupo_do_caso(casos)
    splits = build_nested_splits(casos)

    for outer in splits["outer_folds"]:
        for inner in outer["inner_folds"]:
            grupos_treino = {dono[c] for c in inner["train_case_ids"]}
            grupos_validacao = {dono[c] for c in inner["validation_case_ids"]}
            assert not (grupos_treino & grupos_validacao)


def test_observed_defaults_congelados_espelham_o_contrato_sci_003():
    """OBSERVED_BEHAVIOR: os defaults da assinatura reproduzem o protocolo
    congelado (outer=5, inner=4, seed=20260724). Mudar um default é mudar o
    protocolo silenciosamente — ARGOS-SCI-003 + HG-07."""
    splits = build_nested_splits(_coorte_sintetica())
    assert splits["outer_fold_count"] == 5
    assert splits["inner_fold_count"] == 4
    assert splits["seed"] == 20260724
    assert len(splits["outer_folds"]) == 5
    assert all(len(o["inner_folds"]) == 4 for o in splits["outer_folds"])


def test_observed_menos_grupos_que_folds_aborta():
    casos = [_caso(f"c{i}", f"g{i}", "POSITIVE") for i in range(3)]
    casos += [_caso(f"n{i}", f"h{i}", "NEGATIVE") for i in range(3)]
    with pytest.raises(PipelineError):
        build_nested_splits(casos, outer_folds=7, inner_folds=2)


def test_observed_classe_sem_grupo_por_fold_aborta():
    casos = [_caso(f"c{i}", f"g{i}", "POSITIVE") for i in range(8)]
    casos += [_caso(f"n{i}", f"h{i}", "NEGATIVE") for i in range(2)]
    with pytest.raises(PipelineError):
        build_nested_splits(casos, outer_folds=4, inner_folds=2)


def test_observed_folds_menor_que_2_aborta():
    with pytest.raises(PipelineError):
        build_nested_splits(_coorte_sintetica(), outer_folds=1, inner_folds=4)


def test_observed_case_id_duplicado_aborta():
    casos = _coorte_sintetica()
    casos.append(casos[0])
    with pytest.raises(PipelineError):
        build_nested_splits(casos)


def test_observed_seed_diferente_gera_atribuicao_diferente():
    casos = _coorte_sintetica()
    testes_a = [
        tuple(o["test_case_ids"]) for o in build_nested_splits(casos, seed=1)["outer_folds"]
    ]
    testes_b = [
        tuple(o["test_case_ids"]) for o in build_nested_splits(casos, seed=2)["outer_folds"]
    ]
    assert testes_a != testes_b
