from pathlib import Path


def test_start_medgemma_uses_configurable_windows_venv():
    text = Path("tools/start_medgemma.ps1").read_text(encoding="utf-8")
    assert '[string]$Venv = ".venv-win"' in text
    assert 'Join-Path $Root "$Venv\\Scripts\\python.exe"' in text
    assert 'Join-Path $Root ".venv\\Scripts\\python.exe"' not in text


def test_start_medgemma_launches_hidden_and_runs_local_only_preflight():
    text = Path("tools/start_medgemma.ps1").read_text(encoding="utf-8")
    assert "--local-only" in text
    assert "-WindowStyle Hidden" in text
    assert "model_loaded -eq $true" in text
