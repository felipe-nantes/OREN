param([string]$Venv = ".venv-win", [int]$Port = 8765)
$ErrorActionPreference = "Stop"
$Repo = (Resolve-Path $PSScriptRoot).Path
Set-Location $Repo
$Py = Join-Path $Repo "$Venv\Scripts\python.exe"
$Cert = Join-Path $Repo ".local\quest_https\oren-quest-ca.pem"
if (-not (Test-Path $Py)) { throw "Ambiente Python nao encontrado: $Py" }
& (Join-Path $Repo "setup_quest_https.ps1") -Venv $Venv | Out-Null
if (-not (Test-Path $Cert)) { throw "CA publica do OREN nao encontrada: $Cert" }
$listener = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
if ($listener) {
  $health = & curl.exe -s --max-time 2 "http://127.0.0.1:$Port/health" 2>$null
  if ($health -match 'oren-quest-certificate') {
    Write-Host "Servidor do certificado ja esta ativo." -ForegroundColor Green
    exit 0
  }
  throw "A porta $Port esta ocupada por um processo sem resposta (PID $($listener.OwningProcess)). Feche-o e tente novamente."
}
. (Join-Path $Repo "tools\quest_network.ps1")
$network = Get-OrenQuestNetwork
$Ip = $network.IPAddress
Write-Host "No Quest Browser, abra: http://${Ip}:$Port" -ForegroundColor Green
Write-Host "Esta pagina expoe somente a CA publica estavel. Instale uma unica vez. Ctrl+C encerra." -ForegroundColor Cyan
& $Py "tools\serve_quest_certificate.py" --certificate $Cert --host 0.0.0.0 --port $Port
