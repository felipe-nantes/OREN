from __future__ import annotations

import pytest

from dtwin.benchmark.openswisshcc_v11_v13_complementarity import (
    compare_predictions,
)
from dtwin.core import PipelineError


def test_complementarity_and_oracle_are_counted_without_selecting_rule():
    result = compare_predictions(
        case_ids=["a", "b", "c", "d"],
        truth=[True, True, False, False],
        v11_predictions=[True, False, False, True],
        v13_predictions=["NEGATIVA", "POSITIVA", "NEGATIVA", "INCONCLUSIVA"],
    )
    assert result["pair_correctness"] == {
        "both_correct": 1,
        "only_v11_correct": 1,
        "only_v13_correct": 1,
        "both_wrong_or_v13_inconclusive": 1,
    }
    assert result["v11_errors_corrected_by_v13"]["total"] == 1
    assert result["v13_errors_corrected_by_v11"]["total"] == 1
    assert result["oracle_any_correct"]["sensitivity"] == 1.0
    assert result["oracle_any_correct"]["specificity"] == 0.5
    assert result["oracle_any_correct"]["not_a_model_metric"] is True
    assert result["rule_selected"] is False
    assert result["holdout_opened"] is False


def test_inconclusive_is_never_counted_as_correct():
    result = compare_predictions(
        case_ids=["a", "b"],
        truth=[True, False],
        v11_predictions=[False, True],
        v13_predictions=["INCONCLUSIVA", "INCONCLUSIVA"],
    )
    assert result["pair_correctness"]["both_wrong_or_v13_inconclusive"] == 2
    assert result["v11_errors_corrected_by_v13"]["total"] == 0


@pytest.mark.parametrize(
    "case_ids,truth,v11,v13",
    [
        ([], [], [], []),
        (["a", "a"], [True, False], [True, False], ["POSITIVA", "NEGATIVA"]),
        (["a"], [True], [True], ["INVALIDA"]),
    ],
)
def test_invalid_vectors_are_rejected(case_ids, truth, v11, v13):
    with pytest.raises(PipelineError):
        compare_predictions(
            case_ids=case_ids,
            truth=truth,
            v11_predictions=v11,
            v13_predictions=v13,
        )

