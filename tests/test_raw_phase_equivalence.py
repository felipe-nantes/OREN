from dtwin.learning.raw_phase_equivalence import positive_arm_metrics, selection_key


def test_selection_key_is_order_sensitive_and_deterministic():
    assert selection_key(["a", "b", "c"]) == selection_key(["a", "b", "c"])
    assert selection_key(["a", "b", "c"]) != selection_key(["c", "b", "a"])


def test_positive_metrics_count_failures_as_false_negatives():
    metrics = positive_arm_metrics([
        {"status": "complete", "prediction": "POSITIVE", "automatic_total_seconds": 170, "panel_byte_equivalent": True},
        {"status": "complete", "prediction": "NEGATIVE", "automatic_total_seconds": 190, "panel_byte_equivalent": True},
        {"status": "technical_failure", "prediction": None, "automatic_total_seconds": 10, "panel_byte_equivalent": False},
    ])
    assert metrics["sensitivity"] == 1 / 3
    assert metrics["completion_rate"] == 2 / 3
    assert metrics["within_180_seconds_rate"] == 1 / 3
    assert metrics["specificity"] is None
    assert metrics["sensitivity_ci95_wilson"][0] < metrics["sensitivity"]
    assert metrics["sensitivity_ci95_wilson"][1] > metrics["sensitivity"]
    assert metrics["sensitivity_75_gate_passed"] is False
    assert metrics["all_cases_within_180_seconds"] is False
    assert metrics["simultaneous_75_75_gate_evaluable"] is False
