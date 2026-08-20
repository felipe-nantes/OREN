import hashlib
import json
import time
from pathlib import Path

import pytest

from dtwin.benchmark.openswisshcc_inference import infer_reviewed_candidate
from dtwin.benchmark.openswisshcc_review import create_panel_review
from dtwin.core import PipelineError
from dtwin.medgemma_client import load_screening_config

CONFIG = Path("configs/medgemma_local_4b_multiphase_fast_pathology.yaml")


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class FakeClient:
    def __init__(self, delay: float = 0.0):
        self.delay = delay
        self.last_timings = {"medgemma_inference": delay}

    def generate(self, panel_path: Path, prompt: str):
        assert panel_path.is_file()
        assert "lesão focal" in prompt.lower()
        time.sleep(self.delay)
        return {
            "resultado_hipotese": "NEGATIVA",
            "resumo_do_achado": "Classificação rápida sem narrativa clínica gerada pelo modelo.",
            "localizacao_aproximada": "Não determinada no modo de classificação rápida.",
            "sinais_visuais_observados": ["Sem evidência focal suficiente no painel."],
            "confianca": "moderada",
            "limitacoes_da_analise": ["Revisão humana obrigatória."],
            "necessidade_de_revisao_humana": True,
            "alvo_da_triagem": "lesao_focal_hepatica_suspeita",
            "ha_lesao_focal_suspeita": False,
            "ha_variante_anatomica_benigna": False,
            "ha_pseudolesao_ou_artefato": False,
            "tipo_alteracao_nao_alvo": "none",
            "justificativa_da_separacao": "Sem evidência focal suficiente no painel.",
        }


def _approved_candidate(tmp_path: Path) -> tuple[Path, Path, str]:
    panels = tmp_path / "panels"
    case_id = "anon-inference-test"
    case = panels / case_id
    case.mkdir(parents=True)
    panel = case / "panel.png"
    panel.write_bytes(b"reviewed-panel")
    panel_hash = _sha(panel)
    panel_manifest = {
        "case_id": case_id,
        "panel_sha256": panel_hash,
        "input_volume_sha256": "a" * 64,
        "input_liver_mask_sha256": "b" * 64,
        "lesion_pre_marked": False,
    }
    (case / "panel_manifest.json").write_text(json.dumps(panel_manifest), encoding="utf-8")
    candidate = {
        "case_id": case_id,
        "candidate_signature": "candidate-signature",
        "candidate_version": "openswisshcc-multiphase-fast-pathology-v1",
        "panel_filename": panel.name,
        "panel_manifest_filename": "panel_manifest.json",
        "panel_sha256": panel_hash,
        "panel_bytes": panel.stat().st_size,
        "config_sha256": _sha(CONFIG),
        "research_only": True,
        "clinical_use_allowed": False,
    }
    (case / "candidate_manifest.json").write_text(json.dumps(candidate), encoding="utf-8")
    review = tmp_path / "approved.json"
    create_panel_review(
        panel_root=panels,
        case_ids=[case_id],
        output_path=review,
        reviewer="human-reviewer",
        confirmations={
            "no_visible_phi": True,
            "multiphase_alignment_acceptable": True,
            "liver_framing_acceptable": True,
        },
    )
    return panels, review, case_id


def test_inference_writes_normal_report_without_ground_truth(tmp_path):
    panels, review, case_id = _approved_candidate(tmp_path)
    output = tmp_path / "inference"
    result = infer_reviewed_candidate(
        case_id=case_id,
        panel_root=panels,
        review_path=review,
        output_root=output,
        config_path=CONFIG,
        client=FakeClient(),
    )
    assert result["prediction"] == "NEGATIVA"
    assert result["within_time_limit"] is True
    assert result["ground_truth_read"] is False
    report = json.loads((output / case_id / "medgemma_report.json").read_text(encoding="utf-8"))
    assert report["report"]["resultado_hipotese"] == "NEGATIVA"
    assert report["qualification"]["ground_truth_read"] is False
    assert report["model_id"] == "google/medgemma-1.5-4b-it"


def test_inference_rejects_config_not_bound_to_candidate(tmp_path):
    panels, review, case_id = _approved_candidate(tmp_path)
    with pytest.raises(PipelineError, match="Configuração não corresponde"):
        infer_reviewed_candidate(
            case_id=case_id,
            panel_root=panels,
            review_path=review,
            output_root=tmp_path / "out",
            config_path=Path("configs/medgemma_local_4b_venous_fallback_pathology.yaml"),
            client=FakeClient(),
        )


def test_inference_fails_closed_when_time_limit_is_exceeded(tmp_path):
    panels, review, case_id = _approved_candidate(tmp_path)
    output = tmp_path / "out"
    with pytest.raises(PipelineError, match="excedeu o teto"):
        infer_reviewed_candidate(
            case_id=case_id,
            panel_root=panels,
            review_path=review,
            output_root=output,
            config_path=CONFIG,
            max_case_seconds=0.01,
            client=FakeClient(delay=0.02),
        )
    assert not (output / case_id / "medgemma_report.json").exists()
    assert not list(output.glob(f".{case_id}.staging.*"))


def test_inference_rejects_unapproved_case(tmp_path):
    panels, review, _ = _approved_candidate(tmp_path)
    with pytest.raises(PipelineError, match="aprovação visual"):
        infer_reviewed_candidate(
            case_id="anon-other",
            panel_root=panels,
            review_path=review,
            output_root=tmp_path / "out",
            config_path=CONFIG,
            client=FakeClient(),
        )


def test_production_configs_are_prefilled_without_retries():
    for path in (
        CONFIG,
        Path("configs/medgemma_local_4b_venous_fallback_pathology.yaml"),
    ):
        config = load_screening_config(path)
        assert config["medgemma"]["response_mode"] == "prefilled_label"
        assert config["medgemma"]["max_retries"] == 0
        assert config["medgemma"]["response_validation_max_retries"] == 0
        assert config["medgemma"]["timeout_seconds"] == 120
