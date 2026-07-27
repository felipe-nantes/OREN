from __future__ import annotations

import json
from pathlib import Path

import pytest

from dtwin.benchmark.benign_mimic_adjudication import (
    SCHEMA,
    adjudicate_hcc_vs_benign_mimic,
)
from dtwin.core import PipelineError


def _write(path: Path, payload: dict) -> Path:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _envelope(*, decision: str, config: str, panel_set: str = "panels", v2: bool = False, confidence: str = "moderada", lesion: bool = False) -> dict:
    report = {
        "resultado_hipotese": decision,
        "confianca": confidence,
        "necessidade_de_revisao_humana": True,
    }
    if v2:
        report.update({
            "alvo_da_triagem": "lesao_focal_hepatica_suspeita",
            "ha_lesao_focal_suspeita": lesion,
            "ha_variante_anatomica_benigna": decision == "NEGATIVA",
            "ha_pseudolesao_ou_artefato": False,
            "tipo_alteracao_nao_alvo": "other" if decision == "NEGATIVA" else "none",
            "justificativa_da_separacao": "Evidência visual registrada na releitura.",
        })
    return {
        "case_id": "anon-case",
        "regulatory_mode": "RESEARCH",
        "requires_human_review": True,
        "lesion_pre_marked": False,
        "input_panel_set_sha256": panel_set,
        "screening_config_sha256": config,
        "report": report,
    }


def test_confident_second_negative_can_clear_initial_positive(tmp_path: Path):
    first = _write(tmp_path / "first.json", _envelope(decision="POSITIVA", config="a"))
    second = _write(tmp_path / "second.json", _envelope(decision="NEGATIVA", config="b", v2=True))
    result = adjudicate_hcc_vs_benign_mimic(
        first_pass_path=first, discriminator_path=second, output_path=tmp_path / "out.json"
    )
    assert result["schema"] == SCHEMA
    assert result["final_decision"] == "NEGATIVA"
    assert result["cleared_by_second_read"] is True
    assert len(result["adjudication_signature"]) == 64
    assert result["ground_truth_read"] is False
    assert result["lesion_masks_read"] == 0


def test_low_confidence_second_negative_becomes_inconclusive(tmp_path: Path):
    first = _write(tmp_path / "first.json", _envelope(decision="POSITIVA", config="a"))
    second = _write(tmp_path / "second.json", _envelope(decision="NEGATIVA", config="b", v2=True, confidence="baixa"))
    result = adjudicate_hcc_vs_benign_mimic(
        first_pass_path=first, discriminator_path=second, output_path=tmp_path / "out.json"
    )
    assert result["final_decision"] == "INCONCLUSIVA"


def test_second_reader_never_upgrades_initial_negative(tmp_path: Path):
    first = _write(tmp_path / "first.json", _envelope(decision="NEGATIVA", config="a"))
    second = _write(tmp_path / "second.json", _envelope(decision="POSITIVA", config="b", v2=True, lesion=True))
    result = adjudicate_hcc_vs_benign_mimic(
        first_pass_path=first, discriminator_path=second, output_path=tmp_path / "out.json"
    )
    assert result["final_decision"] == "NEGATIVA"
    assert result["aggregation_rule"] == "preserve_initial_negative"


@pytest.mark.parametrize("field,value", [("input_panel_set_sha256", "other"), ("screening_config_sha256", "a")])
def test_requires_same_panels_and_distinct_prompt(tmp_path: Path, field: str, value: str):
    first = _write(tmp_path / "first.json", _envelope(decision="POSITIVA", config="a"))
    second_payload = _envelope(decision="NEGATIVA", config="b", v2=True)
    second_payload[field] = value
    second = _write(tmp_path / "second.json", second_payload)
    with pytest.raises(PipelineError):
        adjudicate_hcc_vs_benign_mimic(
            first_pass_path=first, discriminator_path=second, output_path=tmp_path / "out.json"
        )


def test_rejects_discriminator_without_pathology_target_v2(tmp_path: Path):
    first = _write(tmp_path / "first.json", _envelope(decision="POSITIVA", config="a"))
    second = _write(tmp_path / "second.json", _envelope(decision="NEGATIVA", config="b"))
    with pytest.raises(PipelineError, match="pathology-target v2"):
        adjudicate_hcc_vs_benign_mimic(
            first_pass_path=first, discriminator_path=second, output_path=tmp_path / "out.json"
        )
