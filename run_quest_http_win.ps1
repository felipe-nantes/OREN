param(
  [string]$Venv = ".venv-win",
  [int]$Port = 8082
)
$ErrorActionPreference = "Stop"
$Repo = (Resolve-Path $PSScriptRoot).Path
Set-Location $Repo
$Py = Join-Path $Repo "$Venv\Scripts\python.exe"
if (-not (Test-Path $Py)) { throw "Ambiente Python nao encontrado: $Py" }
$DefaultAdapters = Get-NetIPConfiguration -ErrorAction SilentlyContinue |
  Where-Object { $_.NetAdapter.Status -eq "Up" -and $_.IPv4DefaultGateway }
$Ip = $DefaultAdapters |
  ForEach-Object { $_.IPv4Address } |
  Where-Object { $_.IPAddress -notlike '127.*' -and $_.IPAddress -notlike '169.254.*' } |
  Select-Object -First 1 -ExpandProperty IPAddress
if (-not $Ip) { throw "Nao foi possivel encontrar o IPv4 da rede local." }
$listener = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
if ($listener) {
  $healthText = & curl.exe -s --max-time 3 "http://127.0.0.1:$Port/api/health" 2>$null
  $health = $null
  try { $health = $healthText | ConvertFrom-Json } catch { $health = $null }
  if ($health -and $health.backend) {
    Write-Host "OREN Quest HTTP ja esta ativo: http://${Ip}:$Port" -ForegroundColor Green
    Write-Host "Use este endereco em chrome://flags como origem segura." -ForegroundColor Cyan
    exit 0
  }
  throw "A porta $Port esta ocupada por outro processo (PID $($listener.OwningProcess))."
}
$env:WEBAPP_MEDGEMMA_CONFIG = "configs\medgemma_local_4b.yaml"
$env:WEBAPP_MEDGEMMA_HEALTH = "http://127.0.0.1:8001/health"
$env:OREN_QUEST_BASE_URL = "http://${Ip}:$Port"
Write-Host "OREN Quest sem certificado: http://${Ip}:$Port" -ForegroundColor Green
Write-Host "Atalho do caso atual: http://${Ip}:$Port/quest" -ForegroundColor Green
Write-Host "No Quest Browser, configure esta origem em:" -ForegroundColor Cyan
Write-Host "chrome://flags/#unsafely-treat-insecure-origin-as-secure" -ForegroundColor Yellow
Write-Host "Depois reinicie o navegador pelo botao Relaunch." -ForegroundColor Yellow
& $Py -m uvicorn webapp.server:app --host 0.0.0.0 --port $Port
