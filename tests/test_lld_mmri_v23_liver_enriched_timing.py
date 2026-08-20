from __future__ import annotations

import json
from pathlib import Path

import pytest

from dtwin.benchmark.lld_mmri_v23_liver_enriched_review import (
    create_liver_enriched_human_review,
)
from dtwin.benchmark.lld_mmri_v23_liver_enriched_timing import (
    freeze_liver_enriched_timing_protocol,
    run_liver_enriched_timing_pilot,
    verify_liver_enriched_timing_protocol,
    verify_liver_enriched_timing_run,
)
from dtwin.benchmark.openswisshcc_alignment import _sha256
from dtwin.core import PipelineError
from tests.test_lld_mmri_v23_liver_enriched_review import _sources

CONFIG = Path("configs/medgemma_local_4b_lld_v23_liver_enriched_pilot.yaml")


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
    def __init__(self, states: list[str], *, fail_at: int | None = None):
        self.states = states
        self.fail_at = fail_at
        self.calls: list[tuple[str, str]] = []
        self.last_response_audit = {}
        self.last_timings = {"client_total": 0.01}
        self.med = {"timeout_seconds": 120}

    def generate(self, panel_path: Path, prompt: str) -> dict:
        self.calls.append((Path(panel_path).name, prompt))
        if self.fail_at == len(self.calls):
            raise RuntimeError("falha simulada")
        return _report(self.states[len(self.calls) - 1])


def _reviewed(tmp_path: Path):
    panels, gallery = _sources(tmp_path, config_sha256=_sha256(CONFIG))
    review = tmp_path / "review.json"
    create_liver_enriched_human_review(
        panel_root=panels, gallery_root=gallery, output_path=review,
        reviewer="jm", approved=True,
    )
    return panels, gallery, review


def test_liver_enriched_protocol_requires_review(tmp_path: Path):
    panels, gallery = _sources(tmp_path, config_sha256=_sha256(CONFIG))
    with pytest.raises(PipelineError, match="Revisao liver-enriched"):
        freeze_liver_enriched_timing_protocol(
            panel_root=panels, gallery_root=gallery,
            review_path=tmp_path / "missing.json", config_path=CONFIG,
            output_path=tmp_path / "protocol.json",
        )


def test_liver_enriched_protocol_freezes_variable_panel_counts(tmp_path: Path):
    panels, gallery, review = _reviewed(tmp_path)
    protocol_path = tmp_path / "protocol.json"
    frozen = freeze_liver_enriched_timing_protocol(
        panel_root=panels, gallery_root=gallery, review_path=review,
        config_path=CONFIG, output_path=protocol_path,
    )
    verified, _cohort, _config = verify_liver_enriched_timing_protocol(
        panel_root=panels, gallery_root=gallery, review_path=review,
        config_path=CONFIG, protocol_path=protocol_path,
    )
    assert verified == frozen
    assert [case["panel_image_count"] for case in frozen["cases"]] == [3, 2]
    assert frozen["total_panel_image_count"] == 5
    assert frozen["maximum_seconds_per_case"] == 180.0
    assert frozen["full_dicom_end_to_end_gate_claimed"] is False


def test_liver_enriched_protocol_detects_panel_count_tamper(tmp_path: Path):
    panels, gallery, review = _reviewed(tmp_path)
    protocol_path = tmp_path / "protocol.json"
    freeze_liver_enriched_timing_protocol(
        panel_root=panels, gallery_root=gallery, review_path=review,
        config_path=CONFIG, output_path=protocol_path,
    )
    changed = json.loads(protocol_path.read_text(encoding="utf-8"))
    changed["cases"][1]["panel_image_count"] = 3
    protocol_path.write_text(json.dumps(changed), encoding="utf-8")
    with pytest.raises(PipelineError, match="invalido ou adulterado"):
        verify_liver_enriched_timing_protocol(
            panel_root=panels, gallery_root=gallery, review_path=review,
            config_path=CONFIG, protocol_path=protocol_path,
        )


def test_liver_enriched_protocol_refuses_non_180_limit(tmp_path: Path):
    panels, gallery, review = _reviewed(tmp_path)
    with pytest.raises(PipelineError, match="180 segundos"):
        freeze_liver_enriched_timing_protocol(
            panel_root=panels, gallery_root=gallery, review_path=review,
            config_path=CONFIG, output_path=tmp_path / "protocol.json",
            maximum_seconds=181.0,
        )


