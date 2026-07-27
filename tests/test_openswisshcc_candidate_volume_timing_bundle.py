from __future__ import annotations

import pytest

from dtwin.benchmark.openswisshcc_candidate_volume_timing import SCENARIOS
from dtwin.benchmark.openswisshcc_candidate_volume_timing_bundle import _selected_timing_cases
from dtwin.core import PipelineError


def _plan():
    counts = {"fallback": 1, "one_candidate": 1, "three_candidates": 3, "five_candidates": 5}
    return {
        "selected_cases": [
            {
                "scenario": scenario,
                "case_id": f"anon-{index:016d}",
                "candidate_stack_count": counts[scenario],
                "fallback_no_candidate": scenario == "fallback",
                "alignment_available": True,
                "alignment_unavailable_reason": None,
            }
            for index, scenario in enumerate(SCENARIOS, 1)
        ]
    }


def test_timing_bundle_requires_exact_frozen_scenario_order_and_counts():
    selected = _selected_timing_cases(_plan())
    assert [item["scenario"] for item in selected] == list(SCENARIOS)
    assert [item["candidate_stack_count"] for item in selected] == [1, 1, 3, 5]


@pytest.mark.parametrize("mutation", ["order", "count", "alignment", "fallback"])
def test_timing_bundle_rejects_divergence_from_signed_plan(mutation):
    plan = _plan()
    if mutation == "order":
        plan["selected_cases"][0], plan["selected_cases"][1] = plan["selected_cases"][1], plan["selected_cases"][0]
    elif mutation == "count":
        plan["selected_cases"][2]["candidate_stack_count"] = 2
    elif mutation == "alignment":
        plan["selected_cases"][3]["alignment_available"] = False
    else:
        plan["selected_cases"][1]["fallback_no_candidate"] = True
    with pytest.raises(PipelineError):
        _selected_timing_cases(plan)
