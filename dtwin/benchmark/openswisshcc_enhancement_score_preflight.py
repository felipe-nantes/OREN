"""Fail-closed preflight for the v22 exact-top5 MedGemma 4B pilot.

The preflight validates semantics that the reusable v16 volume scorer does not
know about: deterministic enhancement provenance, exact top-five selection,
the retrospective development audit, and absence of holdout/ground-truth data
from the scoring bundle.  It performs no inference and reads no labels or
lesion-mask voxels.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from dtwin.benchmark.openswisshcc_alignment import _sha256
from dtwin.benchmark.openswisshcc_candidate_volume_score import (
    validate_candidate_volume_bundle,
)
from dtwin.benchmark.openswisshcc_enhancement_localizer_audit import AUDIT_SCHEMA
from dtwin.benchmark.openswisshcc_enhancement_proposal_selection import (
    ALGORITHM_VERSION,
    MAX_COMPONENTS,
)
from dtwin.benchmark.openswisshcc_lesion_localizer import CASE_SCHEMA, RUN_SCHEMA
from dtwin.core import PipelineError
from dtwin.medgemma_screening import _write_json_atomic


PREFLIGHT_SCHEMA = "argos-openswisshcc-enhancement-top5-score-preflight-v22"


def _load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PipelineError(f"JSON invalido no preflight v22: {path}.") from exc
    if not isinstance(value, dict):
        raise PipelineError(f"Objeto JSON esperado no preflight v22: {path}.")
    return value


def _refuse_holdout(*paths: Path) -> None:
    if any(
        any("holdout" in part.lower() for part in Path(path).resolve().parts)
        for path in paths
    ):
        raise PipelineError("Preflight v22 recusou caminho de holdout.")


def validate_enhancement_top5_bundle(
    *, bundle_root: Path, localizer_root: Path, audit_path: Path
) -> dict[str, Any]:
    """Validate exact-top5 visual inputs without opening labels or masks."""

    bundle_root = Path(bundle_root).resolve()
    localizer_root = Path(localizer_root).resolve()
    audit_path = Path(audit_path).resolve()
    _refuse_holdout(bundle_root, localizer_root, audit_path)
    bundle = validate_candidate_volume_bundle(bundle_root)
    cohort = bundle["cohort"]
    protocol = cohort.get("protocol", {})
    if (
        bundle["case_count"] != 10
        or protocol.get("candidate_target_fraction") != 1.0
        or protocol.get("minimum_base_candidates") != MAX_COMPONENTS
        or protocol.get("maximum_candidates") != MAX_COMPONENTS
        or cohort.get("ground_truth_read") is not False
        or cohort.get("dataset_lesion_mask_used") is not False
        or cohort.get("holdout_opened") is not False
        or cohort.get("inference_executed") is not False
    ):
        raise PipelineError("Bundle visual v22 nao representa exact-top5 cego.")

    summary_path = localizer_root / "summary.json"
    summary = _load(summary_path)
    if (
        summary.get("schema") != RUN_SCHEMA
        or summary.get("status") != "complete_scores_only_no_decision"
        or summary.get("algorithm_version") != ALGORITHM_VERSION
        or summary.get("ground_truth_read") is not False
        or summary.get("ground_truth_lesion_mask_used") is not False
        or summary.get("metrics_calculated") is not False
        or summary.get("final_decision") is not None
        or cohort.get("source_localizer_summary_sha256") != _sha256(summary_path)
        or not set(bundle["case_ids"]) <= set(summary.get("case_ids", []))
    ):
        raise PipelineError("Localizador deterministico v22 divergiu do bundle visual.")

    checked_cases: list[dict[str, Any]] = []
    for case in bundle["cases"]:
        case_id = case["case_id"]
        visual_manifest_path = bundle_root / case_id / "case_manifest.json"
        visual = _load(visual_manifest_path)
        selection = visual.get("selection", {})
        component_count = int(selection.get("component_count", -1))
        selected_count = int(selection.get("selected_component_count", -1))
        expected_selected = min(max(component_count, 0), MAX_COMPONENTS)
        expected_stacks = expected_selected if expected_selected else 1
        expected_ranks = list(range(1, expected_selected + 1))
        if (
            selection.get("rule") != "largest_until_minimum_and_target_fraction_with_maximum"
            or selection.get("target_fraction") != 1.0
            or selection.get("minimum_candidates") != MAX_COMPONENTS
            or selection.get("maximum_candidates") != MAX_COMPONENTS
            or selection.get("candidate_volume_coverage_fraction") != 1.0
            or selected_count != expected_selected
            or selection.get("selected_component_ranks") != expected_ranks
            or visual.get("candidate_stack_count") != expected_stacks
            or visual.get("gate", {}).get("candidate_coverage_passed") is not True
        ):
            raise PipelineError(f"Selecao exact-top5 invalida no caso {case_id}.")

        localizer_manifest_path = localizer_root / case_id / "localizer_manifest.json"
        localizer = _load(localizer_manifest_path)
        if (
            localizer.get("schema") != CASE_SCHEMA
            or localizer.get("case_id") != case_id
            or localizer.get("status") != "candidate_scores_only_no_decision"
            or localizer.get("algorithm_version") != ALGORITHM_VERSION
            or localizer.get("candidate_mask_is_model_derived") is not False
            or localizer.get("candidate_mask_is_deterministic_enhancement") is not True
            or localizer.get("ground_truth_read") is not False
            or localizer.get("ground_truth_lesion_mask_used") is not False
            or localizer.get("metrics_calculated") is not False
            or localizer.get("final_decision") is not None
            or visual.get("source_localizer_manifest_sha256")
            != _sha256(localizer_manifest_path)
        ):
            raise PipelineError(f"Proveniencia deterministica invalida no caso {case_id}.")
        checked_cases.append(
            {
                "case_id": case_id,
                "component_count": component_count,
                "selected_component_count": selected_count,
                "candidate_stack_count": expected_stacks,
                "visual_case_manifest_sha256": _sha256(visual_manifest_path),
                "localizer_manifest_sha256": _sha256(localizer_manifest_path),
            }
        )

    audit = _load(audit_path)
    if (
        audit.get("schema") != AUDIT_SCHEMA
        or audit.get("status") != "retrospective_development_audit_complete"
        or audit.get("development_only") is not True
        or audit.get("holdout_used") is not False
        or audit.get("inference_executed") is not False
        or audit.get("medgemma_called") is not False
        or audit.get("lesion_masks_used_for_inference") is not False
        or audit.get("lesion_masks_sent_to_medgemma") is not False
        or audit.get("qualified") is not False
    ):
        raise PipelineError("Auditoria retrospectiva v22 ausente ou insegura.")

    return {
        "bundle": bundle,
        "checked_cases": checked_cases,
        "source_hashes": {
            "bundle_cohort_sha256": bundle["cohort_sha256"],
            "gallery_signature": cohort["gallery_signature"],
            "localizer_summary_sha256": _sha256(summary_path),
            "retrospective_audit_sha256": _sha256(audit_path),
        },
    }


def write_enhancement_top5_preflight(
    *, bundle_root: Path, localizer_root: Path, audit_path: Path, output_path: Path
) -> dict[str, Any]:
    """Write an immutable evidence record; still does not authorize inference."""

    output_path = Path(output_path).resolve()
    _refuse_holdout(output_path)
    if output_path.exists():
        raise PipelineError("Preflight v22 ja existe; sobrescrita recusada.")
    validated = validate_enhancement_top5_bundle(
        bundle_root=bundle_root,
        localizer_root=localizer_root,
        audit_path=audit_path,
    )
    bundle = validated["bundle"]
    value: dict[str, Any] = {
        "schema": PREFLIGHT_SCHEMA,
        "status": "passed_pending_explicit_human_review",
        "algorithm_version": ALGORITHM_VERSION,
        "case_count": bundle["case_count"],
        "candidate_stack_count": bundle["candidate_stack_count"],
        "selection": {
            "threshold": "t3",
            "maximum_components": MAX_COMPONENTS,
            "coverage_of_selected_top5_components": 1.0,
        },
        "cases": validated["checked_cases"],
        "source_hashes": validated["source_hashes"],
        "human_review_signed": False,
        "inference_authorized": False,
        "inference_executed": False,
        "labels_read": False,
        "lesion_masks_read": False,
        "holdout_opened": False,
        "case_time_gate_seconds": 180.0,
        "research_only": True,
        "clinical_use_allowed": False,
        "requires_human_review": True,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    _write_json_atomic(output_path, value)
    return value


__all__ = [
    "PREFLIGHT_SCHEMA",
    "validate_enhancement_top5_bundle",
    "write_enhancement_top5_preflight",
]
