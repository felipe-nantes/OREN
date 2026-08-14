param([string]$Venv = ".venv-win", [string]$Ip)
$ErrorActionPreference = "Stop"
$Repo = (Resolve-Path $PSScriptRoot).Path
$Py = Join-Path $Repo "$Venv\Scripts\python.exe"
if (-not (Test-Path $Py)) { throw "Ambiente Python nao encontrado: $Py" }
. (Join-Path $Repo "tools\quest_network.ps1")
if (-not $Ip) { $Ip = (Get-OrenQuestNetwork).IPAddress }
& $Py -c "import cryptography" 2>$null
if ($LASTEXITCODE -ne 0) {
  throw "Dependencia ausente. Execute: $Py -m pip install -e `".[webapp,quest]`""
}
$raw = & $Py (Join-Path $Repo "tools\create_quest_certificate.py") --ip $Ip --out (Join-Path $Repo ".local\quest_https") --json
if ($LASTEXITCODE -ne 0) { throw "Falha ao preparar certificado HTTPS." }
$state = ($raw -join "`n") | ConvertFrom-Json
if ($state.leaf_regenerated) {
  Write-Host "Certificado HTTPS atualizado automaticamente para $Ip." -ForegroundColor Green
} else {
  Write-Host "Certificado HTTPS ja corresponde ao IP $Ip." -ForegroundColor Green
}
if ($state.quest_ca_install_required) {
  Write-Host "Primeiro uso: instale a CA publica no Quest uma unica vez." -ForegroundColor Yellow
  Write-Host "Execute servir_certificado_quest.ps1 para disponibilizar o arquivo." -ForegroundColor Yellow
} elseif ($state.ca_migrated) {
  Write-Host "Certificado anteriormente confiado foi preservado como CA estavel." -ForegroundColor Cyan
} else {
  Write-Host "A CA OREN permanece a mesma; trocar de rede nao exige reinstalacao no Quest." -ForegroundColor Cyan
}
$state
