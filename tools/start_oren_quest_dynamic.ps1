[CmdletBinding()]
param(
    [switch]$NoBuild,
    [switch]$SkipMedGemmaStart,
    [switch]$NoOpen,
    [switch]$SkipFirewall
)
$ErrorActionPreference = "Stop"
$repo = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $repo
. (Join-Path $repo "tools\quest_network.ps1")
$network = Get-OrenQuestNetwork

Write-Host "Rede detectada: $($network.NetworkName) | $($network.InterfaceAlias) | $($network.IPAddress)" -ForegroundColor Cyan
if (-not $SkipFirewall) {
    & powershell -NoProfile -ExecutionPolicy Bypass -File tools\ensure_quest_firewall.ps1 -Port 8443
    if ($LASTEXITCODE -ne 0) { throw "Falha ao liberar acesso local no firewall." }
}

$startArgs = @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', 'tools\start_argos_docker.ps1', '-NoBuild')
if ($SkipMedGemmaStart) { $startArgs += '-SkipMedGemmaStart' }
& powershell @startArgs
if ($LASTEXITCODE -ne 0) { throw "OREN nao iniciou corretamente." }

# Rele a rede depois do Docker iniciar para evitar publicar um endereco obsoleto
# se o adaptador reconectou durante a inicializacao.
$network = Get-OrenQuestNetwork
$questUrl = "https://$($network.IPAddress):8443/quest/"
$statePath = Join-Path $repo '.local\quest_https\certificate-state.json'
if (-not (Test-Path $statePath)) { throw "Estado do certificado Quest nao encontrado." }
$state = Get-Content $statePath -Raw | ConvertFrom-Json
$page = Join-Path $repo '.local\quest_https\ABRIR_NO_META_QUEST.html'
$py = Join-Path $repo '.venv-win\Scripts\python.exe'
& $py tools\create_quest_access_page.py --url $questUrl --ip $network.IPAddress `
    --network $network.NetworkName --fingerprint $state.ca_sha256_fingerprint --out $page | Out-Null
if ($LASTEXITCODE -ne 0) { throw "Falha ao criar o QR de acesso." }

try { Set-Clipboard -Value $questUrl } catch { }
Write-Host ""
Write-Host "OREN pronto no Meta Quest: $questUrl" -ForegroundColor Green
Write-Host "O link foi copiado. O QR foi aberto no PC para leitura pelo Quest." -ForegroundColor Cyan
if ($state.quest_ca_install_required) {
    Write-Host "ATENCAO: esta CA ainda precisa ser instalada uma unica vez no Quest." -ForegroundColor Yellow
    Write-Host "Execute SERVIR_CERTIFICADO_QUEST.cmd antes do primeiro acesso HTTPS." -ForegroundColor Yellow
}
if (-not $NoOpen) { Start-Process $page }
