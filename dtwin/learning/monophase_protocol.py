"""Fail-closed contracts for single-phase liver MRI screening.

This module does not classify images.  It records which sequence was actually
selected, which visual claims that sequence can support, and converts an
already-frozen visual decision into a hierarchical research result.  Keeping
these concerns separate prevents an arterial, DWI or unknown series from being
silently interpreted by a delayed-phase head.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from dtwin.core import PipelineError

SEQUENCE_CONTRACT_SCHEMA = "oren-monophase-sequence-contract-v1"
HIERARCHICAL_RESULT_SCHEMA = "oren-hierarchical-liver-screening-v1"
SCREENING_TARGET = "hcc_suspicion"

_SEQUENCE_SPECS: dict[str, dict[str, Any]] = {
    "T1_ARTERIAL": {
        "source_phase_key": "t1_arterial",
        "family": "t1_dynamic",
        "capabilities": ["arterial_appearance", "arterial_hyperenhancement_suspicion"],
    },
    "T1_PORTAL": {
        "source_phase_key": "t1_venous",
        "family": "t1_dynamic",
        "capabilities": ["portal_venous_appearance"],
    },
    "T1_DELAYED": {
        "source_phase_key": "t1_delayed",
        "family": "t1_dynamic",
        "capabilities": ["delayed_appearance", "delayed_contrast_persistence_suspicion"],
    },
    "T1_POST_CONTRAST": {
        "source_phase_key": "t1_post_contrast_unknown_timing",
        "family": "t1_dynamic_unknown_timing",
        "capabilities": ["post_contrast_appearance"],
    },
    "T1_UNSPECIFIED": {
        "source_phase_key": "t1_unspecified",
        "family": "t1",
        "capabilities": ["t1_appearance"],
    },
    "T1_IN_PHASE": {
        "source_phase_key": "t1_in_phase",
        "family": "t1_chemical_shift",
        "capabilities": ["in_phase_appearance"],
    },
    "T1_OUT_PHASE": {
        "source_phase_key": "t1_out_phase",
        "family": "t1_chemical_shift",
        "capabilities": ["out_of_phase_appearance"],
    },
    "T2": {
        "source_phase_key": "t2",
        "family": "t2",
        "capabilities": ["t2_signal_appearance"],
    },
    "DWI": {
        "source_phase_key": "dwi",
        "family": "diffusion",
        "capabilities": ["diffusion_weighted_signal_suspicion"],
    },
    "ADC": {
        "source_phase_key": "adc",
        "family": "diffusion",
        "capabilities": ["adc_signal_suspicion"],
    },
}

_SEQUENCE_SPECIFIC_MEDSIGLIP_PHASES = {
    "t1_arterial",
    "t1_venous",
    "t1_delayed",
}
_BENIGN_SUBTYPES = {"fnh", "hemangioma", "hepatic_cyst"}


def resolve_monophase_sequence_contract(selected: Mapping[str, Any] | None) -> dict[str, Any]:
    """Return a sanitized capability contract for the selected real MR series."""

    selected = dict(selected or {})
    sequence_class = str(selected.get("sequence_class") or "UNKNOWN").strip().upper()
    spec = _SEQUENCE_SPECS.get(sequence_class)
    warnings = sorted({str(value) for value in (selected.get("warnings") or [])})
    quality_score = selected.get("quality_score")
    if quality_score is not None:
        try:
            quality_score = int(quality_score)
        except (TypeError, ValueError) as exc:
            raise PipelineError("quality_score monofásico inválido.") from exc
    eligible = selected.get("eligible_for_screening")
    if eligible is not None and not isinstance(eligible, bool):
        raise PipelineError("eligible_for_screening monofásico inválido.")

    recognized = spec is not None
    source_phase_key = str(spec["source_phase_key"]) if spec else "unknown"
    explicitly_ineligible = eligible is False
    return {
        "schema": SEQUENCE_CONTRACT_SCHEMA,
        "mode": "single_real_series",
        "selected_sequence_class": sequence_class,
        "source_phase_key": source_phase_key,
        "sequence_family": str(spec["family"]) if spec else "unknown",
        "sequence_recognized": recognized,
        "quality_score": quality_score,
        "eligible_for_screening": eligible,
        "warnings": warnings,
        "supported_visual_capabilities": list(spec["capabilities"]) if spec else [],
        "sequence_specific_medsiglip_bundle_allowed": (
            recognized
            and not explicitly_ineligible
            and source_phase_key in _SEQUENCE_SPECIFIC_MEDSIGLIP_PHASES
        ),
        "dynamic_enhancement_information_present": False,
        "cross_phase_claims_allowed": False,
        "washout_claim_allowed": False,
        "synthetic_phases_created": False,
        "requires_human_review": True,
        "research_only": True,
        "clinical_use_allowed": False,
    }


def build_hierarchical_screening_result(
    *,
    prediction: str,
    subtype: Mapping[str, Any] | None,
    sequence_contract: Mapping[str, Any],
) -> dict[str, Any]:
    """Separate target pathology, observed finding and subtype.

    The binary endpoint remains HCC suspicion.  A named benign lesion is still
    reported as an observed focal finding, but never changes a negative target
    decision into a positive one.  Any contradiction is exposed rather than
    resolved by guessing.
    """

    state = str(prediction).strip().upper()
    if state not in {"POSITIVE", "NEGATIVE", "INCONCLUSIVE"}:
        raise PipelineError(f"Predição hierárquica inválida: {prediction!r}")
    if sequence_contract.get("schema") != SEQUENCE_CONTRACT_SCHEMA:
        raise PipelineError("Contrato de sequência monofásica inválido.")

    subtype = dict(subtype or {})
    determined = bool(subtype.get("determined"))
    subtype_name = str(subtype.get("subtype") or "").strip() if determined else ""
    if determined and subtype_name not in (_BENIGN_SUBTYPES | {"hcc"}):
        raise PipelineError(f"Subtipo monofásico não autorizado: {subtype_name!r}")

    contradiction = (
        (state == "NEGATIVE" and subtype_name == "hcc")
        or (state == "POSITIVE" and subtype_name in _BENIGN_SUBTYPES)
    )
    if contradiction:
        target_state = "INCONCLUSIVE"
        subtype_reportable = False
        nature = "indeterminate_due_to_model_disagreement"
    else:
        target_state = state
        subtype_reportable = determined
        if subtype_name == "hcc":
            nature = "suspicious_target_pathology"
        elif subtype_name in _BENIGN_SUBTYPES:
            nature = "named_benign_focal_finding"
        elif state == "POSITIVE":
            nature = "unspecified_suspicious_target_pathology"
        elif state == "NEGATIVE":
            nature = "no_target_pathology_demonstrated"
        else:
            nature = "indeterminate"

    focal_state = (
        "PRESENT" if determined else "SUSPICIOUS" if state == "POSITIVE" else "NOT_DEMONSTRATED"
    )
    return {
        "schema": HIERARCHICAL_RESULT_SCHEMA,
        "target_condition": SCREENING_TARGET,
        "target_pathology_state": target_state,
        "focal_finding_state": focal_state,
        "finding_nature": nature,
        "subtype_determined": subtype_reportable,
        "subtype": subtype_name if subtype_reportable else None,
        "subtype_confidence": (
            subtype.get("subtype_confidence") if subtype_reportable else None
        ),
        "model_outputs_consistent": not contradiction,
        "model_disagreement_requires_review": contradiction,
        "source_phase_key": sequence_contract.get("source_phase_key"),
        "cross_phase_claims_made": False,
        "requires_human_review": True,
        "research_only": True,
        "clinical_use_allowed": False,
    }


__all__ = [
    "HIERARCHICAL_RESULT_SCHEMA",
    "SCREENING_TARGET",
    "SEQUENCE_CONTRACT_SCHEMA",
    "build_hierarchical_screening_result",
    "resolve_monophase_sequence_contract",
]