def _frozen(tmp_path: Path):
    panels, gallery, review = _reviewed(tmp_path)
    protocol = tmp_path / "protocol.json"
    frozen = freeze_liver_enriched_timing_protocol(
        panel_root=panels, gallery_root=gallery, review_path=review,
        config_path=CONFIG, output_path=protocol,
    )
    return panels, gallery, review, protocol, frozen


def test_runner_uses_three_and_two_panels_and_aggregates(tmp_path: Path):
    panels, gallery, review, protocol, _frozen_protocol = _frozen(tmp_path)
    client = FakeClient(["NEGATIVA", "POSITIVA", "NEGATIVA", "NEGATIVA", "NEGATIVA"])
    output = tmp_path / "timing"
    summary = run_liver_enriched_timing_pilot(
        panel_root=panels, gallery_root=gallery, review_path=review,
        config_path=CONFIG, protocol_path=protocol, output_root=output,
        client=client,
    )
    assert len(client.calls) == 5
    assert all(f"painel {number}/3" in client.calls[number - 1][1] for number in range(1, 4))
    assert "painel 1/2" in client.calls[3][1]
    assert "painel 2/2" in client.calls[4][1]
    stable = json.loads((output / "anon-stable" / "medgemma_report.json").read_text(encoding="utf-8"))
    fallback = json.loads((output / "anon-fallback" / "medgemma_report.json").read_text(encoding="utf-8"))
    assert stable["report"]["resultado_hipotese"] == "POSITIVA"
    assert fallback["report"]["resultado_hipotese"] == "NEGATIVA"
    assert len(stable["panel_reports"]) == 3
    assert len(fallback["panel_reports"]) == 2
    assert stable["organ_mask_sent_to_model"] is False
    assert summary["case_count"] == 2
    assert summary["panel_image_count"] == 5
    verified = verify_liver_enriched_timing_run(
        panel_root=panels, gallery_root=gallery, review_path=review,
        config_path=CONFIG, protocol_path=protocol, output_root=output,
    )
    assert verified["status"] == "verified_complete_label_blind"
    assert verified["prediction_counts"] == {"NEGATIVA": 1, "POSITIVA": 1}
    assert verified["panel_image_count"] == 5

    resumed_client = FakeClient([])
    resumed = run_liver_enriched_timing_pilot(
        panel_root=panels, gallery_root=gallery, review_path=review,
        config_path=CONFIG, protocol_path=protocol, output_root=output,
        client=resumed_client,
    )
    assert resumed == summary
    assert resumed_client.calls == []


def test_runner_refuses_tampered_persisted_report(tmp_path: Path):
    panels, gallery, review, protocol, _ = _frozen(tmp_path)
    output = tmp_path / "timing"
    run_liver_enriched_timing_pilot(
        panel_root=panels, gallery_root=gallery, review_path=review,
        config_path=CONFIG, protocol_path=protocol, output_root=output,
        client=FakeClient(["NEGATIVA"] * 5),
    )
    (output / "anon-stable" / "medgemma_report.json").write_text("{}", encoding="utf-8")
    unused = FakeClient([])
    with pytest.raises(PipelineError, match="divergiu"):
        run_liver_enriched_timing_pilot(
            panel_root=panels, gallery_root=gallery, review_path=review,
            config_path=CONFIG, protocol_path=protocol, output_root=output,
            client=unused,
        )
    assert unused.calls == []


def test_runner_intermediate_failure_has_no_final_report(tmp_path: Path):
    panels, gallery, review, protocol, _ = _frozen(tmp_path)
    output = tmp_path / "timing"
    with pytest.raises(RuntimeError, match="falha simulada"):
        run_liver_enriched_timing_pilot(
            panel_root=panels, gallery_root=gallery, review_path=review,
            config_path=CONFIG, protocol_path=protocol, output_root=output,
            client=FakeClient(["NEGATIVA"] * 5, fail_at=2),
        )
    failed = output / "anon-stable"
    assert (failed / "timing_failure.json").is_file()
    assert not (failed / "medgemma_report.json").exists()
