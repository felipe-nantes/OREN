"""Guarda do índice de status dos tools (REF-06B/W-046).

`tools/TOOLS_STATUS_INDEX.yaml` é metadado consultivo (escada da PHASE_01
re-executada na árvore atual). Este teste garante que o índice acompanha o
diretório: tool novo sem entrada (ou entrada órfã) quebra a suíte. A
CLASSIFICAÇÃO em si não é re-verificada aqui (exigiria a varredura de
corpus na suíte); regenere com evidence/REF-06B/gerador_tools_index.py.

STATIC_ORPHAN não significa morto: remoção de tools exige prova de
reachability runtime + fase própria + autorização (LONG_PLAN item 10).
"""
from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
INDEX_PATH = ROOT / "tools" / "TOOLS_STATUS_INDEX.yaml"
STATUS_VALIDOS = {
    "RUNTIME_OR_LAUNCH_WIRED", "TEST_REFERENCED_ONLY", "TOOLCHAIN_ONLY",
    "DOC_REFERENCED_ONLY", "STATIC_ORPHAN",
}


def _index():
    return yaml.safe_load(INDEX_PATH.read_text(encoding="utf-8"))


def _tools_no_disco() -> set[str]:
    return {
        p.relative_to(ROOT).as_posix()
        for p in (ROOT / "tools").rglob("*")
        if p.is_file() and p.name != INDEX_PATH.name and "__pycache__" not in p.parts
    }


def test_indice_cobre_exatamente_os_tools_do_disco():
    dados = _index()
    indexados = [e["path"] for e in dados["tools"]]
    assert len(indexados) == len(set(indexados)), "entradas duplicadas"
    no_disco = _tools_no_disco()
    faltando = sorted(no_disco - set(indexados))
    orfaos = sorted(set(indexados) - no_disco)
    assert faltando == [], (
        "tools sem entrada no índice (regenere com "
        f"evidence/REF-06B/gerador_tools_index.py): {faltando}"
    )
    assert orfaos == [], f"entradas do índice sem arquivo: {orfaos}"
    assert dados["resumo"]["total"] == len(no_disco)


def test_todo_status_pertence_a_escada_da_ph01():
    fora = [
        (e["path"], e["status"])
        for e in _index()["tools"]
        if e["status"] not in STATUS_VALIDOS
    ]
    assert fora == []
