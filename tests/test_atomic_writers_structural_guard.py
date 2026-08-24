"""Guarda estrutural dos writers atômicos (REF-01/W-003, SW-ATOMIC-01).

A PHASE_04 mapeou dezenas de helpers "atomic" por AST; a PHASE_08 e a REF-01
uniformizaram o comportamento (destino preservado sob interrupção; temporário
limpo em falha). Este teste torna essa auditoria um INVARIANTE permanente:
toda função com "atomic" no nome que escreve arquivo deve (a) limpar o
temporário em try/finally OU (b) delegar a um helper canônico. Um writer novo
divergente quebra a suíte (e a CI) no dia em que nascer.

Se este teste falhar: NÃO enfraqueça a regra — corrija o writer novo com o
padrão canônico (`dtwin.learning.protocol.atomic_write_json` é a referência).
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASES = ("dtwin", "webapp", "tools")

# "atomic" como token proprio — exclui falsos positivos como "anatomically".
NOME_ATOMICO = re.compile(r"(?<![a-z])atomic", re.IGNORECASE)

CANONICOS = (
    "atomic_write_json(",       # dtwin.learning.protocol (SW-ATOMIC-01)
    "_atomic_text(",            # dtwin.benchmark.reporting
    "_atomic_npy(",             # dtwin.learning.medsiglip_embeddings
    "_write_json_atomic(",      # dtwin.volumetry
    "_write_text_atomic(",      # delegacao local em pares texto/json
    "_atomic_json(",            # delegacao local consolidada
)
ESCRITA = (
    "replace(", "os.replace", "write_text", "write_bytes", "dump(",
    "save(", "WriteImage", "np.save", "tofile",
)


def _funcoes_atomicas():
    for base in BASES:
        for caminho in (ROOT / base).rglob("*.py"):
            try:
                arvore = ast.parse(caminho.read_text(encoding="utf-8"))
            except (SyntaxError, OSError):
                continue
            for no in ast.walk(arvore):
                if isinstance(no, ast.FunctionDef) and NOME_ATOMICO.search(no.name):
                    yield caminho.relative_to(ROOT), no


def _cleanup_em_finally(no: ast.FunctionDef) -> bool:
    for n in ast.walk(no):
        if isinstance(n, ast.Try) and n.finalbody:
            corpo_finally = "".join(ast.unparse(x) for x in n.finalbody)
            if any(tok in corpo_finally for tok in ("unlink", "remove", "rmtree")):
                return True
    return False


def test_todo_writer_atomico_limpa_tmp_ou_delega():
    violacoes = []
    total = 0
    for rel, no in _funcoes_atomicas():
        corpo = ast.unparse(no)
        escreve = any(tok in corpo for tok in ESCRITA)
        if not escreve:
            continue
        total += 1
        delega = any(tok in corpo for tok in CANONICOS)
        if not (_cleanup_em_finally(no) or delega):
            violacoes.append(f"{rel}:{no.lineno} {no.name}")
    assert total >= 40, f"varredura encontrou só {total} writers — o scanner quebrou?"
    assert violacoes == [], (
        "Writers 'atomic' sem try/finally-cleanup nem delegação ao canônico "
        f"(corrija com o padrão de dtwin.learning.protocol.atomic_write_json): {violacoes}"
    )


def test_canonico_do_contrato_existe_e_e_seguro():
    # SW-ATOMIC-01: o canônico nomeado pelo contrato precisa existir e manter
    # o padrão (mkstemp + fsync + replace + finally-unlink).
    fonte = (ROOT / "dtwin" / "learning" / "protocol.py").read_text(encoding="utf-8")
    arvore = ast.parse(fonte)
    funcao = next(
        no for no in ast.walk(arvore)
        if isinstance(no, ast.FunctionDef) and no.name == "atomic_write_json"
    )
    corpo = ast.unparse(funcao)
    assert "mkstemp" in corpo and "fsync" in corpo and "replace" in corpo
    assert _cleanup_em_finally(funcao)
