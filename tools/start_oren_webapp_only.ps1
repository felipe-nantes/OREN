param([int]$Port = 8080, [string]$Venv = ".venv-win")
$ErrorActionPreference = "Stop"
$Repo = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $Repo
$Py = Join-Path $Repo "$Venv\Scripts\python.exe"
if (-not (Test-Path $Py)) { throw "Ambiente Python nao encontrado: $Py" }
$env:WEBAPP_MEDGEMMA_CONFIG = "configs\medgemma_local_4b.yaml"
$env:WEBAPP_MEDGEMMA_HEALTH = "http://127.0.0.1:8001/health"
$env:OREN_QUEST_PORT = "8443"
& $Py -m uvicorn webapp.server:app --host 127.0.0.1 --port $Port
