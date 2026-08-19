"""Invariant tests — SW-FAIL-CLOSED-01, SW-HTTP-01, SW-XR-01, POL-PHI-01
(PHASE_04_INVARIANTS, wave final).

- `SW-FAIL-CLOSED-01`: falha de input/modelo/artefato obrigatório não pode
  fabricar máscara, relatório ou resultado.
- `SW-HTTP-01`: MedGemma usa o contrato `dtwin-medgemma-v1`; respostas passam
  por schema; backend divergente é recusado.
- `SW-XR-01`: sessões XR são token-hasheadas, expiram e falham com 401 — sem
  vazamento de token em path/log.
- `POL-PHI-01`: dados de pacientes não entram no Git; diretórios sensíveis
  permanecem ignorados.

TASK-2026-08-18-PH04-INV-05.
"""

from __future__ import annotations

import json
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi import HTTPException
from hypothesis import given, settings
from hypothesis import strategies as st

from dtwin.core import PipelineError

ROOT = Path(__file__).resolve().parents[1]


# --------------------------------------------------------------------------- #
# SW-FAIL-CLOSED-01
# --------------------------------------------------------------------------- #
def test_leitura_de_imagem_inexistente_falha_com_erro_do_dominio(tmp_path):
    """SW-FAIL-CLOSED-01: input ausente vira PipelineError explícito — nunca
    uma imagem vazia fabricada, nunca exceção crua de I/O vazando."""
    from dtwin.core import read_image

    with pytest.raises(PipelineError, match="Falha ao ler imagem"):
        read_image(tmp_path / "nao_existe.nii.gz")


def test_serie_dicom_ausente_falha_com_erro_do_dominio(tmp_path):
    from dtwin.core import read_dicom_series

    with pytest.raises(PipelineError):
        read_dicom_series(tmp_path / "pasta_vazia_inexistente")


def test_finalize_sem_mascara_do_orgao_nao_fabrica_resultado(tmp_path):
    """SW-FAIL-CLOSED-01 no pipeline: finalize sem a máscara do prepare
    aborta pedindo o prepare — não inventa máscara nem malha."""
    from dtwin.core import Case
    from dtwin.stages import stage4b_import_lesion

    case = Case(root=tmp_path)
    with pytest.raises(PipelineError, match="rode 'prepare'"):
        stage4b_import_lesion(case, {}, no_lesion=True)


def test_bundle_de_producao_corrompido_e_recusado(tmp_path):
    """SW-FAIL-CLOSED-01 + SW-ARTIFACT-01: manifesto de bundle sem schema
    válido é recusado — o classificador nunca roda sobre bundle desconhecido."""
    from dtwin.learning.visual_inference import load_production_bundle

    (tmp_path / "bundle_manifest.json").write_text(
        json.dumps({"schema": "schema-desconhecido"}), encoding="utf-8"
    )
    with pytest.raises(PipelineError):
        load_production_bundle(tmp_path)


# --------------------------------------------------------------------------- #
# SW-HTTP-01
# --------------------------------------------------------------------------- #
def _cliente_gateway(monkeypatch, health_payload):
    """Constrói o adaptador HTTP real (HTTPJSONMedGemmaClient) com socket e
    health mockados — nenhuma rede é tocada."""
    import socket as socket_module
    from contextlib import contextmanager

    from dtwin import medgemma_client as mc

    config = {
        "medgemma": {
            "enabled": True,
            "provider": "http_json_v1",
            "model_id": "modelo/configurado",
            "model_version": "v1",
            "backend_configured": True,
            "model_available": True,
            "execution_mode": "local",
            "endpoint_url": "http://127.0.0.1:8001/generate",
            "healthcheck_url": "http://127.0.0.1:8001/health",
            "timeout_seconds": 5,
        }
    }

    @contextmanager
    def _conexao_falsa(*args, **kwargs):
        yield None

    class _RespostaFalsa:
        def __init__(self, payload):
            self._corpo = json.dumps(payload).encode("utf-8")

        def read(self):
            return self._corpo

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    monkeypatch.setattr(mc.socket, "create_connection", _conexao_falsa)
    monkeypatch.setattr(mc, "urlopen", lambda *a, **k: _RespostaFalsa(health_payload))
    return mc.HTTPJSONMedGemmaClient(config)


@pytest.mark.parametrize(
    "health, mensagem",
    [
        ({"status": "loading"}, "não está pronto"),
        (
            {
                "status": "ready",
                "model_id": "modelo/ERRADO",
                "model_version": "v1",
            },
            "exatamente o modelo",
        ),
        (
            {
                "status": "ready",
                "model_id": "modelo/configurado",
                "model_version": "v1",
                "contract": "outro-contrato-v9",
            },
            "contrato MedGemma incompatível",
        ),
    ],
)
def test_health_divergente_e_recusado(monkeypatch, health, mensagem):
    """SW-HTTP-01: backend não-pronto, modelo divergente ou contrato estranho
    são recusados ANTES de qualquer inferência."""
    cliente = _cliente_gateway(monkeypatch, health)
    with pytest.raises(PipelineError, match=mensagem):
        cliente.check_ready()


def test_health_com_contrato_correto_e_aceito(monkeypatch):
    cliente = _cliente_gateway(
        monkeypatch,
        {
            "status": "ready",
            "model_id": "modelo/configurado",
            "model_version": "v1",
            "contract": "dtwin-medgemma-v1",
        },
    )
    health = cliente.check_ready()
    assert health["status"] == "ready"


