from pathlib import Path

from tools.create_quest_access_page import build_page


ROOT = Path(__file__).resolve().parents[1]


def test_network_detection_prefers_real_gateway_and_rejects_apipa() -> None:
    source = (ROOT / "tools" / "quest_network.ps1").read_text(encoding="utf-8")
    assert "IPv4DefaultGateway" in source
    assert "169.254.*" in source
    assert "vEthernet|Docker|WSL" in source
    assert "InterfaceMetric" in source


def test_dynamic_launcher_requires_native_gateway_and_webapp_already_running() -> None:
    """Migração Docker->nativo (TASK-2026-08-18-MIGR-01): o launcher de um
    clique do Quest não sobe mais gateway/webapp via Docker Compose. Ele exige
    que .\\run_win.ps1 e .\\run_quest_win.ps1 já estejam rodando (fluxo nativo
    em duas etapas, decisão do usuário) e falha com mensagem acionável."""
    source = (ROOT / "tools" / "start_oren_quest_dynamic.ps1").read_text(encoding="utf-8")
    assert "start_argos_docker.ps1" not in source
    assert "ensure_docker_desktop.ps1" not in source
    assert "Get-OrenQuestNetwork" in source
    assert "http://127.0.0.1:8001/health" in source
    assert "https://127.0.0.1:8443/api/health" in source
    assert ".\\run_win.ps1" in source
    assert ".\\run_quest_win.ps1" in source


def test_one_click_launcher_uses_native_qr_and_local_subnet_firewall() -> None:
    root_launcher = (ROOT / "INICIAR_OREN_QUEST.cmd").read_text(encoding="utf-8")
    launcher = (ROOT / "tools" / "start_oren_quest_dynamic.ps1").read_text(encoding="utf-8")
    firewall = (ROOT / "tools" / "ensure_quest_firewall.ps1").read_text(encoding="utf-8")
    assert "start_oren_quest_dynamic.ps1" in root_launcher
    assert 'https://$($network.IPAddress):8443/quest/' in launcher
    assert "Set-Clipboard" in launcher
    assert "create_quest_access_page.py" in launcher
    assert "RemoteAddress LocalSubnet" in firewall
    assert "Profile Any" in firewall


def test_access_qr_has_short_url_but_no_session_token_or_remote_asset() -> None:
    page = build_page(
        url="https://192.168.1.40:8443/quest/",
        ip="192.168.1.40",
        network="Pesquisa",
        fingerprint="a" * 64,
    )
    assert "https://192.168.1.40:8443/quest/" in page
    assert "xr_token" not in page
    assert "http://" not in page
    assert "https://" in page
    assert "data:image/svg+xml;base64," in page


def test_public_certificate_server_uses_stable_ca_and_never_key() -> None:
    launcher = (ROOT / "servir_certificado_quest.ps1").read_text(encoding="utf-8")
    server = (ROOT / "tools" / "serve_quest_certificate.py").read_text(encoding="utf-8")
    assert "oren-quest-ca.pem" in launcher
    assert "oren-quest-key" not in server
    assert "uma unica vez" in server
