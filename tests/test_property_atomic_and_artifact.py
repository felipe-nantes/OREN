"""Property + audit tests — SW-ATOMIC-01 e SW-ARTIFACT-01 (PHASE_04_INVARIANTS).

`SW-ATOMIC-01`: "publicação JSON/CSV/NPY/artefato declarada atômica não pode
expor parcial como sucesso."

`SW-ARTIFACT-01`: "artefato consumido deve corresponder a hash/config/model/
preprocessing/protocol aplicáveis; parcial/corrompido deve ser recusado."

O invariante de SW-ATOMIC-01 é sobre o DESTINO, não sobre o temporário: uma
escrita interrompida pode deixar lixo temporário (higiene), mas nunca pode
deixar o destino com conteúdo parcial. Estes testes fixam exatamente isso, no
ponto de interrupção realista — entre escrever o temporário e renomear.

Auditoria de 2026-08-18 (TASK-2026-08-18-PH04-INV-03): 56 helpers atômicos
mapeados em `dtwin/`; os canônicos citados pelo contrato foram verificados
empiricamente. Divergência documentada em TD-007: `reporting._atomic_text`
não tem `try/finally` e vaza o temporário quando interrompido — o destino
permanece íntegro, então o contrato vale, mas a semântica diverge dos demais.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from dtwin.benchmark.reporting import _atomic_text
from dtwin.core import PipelineError, sha256_of
from dtwin.learning.medsiglip_embeddings import _atomic_npy
from dtwin.learning.protocol import atomic_write_json
from dtwin.volumetry import _write_json_atomic

ROOT = Path(__file__).resolve().parents[1]

_json_payload = st.dictionaries(
    keys=st.text(min_size=1, max_size=12),
    values=st.one_of(
        st.integers(min_value=-10**6, max_value=10**6),
        st.floats(allow_nan=False, allow_infinity=False, width=32),
        st.text(max_size=40),
        st.booleans(),
    ),
    max_size=8,
)


# --------------------------------------------------------------------------- #
# SW-ATOMIC-01
# --------------------------------------------------------------------------- #
@settings(max_examples=100, deadline=None)
@given(payload=_json_payload)
def test_property_escrita_atomica_produz_json_sempre_completo(payload, tmp_path_factory):
    """SW-ATOMIC-01 (caminho feliz): para qualquer payload, o artefato
    publicado é sempre JSON íntegro e reparseável -- nunca truncado."""
    destino = tmp_path_factory.mktemp("atomico") / "artefato.json"
    atomic_write_json(destino, payload)
    assert json.loads(destino.read_text(encoding="utf-8")) == payload


@pytest.mark.parametrize(
    "nome, escritor, alvo_do_rename",
    [
        ("protocol.atomic_write_json", atomic_write_json, "os.replace"),
        ("volumetry._write_json_atomic", _write_json_atomic, "os.replace"),
        (
            "reporting._atomic_text",
            lambda p, v: _atomic_text(p, json.dumps(v)),
            "pathlib.Path.replace",
        ),
    ],
)
def test_interrupcao_no_rename_nunca_expoe_destino_parcial(
    nome, escritor, alvo_do_rename, tmp_path
):
    """SW-ATOMIC-01, o invariante central: interrompido entre escrever o
    temporário e renomear, o destino mantém EXATAMENTE a versão anterior.
    Nunca conteúdo parcial, nunca a versão nova pela metade."""
    destino = tmp_path / f"{nome.replace('.', '_')}.json"
    escritor(destino, {"versao": "aprovada"})
    conteudo_anterior = destino.read_text(encoding="utf-8")

    with patch(alvo_do_rename, side_effect=RuntimeError("interrompido")):
        with pytest.raises(RuntimeError):
            escritor(destino, {"versao": "nova_incompleta"})

    assert destino.read_text(encoding="utf-8") == conteudo_anterior, (
        f"{nome} expôs conteúdo parcial/novo após interrupção -- viola SW-ATOMIC-01"
    )


@pytest.mark.parametrize(
    "nome, escritor, alvo_do_rename",
    [
        ("protocol.atomic_write_json", atomic_write_json, "os.replace"),
        ("volumetry._write_json_atomic", _write_json_atomic, "os.replace"),
        (
            "reporting._atomic_text",
            lambda p, v: _atomic_text(p, json.dumps(v)),
            "pathlib.Path.replace",
        ),
    ],
)
def test_interrupcao_sem_versao_anterior_nao_cria_destino_parcial(
    nome, escritor, alvo_do_rename, tmp_path
):
    """SW-ATOMIC-01, primeira publicação: se a primeira escrita é interrompida,
    o destino simplesmente não passa a existir -- um consumidor nunca encontra
    um artefato pela metade onde antes não havia nada."""
    destino = tmp_path / f"{nome.replace('.', '_')}_novo.json"

    with patch(alvo_do_rename, side_effect=RuntimeError("interrompido")):
        with pytest.raises(RuntimeError):
            escritor(destino, {"versao": "nunca_publicada"})

    assert not destino.exists(), (
        f"{nome} criou o destino apesar da interrupção -- viola SW-ATOMIC-01"
    )


def test_escrita_atomica_de_npy_tambem_e_completa_ou_ausente(tmp_path):
    """SW-ATOMIC-01 cobre NPY explicitamente (embeddings)."""
    destino = tmp_path / "vetor.npy"
    vetor = np.arange(12, dtype=np.float32)
    _atomic_npy(destino, vetor)
    np.testing.assert_array_equal(np.load(destino), vetor)

    with patch("os.replace", side_effect=RuntimeError("interrompido")):
        with pytest.raises(RuntimeError):
            _atomic_npy(destino, np.zeros(12, dtype=np.float32))

    np.testing.assert_array_equal(np.load(destino), vetor)


def _helpers_atomicos() -> dict[str, list[str]]:
    """Mapeia módulo -> nomes de funções cujo nome declara atomicidade."""
    encontrados: dict[str, list[str]] = {}
    for arquivo in sorted((ROOT / "dtwin").rglob("*.py")):
        if "__pycache__" in arquivo.parts:
            continue
        try:
            arvore = ast.parse(arquivo.read_text(encoding="utf-8", errors="ignore"))
        except SyntaxError:  # pragma: no cover - defensivo
            continue
        for no in ast.walk(arvore):
            if isinstance(no, ast.FunctionDef) and "atomic" in no.name.lower():
                encontrados.setdefault(
                    arquivo.relative_to(ROOT).as_posix(), []
                ).append(no.name)
    return encontrados


def test_auditoria_todo_helper_atomico_usa_temporario_mais_rename():
    """SW-ATOMIC-01, metade estrutural: uma função que se declara atômica no
    nome tem de publicar via temporário + rename. Escrever direto no destino
    é justamente o modo de falha que o contrato proíbe -- um helper novo com
    o nome "atomic" que escreva direto falha aqui."""
    helpers = _helpers_atomicos()
    assert helpers, "auditoria não encontrou helpers atômicos -- varredura quebrada"

    sem_rename: list[str] = []
    for modulo, funcoes in helpers.items():
        fonte = (ROOT / modulo).read_text(encoding="utf-8", errors="ignore")
        arvore = ast.parse(fonte)
        for no in ast.walk(arvore):
            if not (isinstance(no, ast.FunctionDef) and no.name in funcoes):
                continue
            # Publicação atômica pode aparecer de três formas legítimas:
            #  - método/atributo: os.replace(...), temporary.replace(...)
            #  - shutil.move(...)
            #  - delegação a um helper nomeado, ex.
            #    _replace_checkpoint_file(temporary, path) em
            #    lld_mmri_v23_preparation.py, que é MAIS robusto que a média
            #    (fsync + validação + backup) mas não expõe `.replace` no corpo.
            publica_atomicamente = False
            for interno in ast.walk(no):
                if isinstance(interno, ast.Attribute) and interno.attr in {
                    "replace",
                    "rename",
                    "move",
                }:
                    publica_atomicamente = True
                if isinstance(interno, ast.Call) and isinstance(interno.func, ast.Name):
                    nome_chamado = interno.func.id.lower()
                    if any(t in nome_chamado for t in ("replace", "rename", "atomic")):
                        publica_atomicamente = True
            if not publica_atomicamente:
                sem_rename.append(f"{modulo}::{no.name}")

    assert not sem_rename, (
        "helper(s) com 'atomic' no nome que não publicam via rename/replace "
        f"(SW-ATOMIC-01): {sorted(sem_rename)}"
    )


# --------------------------------------------------------------------------- #
# SW-ARTIFACT-01
# --------------------------------------------------------------------------- #
@settings(max_examples=60, deadline=None)
@given(
    conteudo=st.binary(min_size=8, max_size=256),
    posicao=st.integers(min_value=0),
)
def test_property_qualquer_adulteracao_de_byte_muda_o_hash(
    conteudo, posicao, tmp_path_factory
):
    """SW-ARTIFACT-01: a verificação por hash tem de detectar adulteração em
    QUALQUER posição -- não só no início ou no fim do artefato."""
    destino = tmp_path_factory.mktemp("artefato") / "dado.bin"
    destino.write_bytes(conteudo)
    hash_original = sha256_of(destino)

    indice = posicao % len(conteudo)
    adulterado = bytearray(conteudo)
    adulterado[indice] = (adulterado[indice] + 1) % 256
    destino.write_bytes(bytes(adulterado))

    assert sha256_of(destino) != hash_original, (
        f"adulteração no byte {indice} não mudou o hash -- verificação cega"
    )


def test_artefato_de_volumetria_incompleto_e_recusado(tmp_path):
    """SW-ARTIFACT-01: par JSON+CSV incompleto (um dos dois ausente) é
    recusado explicitamente, não consumido pela metade."""
    from dtwin.volumetry import verify_volumetry_artifacts

    with pytest.raises(PipelineError, match="incompletos"):
        verify_volumetry_artifacts(tmp_path)

    (tmp_path / "volumetry_manifest.json").write_text("{}", encoding="utf-8")
    with pytest.raises(PipelineError, match="incompletos"):
        verify_volumetry_artifacts(tmp_path)


def test_artefato_de_volumetria_com_json_corrompido_e_recusado(tmp_path):
    """SW-ARTIFACT-01: manifesto corrompido falha fechado com erro do domínio
    (PipelineError), não com JSONDecodeError cru vazando para o chamador."""
    from dtwin.volumetry import verify_volumetry_artifacts

    (tmp_path / "volumetry_manifest.json").write_text("{nao é json", encoding="utf-8")
    (tmp_path / "volumetry_summary.csv").write_text("role\nliver\n", encoding="utf-8")

    with pytest.raises(PipelineError, match="invalido|inválido"):
        verify_volumetry_artifacts(tmp_path)
