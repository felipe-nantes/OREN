param([string]$Venv = ".venv-win")
$ErrorActionPreference = "Stop"
$Repo = (Resolve-Path $PSScriptRoot).Path
$Py = Join-Path $Repo "$Venv\Scripts\python.exe"
if (-not (Test-Path $Py)) { throw "Ambiente Python nao encontrado: $Py" }
$Ip = Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
  Where-Object { $_.IPAddress -notlike '127.*' -and $_.PrefixOrigin -ne 'WellKnown' } |
  Sort-Object InterfaceMetric | Select-Object -First 1 -ExpandProperty IPAddress
if (-not $Ip) { throw "Nao foi possivel encontrar o IPv4 da rede local." }
& $Py -c "import cryptography" 2>$null
if ($LASTEXITCODE -ne 0) {
  throw "Dependencia ausente. Execute: $Py -m pip install -e `".[webapp,quest]`""
}
& $Py (Join-Path $Repo "tools\create_quest_certificate.py") --ip $Ip --out (Join-Path $Repo ".local\quest_https")
if ($LASTEXITCODE -ne 0) { throw "Falha ao gerar certificado HTTPS." }
Write-Host "Certificado criado para $Ip." -ForegroundColor Green
Write-Host "Instale oren-quest-cert.pem como certificado confiavel no Quest apenas na rede de pesquisa." -ForegroundColor Yellow
