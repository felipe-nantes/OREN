"""Spec de proveniência do estimando (SR-006 → HG-07/08, HUMAN_DECISOES item 19).

A métrica de SELEÇÃO do bundle (`cross_validated_selection_metrics`, otimista:
~79/80 sobre 451 computáveis) NUNCA pode ser exposta por uma superfície de
apresentação como estimativa de generalização — a única âncora apresentável é
a nested-OOF honesta (75,91/76,11 sobre 467 com falhas no denominador,
SCI-004). Estes testes CONGELAM o enquadramento honesto já vigente em
``webapp.server._visual_model_info``; se algum deles quebrar, uma superfície
passou a promover a métrica errada — pare e consulte HG-08.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from webapp import server

ROOT = Path(__file__).resolve().parents[1]
BUNDLE_REAL = (
    ROOT / "casos" / "qualification" / "hybrid_v1"
    / "medsiglip_multiclass_production_bundle_v1" / "bundle_manifest.json"
)

CHAVES_DE_METRICA_PROIBIDAS = {
    "cross_validated_selection_metrics",
    "sensitivity", "specificity", "balanced_accuracy",
    "tp", "tn", "fp", "fn",
}


def _manifesto_sintetico() -> dict:
    """Espelha o bundle real, INCLUINDO os campos otimistas que não podem vazar."""
    return {
        "schema": "argos-medsiglip-production-bundle-v1",
        "candidate_id": "sintetico_gov01",
        "bundle_signature": "deadbeef" * 8,
        "decision_threshold": 0.4748,
        "cross_validated_selection_metrics": {
            "sensitivity": 0.7907, "specificity": 0.8008,
            "balanced_accuracy": 0.7958, "tp": 170, "tn": 189,
            "fp": 47, "fn": 45, "technical_failures": 0,
        },
        "generalization_estimate_source": "nested_oof_etapa_c",
        "in_sample_performance_is_not_a_generalization_estimate": True,
        "training_case_set_sha256": "cafe" * 16,
        "gate_75_75_stable_by_dataset": False,
        "research_only": True,
        "clinical_use_allowed": False,
    }


@pytest.fixture()
def bundle_sintetico(monkeypatch, tmp_path):
    (tmp_path / "bundle_manifest.json").write_text(
        json.dumps(_manifesto_sintetico()), encoding="utf-8"
    )
    monkeypatch.setattr(server, "_visual_bundle_root", lambda _cenario: tmp_path)
    return tmp_path


def test_model_info_nunca_expoe_metrica_de_selecao(bundle_sintetico):
    info = server._visual_model_info("qualquer")
    assert "cross_validated_selection_metrics" not in info
    # nenhum valor otimista pode vazar por outra chave
    serializado = json.dumps(info, ensure_ascii=False)
    for vazamento in ("0.7907", "0.8008", "0.7958", "79,07", "80,08"):
        assert vazamento not in serializado, f"métrica de seleção vazou: {vazamento}"


def test_model_info_carrega_a_ancora_honesta(bundle_sintetico):
    info = server._visual_model_info("qualquer")
    assert info["generalization_estimate_source"] == "nested_oof_etapa_c"
    assert "75,91" in info["oof_reference"] and "76,11" in info["oof_reference"]
    assert info["research_only"] is True
    assert info["clinical_use_allowed"] is False


def test_model_info_nao_carrega_nenhuma_chave_de_metrica(bundle_sintetico):
    # A identidade do modelo nao e um relatorio de desempenho: alem da string
    # oof_reference (ancora com proveniencia), nenhuma chave de metrica entra.
    info = server._visual_model_info("qualquer")
    assert CHAVES_DE_METRICA_PROIBIDAS.isdisjoint(info.keys())


def test_fallback_sem_manifesto_tambem_nao_expoe_metricas(monkeypatch, tmp_path):
    monkeypatch.setattr(server, "_visual_bundle_root", lambda _c: tmp_path)  # sem manifesto
    info = server._visual_model_info("qualquer")
    assert CHAVES_DE_METRICA_PROIBIDAS.isdisjoint(info.keys())
    assert "cross_validated_selection_metrics" not in json.dumps(info)


@pytest.mark.skipif(not BUNDLE_REAL.is_file(), reason="bundle congelado ausente desta máquina")
def test_bundle_real_carrega_as_guardas_de_proveniencia():
    manifesto = json.loads(BUNDLE_REAL.read_text(encoding="utf-8"))
    assert manifesto["generalization_estimate_source"] == "nested_oof_etapa_c"
    assert manifesto["in_sample_performance_is_not_a_generalization_estimate"] is True
    assert manifesto["training_case_set_sha256"]
    assert manifesto["research_only"] is True and manifesto["clinical_use_allowed"] is False
