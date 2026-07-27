"""Pre-registration for the retrospective multicohort evaluation of ARGOS v23.

This module deliberately does not run inference or read labels.  It freezes the
claim, cohort roles, compatibility rules and failure accounting that must be
honoured by the later executors and evaluators.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from dtwin.benchmark.openswisshcc_v20_fusion import _canonical_sha
from dtwin.benchmark.openswisshcc_v23_baseline import verify_v23_baseline_lock
from dtwin.core import PipelineError


CONTRACT_SCHEMA = "argos-v23-retrospective-multicohort-contract-v1"
READINESS_SCHEMA = "argos-v23-retrospective-multicohort-readiness-v1"
CLAIM = "Desempenho retrospectivo multicohort nas bases disponíveis ao projeto."


def _load_object(path: Path, description: str) -> dict[str, Any]:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PipelineError(f"{description} ausente ou inválido.") from exc
    if not isinstance(value, dict):
        raise PipelineError(f"{description} deve ser um objeto JSON.")
    return value


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with Path(path).open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
    except OSError as exc:
        raise PipelineError(f"Artefato ausente: {path}.") from exc
    return digest.hexdigest()


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _contract_body(*, baseline: dict[str, Any], baseline_lock_sha256: str) -> dict[str, Any]:
    return {
        "schema": CONTRACT_SCHEMA,
        "status": "frozen_before_retrospective_multicohort_reanalysis",
        "claim": {
            "allowed": CLAIM,
            "external_blind_validation_claim_allowed": False,
            "prospective_validation_claim_allowed": False,
            "clinical_qualification_claim_allowed": False,
        },
        "target_condition": "focal_liver_lesion_suspicion",
        "algorithm": {
            "name": "argos_v23_shape_fusion",
            "family_fixed": True,
            "v11_weight": 0.80,
            "candidate_weighted_linearity_weight": 0.20,
            "frozen_calibrator_signature": baseline["calibrator_signature"],
            "frozen_deployment_threshold": baseline["decision_threshold"],
            "baseline_lock_sha256": baseline_lock_sha256,
            "medgemma_model": "medgemma_1_5_4b",
            "rag_in_frozen_v23": False,
            "pathology_target_in_frozen_v23": False,
            "liver_enriched_in_frozen_v23": False,
        },
        "estimands": {
            "primary": {
                "name": "openswisshcc_patient_level_out_of_fold_v23_family",
                "cohort_id": "openswisshcc",
                "fixed_weights": True,
                "ecdf_and_threshold_fit_on_training_only": True,
                "held_out_case_never_used_for_its_transform_or_threshold": True,
                "predictions_out_of_fold_only": True,
            },
            "secondary_frozen_calibrator": {
                "name": "frozen_v23_deployment_score",
                "calibrator_must_remain_unchanged": True,
                "only_exactly_compatible_multiphase_cases_allowed": True,
                "not_a_substitute_for_primary_out_of_fold_metrics": True,
            },
        },
        "cohorts": [
            {
                "cohort_id": "openswisshcc",
                "role": "primary_mixed_retrospective",
                "expected_cases": 132,
                "expected_positive": 63,
                "expected_negative": 69,
                "exact_v23_compatibility": "required",
                "combined_sensitivity_specificity_allowed": True,
                "prior_project_exposure": True,
            },
            {
                "cohort_id": "lld_mmri",
                "role": "secondary_sensitivity_stress",
                "expected_cases": 335,
                "expected_technically_processable": 321,
                "expected_preexisting_technical_failures": 14,
                "exact_v23_compatibility": "must_be_proven_before_scoring",
                "combined_sensitivity_specificity_allowed": False,
                "prior_project_exposure": True,
            },
            {
                "cohort_id": "liverhccseg",
                "role": "secondary_small_positive_sensitivity",
                "expected_cases": 14,
                "exact_v23_compatibility": "must_be_proven_before_scoring",
                "combined_sensitivity_specificity_allowed": False,
                "prior_project_exposure": True,
            },
            {
                "cohort_id": "chaos_mri",
                "role": "secondary_visual_specificity_robustness",
                "expected_cases": 20,
                "exact_v23_compatibility": "incompatible_missing_dynamic_phases",
                "combined_sensitivity_specificity_allowed": False,
                "v23_qualification_metric_allowed": False,
                "prior_project_exposure": True,
            },
            {
                "cohort_id": "local_cases",
                "role": "exploratory_only_pending_human_curation",
                "exact_v23_compatibility": "case_by_case_preflight_required",
                "combined_sensitivity_specificity_allowed": False,
                "v23_qualification_metric_allowed": False,
                "prior_project_exposure": True,
            },
        ],
        "primary_gate": {
            "minimum_sensitivity": 0.75,
            "minimum_specificity": 0.75,
            "maximum_raw_dicom_end_to_end_seconds_per_case": 180.0,
            "inconclusive_counts_as_error": True,
            "technical_failure_counts_as_error": True,
            "noncomputable_v23_counts_as_error": True,
            "timeouts_count_as_error": True,
            "wilson_95_percent_intervals_required": True,
            "confusion_matrix_required": True,
            "roc_auc_secondary_only": True,
            "best_fold_or_best_split_cannot_qualify": True,
            "all_cases_fixed_before_scoring": True,
        },
        "secondary_reporting": {
            "results_must_be_reported_per_cohort": True,
            "cross_dataset_pooled_metric_is_descriptive_only": True,
            "cross_dataset_pooled_metric_cannot_qualify": True,
            "positive_only_and_negative_only_sources_cannot_form_a_primary_metric": True,
            "worst_cohort_result_required": True,
        },
        "anti_gaming": {
            "no_case_removal_after_protocol_freeze": True,
            "no_threshold_change_after_result_observation": True,
            "no_relabeling_from_model_output": True,
            "no_lesion_mask_in_inference": True,
            "no_ground_truth_in_inference": True,
            "missing_phase_cannot_be_fabricated": True,
            "failed_experiments_must_be_retained": True,
            "all_candidates_must_be_predeclared": True,
        },
        "future_candidate_policy": {
            "v24_development_allowed_only_after_v23_result_is_frozen": True,
            "candidate_order": [
                "v23_frozen",
                "v23_plus_liver_enriched",
                "v23_plus_liver_enriched_plus_pathology_target",
                "v23_plus_liver_enriched_plus_pathology_target_plus_text_rag",
                "nested_recalibration_of_predeclared_signals",
            ],
            "selection_objective": "maximize_minimum_sensitivity_specificity",
            "tie_break_order": [
                "best_worst_cohort_result",
                "fewest_technical_failures",
                "lowest_maximum_time",
                "simplest_configuration",
                "least_dataset_specific_calibration",
            ],
        },
        "known_baseline_context": {
            "development_case_count": baseline["case_count"],
            "loocv_sensitivity": baseline["primary_loocv_metrics"]["sensitivity"],
            "loocv_specificity": baseline["primary_loocv_metrics"]["specificity"],
            "qualified": False,
        },
        "phase": 1,
        "inference_authorized": False,
        "metrics_authorized": False,
        "qualified": False,
        "research_only": True,
        "clinical_use_allowed": False,
    }


def freeze_retrospective_multicohort_contract(
    *,
    baseline_lock_path: Path,
    workspace_root: Path,
    output_path: Path,
) -> dict[str, Any]:
    """Freeze the phase-1 methodological contract without reading cohort data."""

    baseline_lock = Path(baseline_lock_path).resolve()
    baseline = verify_v23_baseline_lock(
        lock_path=baseline_lock,
        workspace_root=Path(workspace_root).resolve(),
    )
    body = _contract_body(
        baseline=baseline,
        baseline_lock_sha256=_sha256(baseline_lock),
    )
    contract = {**body, "contract_signature": _canonical_sha(body)}
    destination = Path(output_path).resolve()
    if destination.exists():
        existing = _load_object(destination, "Contrato multicohort existente")
        if existing != contract:
            raise PipelineError(
                "Contrato multicohort existente diverge; sobrescrita recusada."
            )
        return existing
    _write_json(destination, contract)
    return contract


def verify_retrospective_multicohort_contract(
    *,
    contract_path: Path,
    baseline_lock_path: Path,
    workspace_root: Path,
) -> dict[str, Any]:
    """Fail closed if the contract or frozen v23 baseline has changed."""

    contract = _load_object(Path(contract_path).resolve(), "Contrato multicohort")
    baseline_lock = Path(baseline_lock_path).resolve()
    baseline = verify_v23_baseline_lock(
        lock_path=baseline_lock,
        workspace_root=Path(workspace_root).resolve(),
    )
    expected_body = _contract_body(
        baseline=baseline,
        baseline_lock_sha256=_sha256(baseline_lock),
    )
    expected = {
        **expected_body,
        "contract_signature": _canonical_sha(expected_body),
    }
    if contract != expected:
        raise PipelineError("Contrato multicohort adulterado ou divergente.")
    return contract


def build_phase1_readiness(
    *,
    contract_path: Path,
    baseline_lock_path: Path,
    workspace_root: Path,
    output_path: Path,
) -> dict[str, Any]:
    """Record only source availability; never inspect labels or image contents."""

    workspace = Path(workspace_root).resolve()
    contract = verify_retrospective_multicohort_contract(
        contract_path=contract_path,
        baseline_lock_path=baseline_lock_path,
        workspace_root=workspace,
    )
    roots = {
        "openswisshcc": workspace / "casos/qualification/openswisshcc_v1",
        "lld_mmri": workspace / "casos/qualification/lld_mmri_v23",
        "liverhccseg": workspace / "data/raw/LiverHccSeg_v1.1",
        "chaos_mri": workspace / "data/raw/CHAOS_MRI_v1.03",
    }
    source_presence = {
        cohort_id: {
            "relative_root": root.relative_to(workspace).as_posix(),
            "root_present": root.is_dir(),
        }
        for cohort_id, root in roots.items()
    }
    blockers = [
        "bind_and_hash_the_132_case_openswisshcc_inventory",
        "freeze_patient_level_oof_split_and_nested_evaluation_protocol",
        "prove_exact_v23_signal_compatibility_for_lld_mmri",
        "prove_exact_v23_signal_compatibility_for_liverhccseg",
        "keep_chaos_out_of_exact_v23_qualification",
        "curate_local_case_labels_before_any_metric_use",
    ]
    body = {
        "schema": READINESS_SCHEMA,
        "status": "phase1_contract_frozen_inputs_not_bound",
        "contract_signature": contract["contract_signature"],
        "source_presence": source_presence,
        "inspection_scope": "directory_presence_only",
        "labels_read_by_readiness": False,
        "lesion_masks_read_by_readiness": False,
        "image_pixels_read_by_readiness": False,
        "blockers_before_inference": blockers,
        "ready_for_inference": False,
        "ready_for_metrics": False,
        "research_only": True,
        "clinical_use_allowed": False,
    }
    readiness = {**body, "readiness_signature": _canonical_sha(body)}
    destination = Path(output_path).resolve()
    if destination.exists():
        existing = _load_object(destination, "Readiness multicohort existente")
        if existing != readiness:
            raise PipelineError(
                "Readiness multicohort existente diverge; sobrescrita recusada."
            )
        return existing
    _write_json(destination, readiness)
    return readiness


__all__ = [
    "CLAIM",
    "CONTRACT_SCHEMA",
    "READINESS_SCHEMA",
    "build_phase1_readiness",
    "freeze_retrospective_multicohort_contract",
    "verify_retrospective_multicohort_contract",
]
