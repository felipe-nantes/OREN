from pathlib import Path

from tools.create_quest_access_page import build_page


ROOT = Path(__file__).resolve().parents[1]


def test_network_detection_prefers_real_gateway_and_rejects_apipa() -> None:
    source = (ROOT / "tools" / "quest_network.ps1").read_text(encoding="utf-8")
    assert "IPv4DefaultGateway" in source
    assert "169.254.*" in source
    assert "vEthernet|Docker|WSL" in source
    assert "InterfaceMetric" in source


def test_docker_start_always_refreshes_current_ip_certificate() -> None:
    source = (ROOT / "tools" / "start_argos_docker.ps1").read_text(encoding="utf-8")
    assert "ensure_docker_desktop.ps1" in source
    assert "Get-OrenQuestNetwork" in source
    assert "setup_quest_https.ps1 -Ip $questIp" in source
    setup_position = source.index("setup_quest_https.ps1 -Ip $questIp")
    assert "Test-Path .local\\quest_https" not in source[max(0, setup_position - 300) : setup_position]
    assert "--force-recreate --no-deps proxy" in source


def test_docker_desktop_is_started_and_waited_for_automatically() -> None:
    source = (ROOT / "tools" / "ensure_docker_desktop.ps1").read_text(encoding="utf-8")
    assert 'Docker Desktop.exe' in source
    assert 'Start-Process -FilePath $desktopExe' in source
    assert 'ArgumentList "--minimized"' in source
    assert 'docker info' in source
    assert 'Test-DockerEngineReady' in source
    assert '$ErrorActionPreference = "SilentlyContinue"' in source
    assert 'StartupTimeoutSeconds = 300' in source
    assert 'while ([DateTime]::UtcNow -lt $deadline)' in source


def test_one_click_launcher_uses_docker_qr_and_local_subnet_firewall() -> None:
    root_launcher = (ROOT / "INICIAR_OREN_QUEST.cmd").read_text(encoding="utf-8")
    launcher = (ROOT / "tools" / "start_oren_quest_dynamic.ps1").read_text(encoding="utf-8")
    firewall = (ROOT / "tools" / "ensure_quest_firewall.ps1").read_text(encoding="utf-8")
    assert "start_oren_quest_dynamic.ps1" in root_launcher
    assert "start_argos_docker.ps1" in launcher
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
