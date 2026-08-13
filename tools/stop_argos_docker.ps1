[CmdletBinding()]
param([switch]$StopHostMedGemma)

$ErrorActionPreference = "Stop"
$repo = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $repo
$dockerBin = "C:\Program Files\Docker\Docker\resources\bin"
if (-not (Get-Command docker -ErrorAction SilentlyContinue) -and (Test-Path $dockerBin)) {
    $env:PATH = "$dockerBin;$env:PATH"
}
docker compose --env-file .env.docker --profile medgemma-container --profile tools down

if ($StopHostMedGemma) {
    & powershell -NoProfile -ExecutionPolicy Bypass -File tools\stop_medgemma_gateway_win.ps1
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
