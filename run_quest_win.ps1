param(
  [string]$Venv = ".venv-win",
  [int]$Port = 8443
)
$ErrorActionPreference = "Stop"
$Repo = (Resolve-Path $PSScriptRoot).Path
Set-Location $Repo
$Py = Join-Path $Repo "$Venv\Scripts\python.exe"
$Cert = Join-Path $Repo ".local\quest_https\oren-quest-cert.pem"
$Key = Join-Path $Repo ".local\quest_https\oren-quest-key.pem"
if (-not (Test-Path $Py)) { throw "Ambiente Python nao encontrado: $Py" }
if (-not (Test-Path $Cert) -or -not (Test-Path $Key)) {
  & (Join-Path $Repo "setup_quest_https.ps1") -Venv $Venv
}
$Ip = Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
  Where-Object { $_.IPAddress -notlike '127.*' -and $_.PrefixOrigin -ne 'WellKnown' } |
  Sort-Object InterfaceMetric | Select-Object -First 1 -ExpandProperty IPAddress
if (-not $Ip) { throw "Nao foi possivel encontrar o IPv4 da rede local." }

# O launcher pode ser executado mais de uma vez (duplo clique, tarefa agendada
# ou retomada do Windows). Uma instancia OREN saudavel na porta solicitada nao e
# erro: reutilize-a. Se a porta pertencer a outro servico, preserve a falha para
# nao mascarar conflito real.
$listener = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
  Select-Object -First 1
if ($listener) {
  $healthText = & curl.exe -k -s --max-time 3 "https://127.0.0.1:$Port/api/health" 2>$null
  $health = $null
  try { $health = $healthText | ConvertFrom-Json } catch { $health = $null }
  if ($health -and $health.backend) {
    Write-Host "OREN Quest ja esta ativo: https://${Ip}:$Port" -ForegroundColor Green
    Write-Host "Nao foi iniciada uma segunda copia do servidor." -ForegroundColor Cyan
    exit 0
  }
  $owner = Get-CimInstance Win32_Process -Filter "ProcessId=$($listener.OwningProcess)" -ErrorAction SilentlyContinue
  throw "A porta $Port esta ocupada por outro processo (PID $($listener.OwningProcess)): $($owner.CommandLine)"
}

$env:WEBAPP_PORT = "$Port"
$env:WEBAPP_MEDGEMMA_CONFIG = "configs\medgemma_local_4b.yaml"
$env:WEBAPP_MEDGEMMA_HEALTH = "http://127.0.0.1:8001/health"
$env:OREN_QUEST_PORT = "$Port"
Write-Host "OREN Quest seguro: https://${Ip}:$Port" -ForegroundColor Green
Write-Host "Mantenha esta janela aberta. O fluxo desktop em :8080 permanece independente." -ForegroundColor Cyan
& $Py -m uvicorn webapp.server:app --host 0.0.0.0 --port $Port --ssl-keyfile $Key --ssl-certfile $Cert
