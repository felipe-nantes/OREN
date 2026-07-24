from __future__ import annotations

import pytest

from dtwin.learning.robustness import (
    _metrics_for,
    bootstrap_confidence_interval,
    leave_one_dataset_out,
    subgroup_metrics,
)
from dtwin.learning.schemas import ProtectedTrainingCase


def _case(case_id, label, dataset_id, patient_group_id=None, negative_subtype=None,
          positive_subtype=None, phenotype_tags=()):
    return ProtectedTrainingCase(
        case_id=case_id,
        patient_group_id=patient_group_id or case_id,
        dataset_id=dataset_id,
        label=label,
        negative_subtype=negative_subtype,
        positive_subtype=positive_subtype,
        phenotype_tags=tuple(phenotype_tags),
    )


def _row(case_id, prediction, technical_failure=False, score=None):
    return {
        "case_id": case_id,
        "prediction": prediction,
        "technical_failure": technical_failure,
        "score": score,
    }


def test_leave_one_dataset_out_splits_metrics_by_dataset():
    protected = {
        "a1": _case("a1", "POSITIVE", "ds_a"),
        "a2": _case("a2", "NEGATIVE", "ds_a"),
        "b1": _case("b1", "POSITIVE", "ds_b"),
        "b2": _case("b2", "POSITIVE", "ds_b"),
    }
    rows = [
        _row("a1", "POSITIVE"),
        _row("a2", "NEGATIVE"),
        _row("b1", "POSITIVE"),
        _row("b2", "NEGATIVE"),  # wrong: false negative in ds_b
    ]
    lodo = leave_one_dataset_out(rows, protected)
    assert set(lodo) == {"ds_a", "ds_b"}
    assert lodo["ds_a"]["sensitivity"] == 1.0
    assert lodo["ds_a"]["specificity"] == 1.0
    assert lodo["ds_b"]["sensitivity"] == 0.5  # 1 tp, 1 fn


def test_bootstrap_resamples_by_patient_group_not_by_case():
    # Two cases share the same patient_group_id; the group must move together
    # in every resample (never split across it).
    protected = {
        "c1": _case("c1", "POSITIVE", "ds_a", patient_group_id="p1"),
        "c2": _case("c2", "POSITIVE", "ds_a", patient_group_id="p1"),
        "c3": _case("c3", "NEGATIVE", "ds_a", patient_group_id="p2"),
        "c4": _case("c4", "NEGATIVE", "ds_a", patient_group_id="p3"),
    }
    rows = [_row("c1", "POSITIVE"), _row("c2", "POSITIVE"), _row("c3", "NEGATIVE"), _row("c4", "NEGATIVE")]
    result = bootstrap_confidence_interval(rows, protected, n_resamples=200, seed=42)
    assert result["patient_group_count"] == 3
    lo, hi = result["sensitivity_bootstrap_ci95"]
    assert 0.0 <= lo <= hi <= 1.0
    lo2, hi2 = result["specificity_bootstrap_ci95"]
    assert 0.0 <= lo2 <= hi2 <= 1.0


def test_bootstrap_is_deterministic_given_same_seed():
    protected = {
        "c1": _case("c1", "POSITIVE", "ds_a"),
        "c2": _case("c2", "NEGATIVE", "ds_a"),
        "c3": _case("c3", "POSITIVE", "ds_a"),
        "c4": _case("c4", "NEGATIVE", "ds_a"),
    }
    rows = [_row("c1", "POSITIVE"), _row("c2", "NEGATIVE"), _row("c3", "NEGATIVE"), _row("c4", "POSITIVE")]
    first = bootstrap_confidence_interval(rows, protected, n_resamples=300, seed=7)
    second = bootstrap_confidence_interval(rows, protected, n_resamples=300, seed=7)
    assert first == second


def test_subgroup_metrics_reports_honest_coverage_when_subtypes_missing():
    protected = {
        "c1": _case("c1", "NEGATIVE", "ds_a"),  # no negative_subtype populated
        "c2": _case("c2", "POSITIVE", "ds_a"),  # no positive_subtype populated
    }
    rows = [_row("c1", "NEGATIVE"), _row("c2", "POSITIVE")]
    result = subgroup_metrics(rows, protected)
    assert result["by_negative_subtype"] == {}
    assert result["by_positive_subtype"] == {}
    assert result["coverage"]["negative_subtype_coverage_fraction"] == 0.0
    assert result["coverage"]["positive_subtype_coverage_fraction"] == 0.0


def test_subgroup_metrics_breaks_down_by_declared_subtype_and_tag():
    protected = {
        "c1": _case("c1", "NEGATIVE", "ds_a", negative_subtype="benign_anatomic_variant",
                    phenotype_tags=["vascular_structure"]),
        "c2": _case("c2", "NEGATIVE", "ds_a", negative_subtype="benign_anatomic_variant"),
        "c3": _case("c3", "POSITIVE", "ds_a", positive_subtype="hcc_suspicious"),
    }
    rows = [
        _row("c1", "POSITIVE"),  # false positive on a known mimicker
        _row("c2", "NEGATIVE"),
        _row("c3", "POSITIVE"),
    ]
    result = subgroup_metrics(rows, protected)
    assert result["by_negative_subtype"]["benign_anatomic_variant"]["case_count"] == 2
    assert result["by_negative_subtype"]["benign_anatomic_variant"]["specificity"] == 0.5
    assert result["by_positive_subtype"]["hcc_suspicious"]["sensitivity"] == 1.0
    assert result["by_phenotype_tag"]["vascular_structure"]["case_count"] == 1
    assert result["coverage"]["negative_subtype_coverage_fraction"] == 1.0


def test_metrics_for_counts_technical_failure_as_error():
    protected = {"p": _case("p", "POSITIVE", "ds_a"), "n": _case("n", "NEGATIVE", "ds_a")}
    rows = [_row("p", "TECHNICAL_FAILURE", technical_failure=True), _row("n", "NEGATIVE")]
    result = _metrics_for(rows, protected)
    assert result["fn"] == 1
    assert result["technical_failures"] == 1