def test_endpoint_remoto_sem_opt_in_e_recusado(monkeypatch):
    """SW-HTTP-01 + política loopback: execution_mode=local com endpoint fora
    de loopback é recusado na configuração, antes de qualquer socket."""
    from dtwin import medgemma_client as mc

    config = {
        "medgemma": {
            "enabled": True,
            "provider": "http_json_v1",
            "model_id": "m",
            "model_version": "v1",
            "backend_configured": True,
            "model_available": True,
            "execution_mode": "local",
            "endpoint_url": "http://192.168.0.50:8001/generate",
            "timeout_seconds": 5,
        }
    }
    cliente = mc.HTTPJSONMedGemmaClient(config)
    with pytest.raises(PipelineError, match="loopback"):
        cliente.check_ready()


def test_payload_de_geracao_declara_o_contrato_v1():
    """SW-HTTP-01: toda requisição de geração carrega o contrato e a
    identidade do modelo — o servidor pode recusar clientes divergentes."""
    import inspect

    from dtwin import medgemma_client as mc

    fonte = inspect.getsource(mc.HTTPJSONMedGemmaClient._post_generate)
    assert '"contract": "dtwin-medgemma-v1"' in fonte
    assert '"model_id"' in fonte and '"model_version"' in fonte


# --------------------------------------------------------------------------- #
# SW-XR-01
# --------------------------------------------------------------------------- #
@settings(max_examples=80, deadline=None)
@given(token=st.text(min_size=1, max_size=64))
def test_property_nome_da_sessao_e_exatamente_o_sha256_do_token(token, tmp_path_factory):
    """SW-XR-01: o nome do arquivo de sessão é EXATAMENTE o SHA-256 do token
    — nada do token em claro, nada além do digest. (Comparar contra o hash
    esperado evita o falso positivo de substring: tokens de 1 caractere podem
    coincidir com um caractere do próprio hex.)"""
    import hashlib

    from webapp.server import _xr_session_path

    base = tmp_path_factory.mktemp("xr")
    caminho = _xr_session_path(base, token)

    digest_esperado = hashlib.sha256(token.encode("utf-8")).hexdigest()
    assert caminho.name == f"{digest_esperado}.json"
    assert set(caminho.stem) <= set("0123456789abcdef")


def test_sessao_xr_expirada_e_removida_e_recusada_com_401(tmp_path, monkeypatch):
    """SW-XR-01: sessão expirada devolve 401 e o arquivo é apagado — sessões
    são curtas por construção, não por convenção."""
    from webapp import server

    job_id = "ab9900000001"
    monkeypatch.setattr(server, "_case_dir_for_job", lambda _job: tmp_path)

    token = "token-de-teste"
    caminho = server._xr_session_path(tmp_path, token)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(
        json.dumps(
            {
                "job_id": job_id,
                "expires_at": (
                    datetime.now(timezone.utc) - timedelta(minutes=1)
                ).isoformat(),
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(HTTPException) as excecao:
        server._read_xr_session(job_id, token)
    assert excecao.value.status_code == 401
    assert not caminho.exists(), "sessão expirada deveria ter sido removida"


@pytest.mark.parametrize("token_invalido", ["", "x" * 257])
def test_token_vazio_ou_gigante_e_recusado_com_401(token_invalido, tmp_path, monkeypatch):
    from webapp import server

    monkeypatch.setattr(server, "_case_dir_for_job", lambda _job: tmp_path)
    with pytest.raises(HTTPException) as excecao:
        server._read_xr_session("ab9900000002", token_invalido)
    assert excecao.value.status_code == 401


def test_sessao_de_outro_job_e_recusada(tmp_path, monkeypatch):
    """SW-XR-01 (role/job scoping): a sessão vale para UM job; reutilizá-la
    noutro job falha com 401."""
    from webapp import server

    monkeypatch.setattr(server, "_case_dir_for_job", lambda _job: tmp_path)
    token = "token-scopo"
    caminho = server._xr_session_path(tmp_path, token)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(
        json.dumps(
            {
                "job_id": "ab9900000003",
                "expires_at": (
                    datetime.now(timezone.utc) + timedelta(minutes=10)
                ).isoformat(),
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(HTTPException) as excecao:
        server._read_xr_session("ab9900000004", token)  # job diferente
    assert excecao.value.status_code == 401


# --------------------------------------------------------------------------- #
# POL-PHI-01
# --------------------------------------------------------------------------- #
def test_diretorios_de_paciente_estao_ignorados_pelo_git():
    """POL-PHI-01: casos/, flywheel/ e as exportações locais ficam fora do
    Git. Usa o próprio git check-ignore como oráculo — é o mecanismo real."""
    sondas = [
        "casos/paciente_x/volume.nii.gz",
        "flywheel/figado/anon-000/mask.nii.gz",
        "docs/drive/qualquer_arquivo.pdf",
    ]
    resultado = subprocess.run(
        ["git", "check-ignore", *sondas],
        capture_output=True,
        text=True,
        cwd=str(ROOT),
    )
    ignorados = set(resultado.stdout.split())
    faltando = [s for s in sondas if s not in ignorados]
    assert not faltando, f"caminhos sensíveis NÃO ignorados pelo git: {faltando}"


def test_nenhum_arquivo_de_paciente_esta_versionado():
    """POL-PHI-01: além de ignorar o futuro, o índice atual não pode conter
    nada sob casos/ ou flywheel/."""
    resultado = subprocess.run(
        ["git", "ls-files", "casos/", "flywheel/"],
        capture_output=True,
        text=True,
        cwd=str(ROOT),
    )
    versionados = [linha for linha in resultado.stdout.splitlines() if linha.strip()]
    assert not versionados, f"arquivos sob diretórios de paciente versionados: {versionados[:5]}"
