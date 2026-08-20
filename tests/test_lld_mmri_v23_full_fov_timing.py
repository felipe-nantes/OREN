from __future__ import annotations

import json
from pathlib import Path

import pytest

from dtwin.benchmark.lld_mmri_v23_full_fov_review import create_full_fov_human_review
from dtwin.benchmark.lld_mmri_v23_full_fov_timing import (
    freeze_full_fov_timing_protocol,
    run_full_fov_timing_pilot,
    verify_full_fov_timing_protocol,
)
from dtwin.benchmark.openswisshcc_alignment import _sha256
from dtwin.core import PipelineError
from tests.test_lld_mmri_v23_full_fov_review import _sources

CONFIG = Path("configs/medgemma_local_4b_lld_v23_full_fov_no_mask_3x9_pilot.yaml")


def _report(state: str) -> dict:
    return {
        "resultado_hipotese": state,
        "resumo_do_achado": f"Classificacao {state}",
        "localizacao_aproximada": "Nao determinada.",
        "sinais_visuais_observados": ["Escolha restrita."],
        "confianca": "moderada",
        "limitacoes_da_analise": ["Pesquisa; revisao humana obrigatoria."],
        "necessidade_de_revisao_humana": True,
        "alvo_da_triagem": "lesao_focal_hepatica_suspeita",
        "ha_lesao_focal_suspeita": state == "POSITIVA",
        "ha_variante_anatomica_benigna": False,
        "ha_pseudolesao_ou_artefato": False,
        "tipo_alteracao_nao_alvo": "none",
        "justificativa_da_separacao": "Escolha restrita sem narrativa clinica.",
    }


class FakeClient:
    def __init__(self, states: list[str]):
        self.states = states
        self.calls: list[tuple[str, str]] = []
        self.last_response_audit = {}
        self.last_timings = {"client_total": 0.01}
        self.med = {"timeout_seconds": 120}

    def generate(self, panel_path: Path, prompt: str) -> dict:
        self.calls.append((Path(panel_path).name, prompt))
        return _report(self.states[len(self.calls) - 1])


def _frozen(tmp_path: Path):
    panels, gallery = _sources(tmp_path, config_sha256=_sha256(CONFIG))
    review = tmp_path / "review.json"
    create_full_fov_human_review(
        panel_root=panels,
        gallery_root=gallery,
        output_path=review,
        reviewer="jm",
        approved=True,
    )
    protocol = tmp_path / "protocol.json"
    frozen = freeze_full_fov_timing_protocol(
        panel_root=panels,
        gallery_root=gallery,
        review_path=review,
        config_path=CONFIG,
        output_path=protocol,
    )
    return panels, gallery, review, protocol, frozen


def test_timing_protocol_requires_signed_review(tmp_path: Path):
    panels, gallery = _sources(tmp_path, config_sha256=_sha256(CONFIG))
    with pytest.raises(PipelineError, match="Revisao full-FOV"):
        freeze_full_fov_timing_protocol(
            panel_root=panels,
            gallery_root=gallery,
            review_path=tmp_path / "missing.json",
            config_path=CONFIG,
            output_path=tmp_path / "protocol.json",
        )


def test_timing_protocol_roundtrip_and_tamper_detection(tmp_path: Path):
    panels, gallery, review, protocol, frozen = _frozen(tmp_path)
    verified, _cohort, _config = verify_full_fov_timing_protocol(
        panel_root=panels,
        gallery_root=gallery,
        review_path=review,
        config_path=CONFIG,
        protocol_path=protocol,
    )
    assert verified == frozen
    changed = json.loads(protocol.read_text(encoding="utf-8"))
    changed["maximum_seconds_per_case"] = 181.0
    protocol.write_text(json.dumps(changed), encoding="utf-8")
    with pytest.raises(PipelineError, match="invalido ou adulterado"):
        verify_full_fov_timing_protocol(
            panel_root=panels,
            gallery_root=gallery,
            review_path=review,
            config_path=CONFIG,
            protocol_path=protocol,
        )


def test_timing_runner_calls_three_panels_sequentially_and_aggregates(tmp_path: Path):
    panels, gallery, review, protocol, _frozen_protocol = _frozen(tmp_path)
    client = FakeClient(["NEGATIVA", "POSITIVA", "NEGATIVA"])
    output = tmp_path / "timing"
    summary = run_full_fov_timing_pilot(
        panel_root=panels,
        gallery_root=gallery,
        review_path=review,
        config_path=CONFIG,
        protocol_path=protocol,
        output_root=output,
        client=client,
    )
    assert [name for name, _prompt in client.calls] == ["panel_1.png", "panel_2.png", "panel_3.png"]
    assert all(f"painel {number}/3" in client.calls[number - 1][1] for number in range(1, 4))
    report = json.loads(
        (output / "anon-lld-review-test" / "medgemma_report.json").read_text(encoding="utf-8")
    )
    assert report["report"]["resultado_hipotese"] == "POSITIVA"
    assert len(report["panel_reports"]) == 3
    assert report["input_liver_mask_sha256"] is None
    assert report["organ_mask_used"] is False
    assert summary["case_count"] == 1
    assert summary["panel_image_count"] == 3
    assert summary["full_dicom_end_to_end_gate_claimed"] is False

    resumed_client = FakeClient([])
    resumed = run_full_fov_timing_pilot(
        panel_root=panels,
        gallery_root=gallery,
        review_path=review,
        config_path=CONFIG,
        protocol_path=protocol,
        output_root=output,
        client=resumed_client,
    )
    assert resumed == summary
    assert resumed_client.calls == []


def test_timing_runner_refuses_tampered_persisted_case(tmp_path: Path):
    panels, gallery, review, protocol, _frozen_protocol = _frozen(tmp_path)
    output = tmp_path / "timing"
    run_full_fov_timing_pilot(
        panel_root=panels,
        gallery_root=gallery,
        review_path=review,
        config_path=CONFIG,
        protocol_path=protocol,
        output_root=output,
        client=FakeClient(["NEGATIVA", "NEGATIVA", "NEGATIVA"]),
    )
    report = output / "anon-lld-review-test" / "medgemma_report.json"
    report.write_text("{}", encoding="utf-8")
    unused = FakeClient([])
    with pytest.raises(PipelineError, match="divergiu do protocolo"):
        run_full_fov_timing_pilot(
            panel_root=panels,
            gallery_root=gallery,
            review_path=review,
            config_path=CONFIG,
            protocol_path=protocol,
            output_root=output,
            client=unused,
        )
    assert unused.calls == []


def test_timing_protocol_refuses_non_180_limit(tmp_path: Path):
    panels, gallery = _sources(tmp_path, config_sha256=_sha256(CONFIG))
    with pytest.raises(PipelineError, match="180 segundos"):
        freeze_full_fov_timing_protocol(
            panel_root=panels,
            gallery_root=gallery,
            review_path=tmp_path / "unused.json",
            config_path=CONFIG,
            output_path=tmp_path / "protocol.json",
            maximum_seconds=181.0,
        )
