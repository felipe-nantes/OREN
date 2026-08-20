from __future__ import annotations

import json
from pathlib import Path

import pytest

import dtwin.benchmark.v23_retrospective_multicohort as subject
from dtwin.core import PipelineError

BASELINE = {
    "calibrator_signature": "a" * 64,
    "decision_threshold": 0.5121839080459771,
    "case_count": 87,
    "primary_loocv_metrics": {
        "sensitivity": 0.8205128205128205,
        "specificity": 0.7916666666666666,
    },
}


def _setup(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    lock = tmp_path / "lock.json"
    lock.write_text('{"lock": true}\n', encoding="utf-8")
    contract = tmp_path / "contract.json"
    monkeypatch.setattr(
        subject,
        "verify_v23_baseline_lock",
        lambda **_: dict(BASELINE),
    )
    return lock, contract


def test_contract_freezes_claim_and_exact_v23(monkeypatch, tmp_path):
    lock, contract_path = _setup(tmp_path, monkeypatch)
    contract = subject.freeze_retrospective_multicohort_contract(
        baseline_lock_path=lock,
        workspace_root=tmp_path,
        output_path=contract_path,
    )
    assert contract["claim"]["allowed"] == subject.CLAIM
    assert contract["claim"]["external_blind_validation_claim_allowed"] is False
    assert contract["algorithm"]["v11_weight"] == 0.80
    assert contract["algorithm"]["candidate_weighted_linearity_weight"] == 0.20
    assert contract["algorithm"]["frozen_deployment_threshold"] == pytest.approx(
        0.5121839080459771
    )
    assert contract["inference_authorized"] is False


def test_primary_metric_cannot_be_built_from_single_class_sources(
    monkeypatch, tmp_path
):
    lock, contract_path = _setup(tmp_path, monkeypatch)
    contract = subject.freeze_retrospective_multicohort_contract(
        baseline_lock_path=lock,
        workspace_root=tmp_path,
        output_path=contract_path,
    )
    reporting = contract["secondary_reporting"]
    assert reporting["positive_only_and_negative_only_sources_cannot_form_a_primary_metric"]
    cohorts = {row["cohort_id"]: row for row in contract["cohorts"]}
    assert cohorts["lld_mmri"]["combined_sensitivity_specificity_allowed"] is False
    assert cohorts["chaos_mri"]["combined_sensitivity_specificity_allowed"] is False


def test_failure_and_noncomputable_cases_are_errors(monkeypatch, tmp_path):
    lock, contract_path = _setup(tmp_path, monkeypatch)
    contract = subject.freeze_retrospective_multicohort_contract(
        baseline_lock_path=lock,
        workspace_root=tmp_path,
        output_path=contract_path,
    )
    gate = contract["primary_gate"]
    assert gate["inconclusive_counts_as_error"] is True
    assert gate["technical_failure_counts_as_error"] is True
    assert gate["noncomputable_v23_counts_as_error"] is True
    assert gate["timeouts_count_as_error"] is True


def test_chaos_is_never_exact_v23_qualification(monkeypatch, tmp_path):
    lock, contract_path = _setup(tmp_path, monkeypatch)
    contract = subject.freeze_retrospective_multicohort_contract(
        baseline_lock_path=lock,
        workspace_root=tmp_path,
        output_path=contract_path,
    )
    chaos = next(row for row in contract["cohorts"] if row["cohort_id"] == "chaos_mri")
    assert chaos["exact_v23_compatibility"] == "incompatible_missing_dynamic_phases"
    assert chaos["v23_qualification_metric_allowed"] is False


def test_verify_rejects_tampering(monkeypatch, tmp_path):
    lock, contract_path = _setup(tmp_path, monkeypatch)
    subject.freeze_retrospective_multicohort_contract(
        baseline_lock_path=lock,
        workspace_root=tmp_path,
        output_path=contract_path,
    )
    value = json.loads(contract_path.read_text(encoding="utf-8"))
    value["primary_gate"]["minimum_specificity"] = 0.70
    contract_path.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(PipelineError, match="adulterado"):
        subject.verify_retrospective_multicohort_contract(
            contract_path=contract_path,
            baseline_lock_path=lock,
            workspace_root=tmp_path,
        )


def test_readiness_only_checks_directory_presence(monkeypatch, tmp_path):
    lock, contract_path = _setup(tmp_path, monkeypatch)
    subject.freeze_retrospective_multicohort_contract(
        baseline_lock_path=lock,
        workspace_root=tmp_path,
        output_path=contract_path,
    )
    (tmp_path / "data/raw/CHAOS_MRI_v1.03").mkdir(parents=True)
    readiness = subject.build_phase1_readiness(
        contract_path=contract_path,
        baseline_lock_path=lock,
        workspace_root=tmp_path,
        output_path=tmp_path / "readiness.json",
    )
    assert readiness["inspection_scope"] == "directory_presence_only"
    assert readiness["labels_read_by_readiness"] is False
    assert readiness["lesion_masks_read_by_readiness"] is False
    assert readiness["image_pixels_read_by_readiness"] is False
    assert readiness["source_presence"]["chaos_mri"]["root_present"] is True
    assert readiness["ready_for_inference"] is False


def test_existing_contract_is_idempotent_but_not_overwritten(monkeypatch, tmp_path):
    lock, contract_path = _setup(tmp_path, monkeypatch)
    first = subject.freeze_retrospective_multicohort_contract(
        baseline_lock_path=lock,
        workspace_root=tmp_path,
        output_path=contract_path,
    )
    second = subject.freeze_retrospective_multicohort_contract(
        baseline_lock_path=lock,
        workspace_root=tmp_path,
        output_path=contract_path,
    )
    assert first == second
    value = json.loads(contract_path.read_text(encoding="utf-8"))
    value["qualified"] = True
    contract_path.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(PipelineError, match="sobrescrita recusada"):
        subject.freeze_retrospective_multicohort_contract(
            baseline_lock_path=lock,
            workspace_root=tmp_path,
            output_path=contract_path,
        )
