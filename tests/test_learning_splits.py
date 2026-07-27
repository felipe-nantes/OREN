from __future__ import annotations

import copy

import pytest

from dtwin.core import PipelineError
from dtwin.learning.schemas import ProtectedTrainingCase
from dtwin.learning.splits import build_nested_splits, validate_nested_splits


def _cases(count: int = 40) -> list[ProtectedTrainingCase]:
    return [
        ProtectedTrainingCase(
            case_id=f"case-{index:03d}",
            patient_group_id=f"patient-{index:03d}",
            dataset_id="dataset-a" if index % 3 else "dataset-b",
            label="POSITIVE" if index % 2 else "NEGATIVE",
        )
        for index in range(count)
    ]


def test_nested_splits_are_deterministic_and_label_free():
    first = build_nested_splits(_cases(), outer_folds=5, inner_folds=4, seed=7)
    second = build_nested_splits(_cases(), outer_folds=5, inner_folds=4, seed=7)
    assert first == second
    assert "POSITIVE" not in str(first)
    assert "NEGATIVE" not in str(first)


def test_each_case_is_external_test_exactly_once():
    result = build_nested_splits(_cases(), outer_folds=5, inner_folds=4)
    tests = [
        case_id
        for fold in result["outer_folds"]
        for case_id in fold["test_case_ids"]
    ]
    assert sorted(tests) == sorted(case.case_id for case in _cases())
    assert len(tests) == len(set(tests))


def test_patient_group_never_crosses_external_boundary():
    cases = _cases()
    cases.extend(
        [
            ProtectedTrainingCase(
                case_id="case-related-a",
                patient_group_id="patient-001",
                dataset_id="dataset-a",
                label="POSITIVE",
            ),
            ProtectedTrainingCase(
                case_id="case-related-b",
                patient_group_id="patient-001",
                dataset_id="dataset-a",
                label="POSITIVE",
            ),
        ]
    )
    result = build_nested_splits(cases, outer_folds=5, inner_folds=4)
    for fold in result["outer_folds"]:
        train, test = set(fold["train_case_ids"]), set(fold["test_case_ids"])
        related = {"case-001", "case-related-a", "case-related-b"}
        assert related <= train or related <= test


def test_conflicting_patient_labels_are_rejected():
    cases = _cases()
    cases.append(
        ProtectedTrainingCase(
            case_id="conflict",
            patient_group_id="patient-001",
            dataset_id="dataset",
            label="NEGATIVE",
        )
    )
    with pytest.raises(PipelineError, match="labels conflitantes"):
        build_nested_splits(cases)


def test_validation_rejects_external_leakage():
    result = build_nested_splits(_cases())
    broken = copy.deepcopy(result)
    leaked = broken["outer_folds"][0]["test_case_ids"][0]
    broken["outer_folds"][0]["train_case_ids"].append(leaked)
    with pytest.raises(PipelineError, match="Vazamento"):
        validate_nested_splits(broken)
