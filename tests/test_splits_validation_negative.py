"""Testes negativos diretos do validador de splits (PHASE_07 gap G6).

O property test de isolamento só afirmava o braço de vazamento externo;
aqui cada braço fail-closed de ``validate_nested_splits`` é disparado por
uma corrupção dirigida de um artefato válido gerado pelo próprio gerador.
"""
from __future__ import annotations

import copy

import pytest

from dtwin.core import PipelineError
from dtwin.learning.schemas import ProtectedTrainingCase
from dtwin.learning.splits import build_nested_splits, validate_nested_splits


def _cases(count: int = 8) -> list[ProtectedTrainingCase]:
    return [
        ProtectedTrainingCase(
            case_id=f"caso_{index}",
            patient_group_id=f"paciente_{index}",
            dataset_id="ds_sintetico",
            label="POSITIVE" if index % 2 == 0 else "NEGATIVE",
        )
        for index in range(count)
    ]


@pytest.fixture()
def splits_validos() -> dict:
    return build_nested_splits(_cases(), outer_folds=2, inner_folds=2, seed=7)


def test_gerador_exige_ao_menos_um_caso():
    with pytest.raises(PipelineError, match="Nenhum caso dispon"):
        build_nested_splits([], outer_folds=2, inner_folds=2, seed=7)


def test_validador_rejeita_schema_desconhecido(splits_validos):
    corrompido = copy.deepcopy(splits_validos)
    corrompido["schema"] = "schema-desconhecido-v0"
    with pytest.raises(PipelineError, match="Schema de splits inv"):
        validate_nested_splits(corrompido)


def test_validador_rejeita_outer_folds_ausentes(splits_validos):
    corrompido = copy.deepcopy(splits_validos)
    corrompido["outer_folds"] = []
    with pytest.raises(PipelineError, match="Splits externos ausentes"):
        validate_nested_splits(corrompido)


def test_validador_rejeita_caso_duplicado_no_mesmo_fold(splits_validos):
    corrompido = copy.deepcopy(splits_validos)
    fold = corrompido["outer_folds"][0]
    fold["test_case_ids"].append(fold["test_case_ids"][0])
    with pytest.raises(PipelineError, match="duplicado dentro de um fold"):
        validate_nested_splits(corrompido)


def test_validador_rejeita_universos_divergentes_entre_folds(splits_validos):
    corrompido = copy.deepcopy(splits_validos)
    fold = corrompido["outer_folds"][1]
    fold["train_case_ids"] = fold["train_case_ids"][:-1]
    with pytest.raises(PipelineError, match="mesmo universo"):
        validate_nested_splits(corrompido)


def test_validador_rejeita_vazamento_interno(splits_validos):
    corrompido = copy.deepcopy(splits_validos)
    inner = corrompido["outer_folds"][0]["inner_folds"][0]
    inner["validation_case_ids"].append(inner["train_case_ids"][0])
    with pytest.raises(PipelineError, match="validação interna"):
        validate_nested_splits(corrompido)


def test_validador_rejeita_fold_interno_que_nao_cobre_o_treino(splits_validos):
    corrompido = copy.deepcopy(splits_validos)
    inner = corrompido["outer_folds"][0]["inner_folds"][0]
    inner["validation_case_ids"] = inner["validation_case_ids"][:-1]
    with pytest.raises(PipelineError, match="não cobre exatamente o treino"):
        validate_nested_splits(corrompido)


def _move_case_do_teste_para_o_treino(fold: dict, case_id: str) -> None:
    fold["test_case_ids"].remove(case_id)
    fold["train_case_ids"].append(case_id)
    for inner in fold["inner_folds"]:
        inner["train_case_ids"].append(case_id)


def test_validador_rejeita_caso_repetido_em_dois_testes_externos(splits_validos):
    corrompido = copy.deepcopy(splits_validos)
    fold_1, fold_2 = corrompido["outer_folds"]
    emprestado = fold_1["test_case_ids"][0]
    proprio = fold_2["test_case_ids"][0]
    _move_case_do_teste_para_o_treino(fold_2, proprio)
    fold_2["test_case_ids"].append(emprestado)
    fold_2["train_case_ids"].remove(emprestado)
    for inner in fold_2["inner_folds"]:
        if emprestado in inner["train_case_ids"]:
            inner["train_case_ids"].remove(emprestado)
        if emprestado in inner["validation_case_ids"]:
            inner["validation_case_ids"].remove(emprestado)
    with pytest.raises(PipelineError, match="mais de um teste externo"):
        validate_nested_splits(corrompido)


def test_validador_rejeita_caso_que_nunca_e_testado(splits_validos):
    corrompido = copy.deepcopy(splits_validos)
    fold = corrompido["outer_folds"][1]
    _move_case_do_teste_para_o_treino(fold, fold["test_case_ids"][0])
    with pytest.raises(PipelineError, match="uma vez no teste externo"):
        validate_nested_splits(corrompido)


def test_validador_rejeita_case_count_divergente(splits_validos):
    corrompido = copy.deepcopy(splits_validos)
    corrompido["case_count"] = corrompido["case_count"] + 1
    with pytest.raises(PipelineError, match="case_count diverge"):
        validate_nested_splits(corrompido)
