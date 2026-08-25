"""Guarda do índice de status dos configs (REF-06/W-046).

O índice `configs/CONFIG_STATUS_INDEX.yaml` é metadado consultivo EXTERNO —
nenhum config foi editado, porque há pinagem por sha256 no protocol lock e
assinaturas embutidas em artefatos congelados. Este teste torna o índice um
invariante: config novo sem entrada (ou entrada órfã) quebra a suíte, e a
pinagem do protocolo científico é re-verificada para sempre.

Se este teste falhar por config novo: adicione a entrada ao índice com o
status derivado pela regra documentada no próprio arquivo — não enfraqueça.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
INDEX_PATH = ROOT / "configs" / "CONFIG_STATUS_INDEX.yaml"
STATUS_VALIDOS = {"frozen_scientific", "production", "experimental", "legacy"}


def _index():
    return yaml.safe_load(INDEX_PATH.read_text(encoding="utf-8"))


def _configs_no_disco() -> set[str]:
    return {
        p.relative_to(ROOT).as_posix()
        for ext in ("yaml", "json")
        for p in (ROOT / "configs").rglob(f"*.{ext}")
        if p.name != INDEX_PATH.name
    }


def test_indice_cobre_exatamente_os_configs_do_disco():
    dados = _index()
    indexados = [e["path"] for e in dados["configs"]]
    assert len(indexados) == len(set(indexados)), "entradas duplicadas no índice"
    no_disco = _configs_no_disco()
    faltando = sorted(no_disco - set(indexados))
    orfaos = sorted(set(indexados) - no_disco)
    assert faltando == [], f"configs sem entrada no índice: {faltando}"
    assert orfaos == [], f"entradas do índice sem arquivo: {orfaos}"
    assert dados["resumo"]["total"] == len(no_disco)


def test_todo_status_pertence_ao_vocabulario():
    fora = [
        (e["path"], e["status"])
        for e in _index()["configs"]
        if e["status"] not in STATUS_VALIDOS
    ]
    assert fora == []


def test_protocolo_cientifico_permanece_congelado_e_pinado():
    # A pinagem central da auditoria, re-verificada para sempre: o sha256 de
    # hybrid_v1_protocol.yaml precisa continuar IGUAL ao config_sha256 do lock.
    lock = json.loads(
        (ROOT / "configs/training/hybrid_v1_protocol.lock.json").read_text(
            encoding="utf-8"
        )
    )
    sha = hashlib.sha256(
        (ROOT / "configs/training/hybrid_v1_protocol.yaml").read_bytes()
    ).hexdigest()
    assert sha == lock["config_sha256"], (
        "hybrid_v1_protocol.yaml divergiu do lock — mudança no protocolo "
        "congelado exige gate formal (HG), nunca edição direta."
    )
    por_path = {e["path"]: e for e in _index()["configs"]}
    for congelado in (
        "configs/training/hybrid_v1_protocol.yaml",
        "configs/training/hybrid_v1_protocol.lock.json",
        "configs/training/hybrid_v1_nested_splits.json",
        "configs/benchmark/v23_retrospective_multicohort_contract_v1.json",
    ):
        assert por_path[congelado]["status"] == "frozen_scientific", congelado
