from __future__ import annotations

import pytest

from dtwin.core import PipelineError
from dtwin.learning.monophase_protocol import resolve_monophase_sequence_contract
from dtwin.learning.monophase_subtype_adjudication import (
    aggregate_balanced_choice_reads,
    build_balanced_choice_prompts,
    fuse_subtype_adjudication,
    validated_top2,
)


PROBS = {"hcc": 0.45, "fnh": 0.35, "hemangioma": 0.15, "hepatic_cyst": 0.05}


def test_top2_requires_closed_normalized_four_class_space():
    assert [item["subtype"] for item in validated_top2(PROBS)] == ["hcc", "fnh"]
    with pytest.raises(PipelineError, match="quatro classes"):
        validated_top2({"hcc": 1.0})
    with pytest.raises(PipelineError, match="normalizadas"):
        validated_top2({**PROBS, "hcc": 0.5})


def test_prompts_reverse_order_and_forbid_cross_phase_claims():
    specs = build_balanced_choice_prompts(
        top2=validated_top2(PROBS), source_phase_key="t1_delayed",
        panel_number=1, panel_total=1, rag_context="FNH pode mimetizar HCC.",
    )
    assert specs[0]["choice_map"]["A"] == "hcc"
    assert specs[1]["choice_map"]["A"] == "fnh"
    assert "Não alegue washout" in specs[0]["prompt"]
    assert specs[0]["allowed_gateway_choices"] == ["A", "B", "C"]


def test_balanced_reads_map_letters_back_to_subtypes():
    specs = build_balanced_choice_prompts(
        top2=validated_top2(PROBS), source_phase_key="t1_delayed",
        panel_number=1, panel_total=1,
    )
    reads = [
        {"choices": ["A", "B", "C"], "choice_probabilities": {"A": 0.8, "B": 0.1, "C": 0.1}},
        {"choices": ["A", "B", "C"], "choice_probabilities": {"A": 0.1, "B": 0.8, "C": 0.1}},
    ]
    result = aggregate_balanced_choice_reads(prompt_specs=specs, reads=reads)
    assert result["determined"] is True
    assert result["subtype"] == "hcc"
    assert result["order_balanced"] is True


def test_inconclusive_or_small_margin_never_names_subtype():
    specs = build_balanced_choice_prompts(
        top2=validated_top2(PROBS), source_phase_key="t1_delayed",
        panel_number=1, panel_total=1,
    )
    reads = [
        {"choices": ["A", "B", "C"], "choice_probabilities": {"A": 0.35, "B": 0.25, "C": 0.40}},
        {"choices": ["A", "B", "C"], "choice_probabilities": {"A": 0.25, "B": 0.35, "C": 0.40}},
    ]
    result = aggregate_balanced_choice_reads(prompt_specs=specs, reads=reads)
    assert result["determined"] is False
    assert result["subtype"] is None


def test_fusion_never_promotes_benign_binary_and_exposes_disagreement():
    contract = resolve_monophase_sequence_contract({"sequence_class": "T1_DELAYED"})
    fused = fuse_subtype_adjudication(
        binary_prediction="NEGATIVE", class_probabilities=PROBS,
        medgemma_adjudication={"determined": True, "subtype": "hcc", "subtype_confidence": "alta"},
        sequence_contract=contract,
    )
    assert fused["binary_prediction_changed_by_subtype_reader"] is False
    assert fused["hierarchical_result"]["target_pathology_state"] == "INCONCLUSIVE"
    assert fused["requires_human_review"] is True


def test_fusion_rejects_choice_outside_frozen_top2():
    contract = resolve_monophase_sequence_contract({"sequence_class": "T1_DELAYED"})
    with pytest.raises(PipelineError, match="fora do diferencial"):
        fuse_subtype_adjudication(
            binary_prediction="NEGATIVE", class_probabilities=PROBS,
            medgemma_adjudication={"determined": True, "subtype": "hepatic_cyst", "subtype_confidence": "alta"},
            sequence_contract=contract,
        )
