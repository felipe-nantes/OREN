from pathlib import Path


def test_quest_http_launcher_is_explicitly_development_only():
    script = Path("run_quest_http_win.ps1").read_text("utf-8")
    assert "--host 0.0.0.0" in script
    assert "--port $Port" in script
    assert "unsafely-treat-insecure-origin-as-secure" in script
    assert "OREN_QUEST_BASE_URL" in script
    assert "IPv4DefaultGateway" in script
    assert "/quest" in script
    assert "ssl" not in script.lower()
