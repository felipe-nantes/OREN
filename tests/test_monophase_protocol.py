from __future__ import annotations

import pytest

from dtwin.core import PipelineError
from dtwin.learning.monophase_protocol import (
    build_hierarchical_screening_result,
    resolve_monophase_sequence_contract,
)


@pytest.mark.parametrize(
    ("sequence_class", "phase_key", "capability"),
    [
        ("T1_ARTERIAL", "t1_arterial", "arterial_appearance"),
        ("T1_PORTAL", "t1_venous", "portal_venous_appearance"),
        ("T1_DELAYED", "t1_delayed", "delayed_appearance"),
        ("T2", "t2", "t2_signal_appearance"),
        ("DWI", "dwi", "diffusion_weighted_signal_suspicion"),
        ("ADC", "adc", "adc_signal_suspicion"),
    ],
)
def test_sequence_contract_preserves_real_sequence_without_dynamic_claims(
    sequence_class, phase_key, capability
):
    contract = resolve_monophase_sequence_contract(
        {
            "sequence_class": sequence_class,
            "eligible_for_screening": True,
            "quality_score": 91,
            "warnings": [],
        }
    )

    assert contract["source_phase_key"] == phase_key
    assert capability in contract["supported_visual_capabilities"]
    assert contract["dynamic_enhancement_information_present"] is False
    assert contract["cross_phase_claims_allowed"] is False
    assert contract["washout_claim_allowed"] is False
    assert contract["synthetic_phases_created"] is False


def test_unknown_sequence_is_fail_closed_for_specific_medsiglip_bundle():
    contract = resolve_monophase_sequence_contract({"sequence_class": "UNKNOWN"})

    assert contract["sequence_recognized"] is False
    assert contract["source_phase_key"] == "unknown"
    assert contract["sequence_specific_medsiglip_bundle_allowed"] is False
    assert contract["supported_visual_capabilities"] == []


def test_explicitly_ineligible_series_cannot_use_specific_bundle():
    contract = resolve_monophase_sequence_contract(
        {"sequence_class": "T1_DELAYED", "eligible_for_screening": False}
    )
    assert contract["sequence_specific_medsiglip_bundle_allowed"] is False


def test_hierarchical_negative_can_report_named_benign_lesion():
    contract = resolve_monophase_sequence_contract({"sequence_class": "T1_DELAYED"})
    result = build_hierarchical_screening_result(
        prediction="NEGATIVE",
        subtype={"determined": True, "subtype": "fnh", "subtype_confidence": 0.86},
        sequence_contract=contract,
    )

    assert result["target_pathology_state"] == "NEGATIVE"
    assert result["focal_finding_state"] == "PRESENT"
    assert result["finding_nature"] == "named_benign_focal_finding"
    assert result["subtype"] == "fnh"
    assert result["model_outputs_consistent"] is True


def test_hierarchical_positive_hcc_is_consistent():
    contract = resolve_monophase_sequence_contract({"sequence_class": "T1_ARTERIAL"})
    result = build_hierarchical_screening_result(
        prediction="POSITIVE",
        subtype={"determined": True, "subtype": "hcc", "subtype_confidence": 0.79},
        sequence_contract=contract,
    )
    assert result["target_pathology_state"] == "POSITIVE"
    assert result["finding_nature"] == "suspicious_target_pathology"
    assert result["subtype"] == "hcc"


@pytest.mark.parametrize(
    ("prediction", "subtype"),
    [("NEGATIVE", "hcc"), ("POSITIVE", "hemangioma")],
)
def test_hierarchical_disagreement_never_invents_resolution(prediction, subtype):
    contract = resolve_monophase_sequence_contract({"sequence_class": "T1_DELAYED"})
    result = build_hierarchical_screening_result(
        prediction=prediction,
        subtype={"determined": True, "subtype": subtype, "subtype_confidence": 0.9},
        sequence_contract=contract,
    )
    assert result["target_pathology_state"] == "INCONCLUSIVE"
    assert result["subtype_determined"] is False
    assert result["subtype"] is None
    assert result["model_disagreement_requires_review"] is True


def test_hierarchical_contract_rejects_unknown_subtype():
    contract = resolve_monophase_sequence_contract({"sequence_class": "T1_DELAYED"})
    with pytest.raises(PipelineError, match="Subtipo monofásico não autorizado"):
        build_hierarchical_screening_result(
            prediction="POSITIVE",
            subtype={"determined": True, "subtype": "metastasis"},
            sequence_contract=contract,
        )
