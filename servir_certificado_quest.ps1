param([string]$Venv = ".venv-win", [int]$Port = 8765)
$ErrorActionPreference = "Stop"
$Repo = (Resolve-Path $PSScriptRoot).Path
Set-Location $Repo
$Py = Join-Path $Repo "$Venv\Scripts\python.exe"
$Cert = Join-Path $Repo ".local\quest_https\oren-quest-cert.pem"
if (-not (Test-Path $Py)) { throw "Ambiente Python nao encontrado: $Py" }
if (-not (Test-Path $Cert)) { & (Join-Path $Repo "setup_quest_https.ps1") -Venv $Venv }
$listener = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
if ($listener) {
  $health = & curl.exe -s --max-time 2 "http://127.0.0.1:$Port/health" 2>$null
  if ($health -match 'oren-quest-certificate') {
    Write-Host "Servidor do certificado ja esta ativo." -ForegroundColor Green
    exit 0
  }
  throw "A porta $Port esta ocupada por um processo sem resposta (PID $($listener.OwningProcess)). Feche-o e tente novamente."
}
$Ip = Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
  Where-Object { $_.IPAddress -notlike '127.*' -and $_.PrefixOrigin -ne 'WellKnown' } |
  Sort-Object InterfaceMetric | Select-Object -First 1 -ExpandProperty IPAddress
if (-not $Ip) { throw "Nao foi possivel encontrar o IPv4 da rede local." }
$profile = Get-NetConnectionProfile | Where-Object IPv4Connectivity -ne 'Disconnected' | Select-Object -First 1
if ($profile.NetworkCategory -ne 'Private') {
  Write-Host "ATENCAO: a rede '$($profile.Name)' esta como $($profile.NetworkCategory)." -ForegroundColor Yellow
  Write-Host "Altere para Rede privada nas Configuracoes do Windows antes de abrir no Quest." -ForegroundColor Yellow
}
Write-Host "No Quest Browser, abra: http://${Ip}:$Port" -ForegroundColor Green
Write-Host "Esta pagina expoe somente o certificado publico. Ctrl+C encerra." -ForegroundColor Cyan
& $Py "tools\serve_quest_certificate.py" --certificate $Cert --host 0.0.0.0 --port $Port
