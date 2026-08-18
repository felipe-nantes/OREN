"""Runtime nativo (sem Docker) — substitui tests/test_docker_integration.py.

Migração TASK-2026-08-18-MIGR-01: o Docker deixa de ser o único caminho de
execução. Estes testes protegem, no runtime nativo, as mesmas propriedades
que os testes Docker-only garantiam sobre os artefatos de infraestrutura
agora removidos (compose.yaml, docker/, tools/*_docker_*).

Não cobre: distribuição portátil ARM64 (compose.portable.yaml e afins),
preservada fora do escopo desta migração — ver tests/test_portable_distribution.py.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from dtwin.core import PipelineError
from dtwin.graphrag.config import GraphRagConfig, Neo4jConnectionConfig
from webapp import server

ROOT = Path(__file__).resolve().parents[1]


def test_windows_launcher_has_preflight_health_gated_startup_and_scoped_shutdown():
    """run_win.ps1 é o launcher canônico: preflight, portas, retomada
    idempotente e shutdown restrito ao processo que ele próprio criou."""
    launcher = (ROOT / "run_win.ps1").read_text(encoding="utf-8")
    assert "Get-NetTCPConnection -LocalPort $GatewayPort" in launcher
    assert 'if ($h.status -eq "ready")' in launcher  # retomada idempotente
    assert "Stop-Process -Id $gateway.Id -Force" in launcher  # shutdown escopado
    assert 'ExpectedModel = "google/medgemma-1.5-4b-it"' in launcher


def test_windows_launcher_replicates_offline_defense_in_depth_without_docker():
    """HF_HUB_OFFLINE/TRANSFORMERS_OFFLINE eram globais no compose; o launcher
    nativo replica como reforço (o código já passa local_files_only=True)."""
    launcher = (ROOT / "run_win.ps1").read_text(encoding="utf-8")
    assert '$env:HF_HUB_OFFLINE = "1"' in launcher
    assert '$env:TRANSFORMERS_OFFLINE = "1"' in launcher


def test_windows_launcher_never_binds_beyond_loopback():
    launcher = (ROOT / "run_win.ps1").read_text(encoding="utf-8")
    assert "127.0.0.1:$GatewayPort" in launcher
    assert "127.0.0.1:$WebappPort" in launcher
    assert "0.0.0.0" not in launcher


def test_windows_launcher_reports_neo4j_as_optional_without_blocking_startup():
    """Neo4j é serviço nativo local opcional: ausência não impede o launcher
    de continuar para o gateway/webapp."""
    launcher = (ROOT / "run_win.ps1").read_text(encoding="utf-8")
    assert "bolt://localhost:7687" in launcher or "127.0.0.1\", 7687" in launcher
    assert "GraphRAG e opcional" in launcher


def test_mrsegmentator_resolves_native_windows_default_without_container():
    source = (ROOT / "webapp" / "server.py").read_text(encoding="utf-8")
    assert 'os.environ.get("WEBAPP_MRSEGMENTATOR_EXE"' in source
    assert '"Scripts/mrsegmentator.exe" if os.name == "nt" else "bin/mrsegmentator"' in source
    assert (ROOT / ".venv-mrseg").exists(), "venv nativo do MRSegmentator ausente"


def test_medgemma_backends_are_launcher_selected_per_os_not_container_profiles():
    """4B (Windows/CUDA) e 27B (Mac/Ollama) são escolhidos pelo launcher da
    máquina, não por profile do compose."""
    win = (ROOT / "run_win.ps1").read_text(encoding="utf-8")
    mac = (ROOT / "run_mac.sh").read_text(encoding="utf-8")
    assert "medgemma_local_4b.yaml" in win
    assert "medgemma" in mac.lower() and "ollama" in mac.lower()


def test_medgemma_server_binds_loopback_only_with_no_container_opt_in():
    """A exceção ARGOS_CONTAINER->0.0.0.0 do Docker foi removida: sem Docker,
    não existe opt-in para escutar fora de loopback."""
    source = (ROOT / "tools" / "medgemma_server_v14.py").read_text(encoding="utf-8")
    assert "ARGOS_CONTAINER" not in source
    assert 'allowed_hosts = {"127.0.0.1", "localhost", "::1"}' in source
    assert 'allowed_hosts.add("0.0.0.0")' not in source


def test_graphify_wrapper_is_isolated_native_venv_and_code_only():
    """Isolamento nativo do Graphify: venv própria + --code-only. NÃO é
    isolamento de rede kernel-level (network_mode: none do Docker não tem
    equivalente nativo) — risco residual aceito e documentado em
    .fable/MIGRATION_DOCKER_TO_NATIVE.md (PH-03)."""
    wrapper = (ROOT / "tools" / "graphify_argos.ps1").read_text(encoding="utf-8")
    assert r".local\graphify-venv" in wrapper
    assert "--code-only" in wrapper


def test_neo4j_native_config_uses_loopback_and_env_scoped_secret():
    config_text = (ROOT / "configs" / "graphrag_neo4j.yaml").read_text(encoding="utf-8")
    assert "bolt://localhost:7687" in config_text
    assert "password_env: NEO4J_PASSWORD" in config_text
    assert "bolt://neo4j:" not in config_text  # sem hostname de rede docker


def test_neo4j_store_fails_explicitly_when_native_service_unavailable(monkeypatch):
    """GraphRAG é opcional: se o Neo4j nativo não estiver rodando, a falha é
    um PipelineError acionável, não uma exceção genérica do driver."""
    pytest.importorskip("neo4j", reason="extra opcional graphrag não instalado neste ambiente")
    from neo4j.exceptions import ServiceUnavailable

    from dtwin.graphrag.neo4j_store import Neo4jStore

    config = GraphRagConfig(
        neo4j=Neo4jConnectionConfig(
            uri="bolt://localhost:7687",
            user="neo4j",
            password_env="NEO4J_PASSWORD_TEST_NATIVE_RUNTIME",
        )
    )
    monkeypatch.setenv("NEO4J_PASSWORD_TEST_NATIVE_RUNTIME", "senha-de-teste")

    fake_driver = MagicMock()
    fake_driver.verify_connectivity.side_effect = ServiceUnavailable("recusado")

    with patch("neo4j.GraphDatabase.driver", return_value=fake_driver):
        with pytest.raises(PipelineError, match="Neo4j nativo"):
            Neo4jStore(config)
    fake_driver.close.assert_called_once()


def test_no_docker_env_file_or_container_paths_remain_referenced():
    """Depois da migração, nenhum caminho de container deve sobreviver no
    código de aplicação nem nos launchers ativos."""
    for rel in ("dtwin", "webapp", "viewer"):
        for py_file in (ROOT / rel).rglob("*.py"):
            text = py_file.read_text(encoding="utf-8", errors="ignore")
            assert "host.docker.internal" not in text, py_file
            assert "/opt/argos" not in text, py_file
            assert "ARGOS_CONTAINER" not in text, py_file
    for launcher in ("run_win.ps1", "run_mac.sh", "INICIAR_OREN.cmd"):
        text = (ROOT / launcher).read_text(encoding="utf-8", errors="ignore")
        assert "docker run" not in text.lower(), launcher
        assert "docker compose" not in text.lower(), launcher
        assert "compose.yaml" not in text.lower(), launcher
        assert "host.docker.internal" not in text.lower(), launcher


def test_webapp_health_endpoint_responds_without_any_container_runtime():
    """Smoke nativo: FastAPI app sobe e responde /api/health em processo
    puramente Python, sem qualquer camada de container."""
    client = TestClient(server.app)
    response = client.get("/api/health")
    assert response.status_code == 200
