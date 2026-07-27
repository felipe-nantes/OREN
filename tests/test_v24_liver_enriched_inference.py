from __future__ import annotations

import math

import pytest

from dtwin.benchmark import v24_liver_enriched_inference as subject
from dtwin.core import PipelineError


def test_choice_probabilities_are_strictly_validated():
    assert subject._validate_probabilities(
        {"POSITIVA": 0.6, "NEGATIVA": 0.3, "INCONCLUSIVA": 0.1}
    ) == {"POSITIVA": 0.6, "NEGATIVA": 0.3, "INCONCLUSIVA": 0.1}


@pytest.mark.parametrize(
    "value",
    [
        {"POSITIVA": 0.6, "NEGATIVA": 0.4},
        {"POSITIVA": 0.6, "NEGATIVA": 0.6, "INCONCLUSIVA": -0.2},
        {"POSITIVA": math.nan, "NEGATIVA": 0.5, "INCONCLUSIVA": 0.5},
        {"POSITIVA": 0.6, "NEGATIVA": 0.3, "INCONCLUSIVA": 0.2},
    ],
)
def test_choice_probabilities_reject_invalid_sets(value):
    with pytest.raises(PipelineError, match="Probabilidade|Probabilidades"):
        subject._validate_probabilities(value)


def test_protocol_cases_preserve_frozen_order_and_panel_hashes():
    cohort = {
        "cases": [
            {
                "case_id": "anon-a",
                "input_mode": "registered_multiphase_rgb",
                "selection_mode": "stable",
                "panel_count": 2,
                "manifest": "anon-a/manifest.json",
                "manifest_sha256": "a" * 64,
                "panels": [
                    {
                        "panel_number": 1,
                        "relative_path": "anon-a/p1.png",
                        "sha256": "b" * 64,
                    },
                    {
                        "panel_number": 2,
                        "relative_path": "anon-a/p2.png",
                        "sha256": "c" * 64,
                    },
                ],
            }
        ]
    }
    result = subject._protocol_cases(cohort)
    assert result[0]["case_id"] == "anon-a"
    assert result[0]["panels"][1]["sha256"] == "c" * 64
    result[0]["panels"][0]["sha256"] = "changed"
    assert cohort["cases"][0]["panels"][0]["sha256"] == "b" * 64


def test_v24_inference_contract_is_choice_signal_and_180_seconds():
    assert subject.SIGNAL_RULE == "maximum_panel_choice_probability_positiva_v1"
    assert (
        subject.AGGREGATION_RULE
        == "any_positive_else_any_inconclusive_else_all_negative"
    )
