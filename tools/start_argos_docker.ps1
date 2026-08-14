[CmdletBinding()]
param(
    [ValidateSet("Host", "Container")]
    [string]$MedGemmaMode = "Host",
    [switch]$NoBuild,
    [switch]$SkipMedGemmaStart
)

$ErrorActionPreference = "Stop"
$repo = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $repo
$dockerBin = "C:\Program Files\Docker\Docker\resources\bin"
if (-not (Get-Command docker -ErrorAction SilentlyContinue) -and (Test-Path $dockerBin)) {
    $env:PATH = "$dockerBin;$env:PATH"
}

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw "Docker CLI not found. Run tools\setup_docker_windows.ps1 and restart Windows if requested."
}
& powershell -NoProfile -ExecutionPolicy Bypass -File tools\ensure_docker_desktop.ps1
if ($LASTEXITCODE -ne 0) { throw "Docker Desktop engine could not be started." }

$networkHelper = Join-Path $repo "tools\quest_network.ps1"
. $networkHelper
$questNetwork = Get-OrenQuestNetwork
$questIp = $questNetwork.IPAddress
if ($questIp) {
    # Evita que o backend dentro do Docker publique o IP interno 172.x quando a
    # sessão Quest é criada pela interface desktop em 127.0.0.1.
    $env:OREN_QUEST_BASE_URL = "https://${questIp}:8443"
}

if (-not (Test-Path .env.docker)) {
    & powershell -NoProfile -ExecutionPolicy Bypass -File tools\initialize_argos_docker.ps1
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
# Executado em toda inicializacao: e idempotente e renova somente o certificado
# de servidor quando o IPv4 LAN mudou. A CA confiada pelo Quest permanece fixa.
& powershell -NoProfile -ExecutionPolicy Bypass -File setup_quest_https.ps1 -Ip $questIp
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$composeArgs = @("compose", "--env-file", ".env.docker")
if ($MedGemmaMode -eq "Container") {
    $hostHealth = $null
    try { $hostHealth = Invoke-RestMethod "http://127.0.0.1:8001/health" -TimeoutSec 3 } catch { }
    if ($hostHealth) {
        & powershell -NoProfile -ExecutionPolicy Bypass -File tools\stop_medgemma_gateway_win.ps1
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    }
    $env:MEDGEMMA_BASE_URL = "http://medgemma:8001"
    $composeArgs += @("--profile", "medgemma-container")
} else {
    $previousPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    docker compose --env-file .env.docker --profile medgemma-container stop medgemma 2>$null | Out-Null
    $stopCode = $LASTEXITCODE
    $ErrorActionPreference = $previousPreference
    if ($stopCode -ne 0) { throw "Could not stop the optional MedGemma container." }
    if (-not $SkipMedGemmaStart) {
        & powershell -NoProfile -ExecutionPolicy Bypass -File tools\start_medgemma_gateway_win.ps1
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    }
}

& docker @composeArgs config --quiet
if ($LASTEXITCODE -ne 0) { throw "Docker Compose configuration is invalid." }

$upArgs = $composeArgs + @("up", "-d")
if (-not $NoBuild) { $upArgs += "--build" }
& docker @upArgs
if ($LASTEXITCODE -ne 0) { throw "ARGOS Docker startup failed." }
# O upstream do Nginx e resolvido no startup. Se o ARGOS foi recriado ao trocar
# o backend MedGemma, o proxy tambem precisa ser recriado para nao manter o IP
# interno antigo e devolver 502.
& docker @composeArgs up -d --force-recreate --no-deps proxy
if ($LASTEXITCODE -ne 0) { throw "ARGOS proxy recreation failed." }

$deadline = [DateTime]::UtcNow.AddMinutes(15)
while ([DateTime]::UtcNow -lt $deadline) {
    try {
        $health = Invoke-RestMethod "http://127.0.0.1:8080/api/health" -TimeoutSec 8
        $backendReady = $health.backend -eq "pronto"
        $backendIntentionallyOffline = $SkipMedGemmaStart -and $health.backend -eq "desligado"
        if ($backendReady -or $backendIntentionallyOffline) {
            Write-Host "OREN desktop: http://127.0.0.1:8080" -ForegroundColor Green
            if ($questIp) { Write-Host "OREN Meta Quest: https://${questIp}:8443/quest/" -ForegroundColor Green }
            if ($backendIntentionallyOffline) {
                Write-Host "MedGemma não iniciado por solicitação; visualizador e fluxos sem inferência estão prontos." -ForegroundColor Yellow
            }
            exit 0
        }
    } catch { }
    Start-Sleep -Seconds 5
}

docker compose --env-file .env.docker ps
docker compose --env-file .env.docker logs --tail 100
throw "ARGOS containers did not become healthy within 15 minutes."
