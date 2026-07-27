"""Deterministic, patient-grouped nested split generation."""
from __future__ import annotations

import hashlib
import random
from collections import Counter, defaultdict
from typing import Any, Iterable

from dtwin.core import PipelineError
from dtwin.learning.schemas import ProtectedTrainingCase, SPLIT_SCHEMA


def _stable_seed(seed: int, token: str) -> int:
    digest = hashlib.sha256(f"{seed}:{token}".encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big")


def _group_cases(
    cases: Iterable[ProtectedTrainingCase],
) -> dict[str, list[ProtectedTrainingCase]]:
    groups: dict[str, list[ProtectedTrainingCase]] = defaultdict(list)
    seen_case_ids: set[str] = set()
    for case in cases:
        case.validate()
        if case.case_id in seen_case_ids:
            raise PipelineError(f"case_id duplicado: {case.case_id}")
        seen_case_ids.add(case.case_id)
        groups[case.patient_group_id].append(case)
    if not groups:
        raise PipelineError("Nenhum caso disponível para gerar folds.")
    for group_id, rows in groups.items():
        labels = {row.label for row in rows}
        if len(labels) != 1:
            raise PipelineError(
                f"patient_group_id {group_id!r} possui labels conflitantes."
            )
    return dict(groups)


def _assign_groups(
    groups: dict[str, list[ProtectedTrainingCase]],
    *,
    folds: int,
    seed: int,
) -> list[list[str]]:
    if folds < 2:
        raise PipelineError("folds deve ser >= 2.")
    if len(groups) < folds:
        raise PipelineError("Há menos grupos de pacientes do que folds.")

    by_label: dict[str, list[str]] = defaultdict(list)
    for group_id, rows in groups.items():
        by_label[rows[0].label].append(group_id)
    if any(len(values) < folds for values in by_label.values()):
        raise PipelineError(
            "Cada classe deve possuir ao menos um grupo por fold."
        )

    assignments: list[list[str]] = [[] for _ in range(folds)]
    fold_label_counts = [Counter() for _ in range(folds)]
    fold_case_counts = [0 for _ in range(folds)]

    ordered: list[tuple[str, str, int, float]] = []
    for label, group_ids in sorted(by_label.items()):
        rng = random.Random(_stable_seed(seed, label))
        shuffled = list(group_ids)
        rng.shuffle(shuffled)
        for group_id in shuffled:
            ordered.append(
                (group_id, label, len(groups[group_id]), rng.random())
            )
    ordered.sort(key=lambda item: (-item[2], item[1], item[3], item[0]))

    for group_id, label, case_count, _ in ordered:
        target = min(
            range(folds),
            key=lambda index: (
                fold_label_counts[index][label],
                fold_case_counts[index],
                index,
            ),
        )
        assignments[target].append(group_id)
        fold_label_counts[target][label] += case_count
        fold_case_counts[target] += case_count

    return [sorted(values) for values in assignments]


def _case_ids(
    groups: dict[str, list[ProtectedTrainingCase]], group_ids: Iterable[str]
) -> list[str]:
    return sorted(
        case.case_id
        for group_id in group_ids
        for case in groups[group_id]
    )


def build_nested_splits(
    cases: Iterable[ProtectedTrainingCase],
    *,
    outer_folds: int = 5,
    inner_folds: int = 4,
    seed: int = 20260724,
) -> dict[str, Any]:
    """Return explicit nested splits with no labels in the output artifact."""

    groups = _group_cases(cases)
    outer_assignments = _assign_groups(groups, folds=outer_folds, seed=seed)
    all_groups = set(groups)
    outer_rows: list[dict[str, Any]] = []

    for outer_index, test_groups in enumerate(outer_assignments):
        test_set = set(test_groups)
        train_groups = sorted(all_groups - test_set)
        inner_source = {key: groups[key] for key in train_groups}
        inner_assignments = _assign_groups(
            inner_source,
            folds=inner_folds,
            seed=_stable_seed(seed, f"outer-{outer_index}"),
        )
        inner_rows: list[dict[str, Any]] = []
        for inner_index, validation_groups in enumerate(inner_assignments):
            validation_set = set(validation_groups)
            inner_train_groups = sorted(set(train_groups) - validation_set)
            inner_rows.append(
                {
                    "inner_fold": inner_index,
                    "train_case_ids": _case_ids(groups, inner_train_groups),
                    "validation_case_ids": _case_ids(
                        groups, validation_groups
                    ),
                }
            )
        outer_rows.append(
            {
                "outer_fold": outer_index,
                "train_case_ids": _case_ids(groups, train_groups),
                "test_case_ids": _case_ids(groups, test_groups),
                "inner_folds": inner_rows,
            }
        )

    result = {
        "schema": SPLIT_SCHEMA,
        "seed": seed,
        "outer_fold_count": outer_folds,
        "inner_fold_count": inner_folds,
        "case_count": sum(len(rows) for rows in groups.values()),
        "patient_group_count": len(groups),
        "outer_folds": outer_rows,
    }
    validate_nested_splits(result)
    return result


def validate_nested_splits(value: dict[str, Any]) -> None:
    if value.get("schema") != SPLIT_SCHEMA:
        raise PipelineError("Schema de splits inválido.")
    outer_rows = value.get("outer_folds")
    if not isinstance(outer_rows, list) or not outer_rows:
        raise PipelineError("Splits externos ausentes.")
    universe: set[str] | None = None
    all_outer_tests: list[str] = []
    for outer in outer_rows:
        train = list(outer.get("train_case_ids") or [])
        test = list(outer.get("test_case_ids") or [])
        if len(train) != len(set(train)) or len(test) != len(set(test)):
            raise PipelineError("Caso duplicado dentro de um fold externo.")
        if set(train) & set(test):
            raise PipelineError("Vazamento entre treino e teste externo.")
        current = set(train) | set(test)
        universe = current if universe is None else universe
        if current != universe:
            raise PipelineError("Folds externos não cobrem o mesmo universo.")
        all_outer_tests.extend(test)
        for inner in outer.get("inner_folds") or []:
            inner_train = set(inner.get("train_case_ids") or [])
            validation = set(inner.get("validation_case_ids") or [])
            if inner_train & validation:
                raise PipelineError("Vazamento entre treino e validação interna.")
            if inner_train | validation != set(train):
                raise PipelineError(
                    "Fold interno não cobre exatamente o treino externo."
                )
    if len(all_outer_tests) != len(set(all_outer_tests)):
        raise PipelineError("Caso aparece em mais de um teste externo.")
    if universe is None or set(all_outer_tests) != universe:
        raise PipelineError("Cada caso deve aparecer uma vez no teste externo.")
    if len(universe) != int(value.get("case_count", -1)):
        raise PipelineError("case_count diverge dos folds.")
