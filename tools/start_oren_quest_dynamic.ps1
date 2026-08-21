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

# Runtime nativo: este launcher NAO sobe gateway/webapp mais (isso era
# responsabilidade do Docker Compose). Ele publica o QR de acesso para uma
# instancia OREN Quest que ja esteja rodando nativamente. Fluxo em duas
# etapas: (1) .\run_win.ps1 numa janela (gateway MedGemma + webapp desktop);
# (2) .\run_quest_win.ps1 em outra janela (webapp HTTPS :8443 p/ o Quest).
# Este script eh o atalho da etapa 3: detectar a rede e publicar o QR.
if (-not $SkipMedGemmaStart) {
  try {
    $gatewayHealth = Invoke-RestMethod -Uri "http://127.0.0.1:8001/health" -TimeoutSec 3
    if ($gatewayHealth.status -ne "ready") { throw "gateway nao pronto" }
  } catch {
    throw "Gateway MedGemma (:8001) nao esta pronto. Execute .\run_win.ps1 numa janela antes de usar este atalho."
  }
}
try {
  # -SkipCertificateCheck so existe no PowerShell 7+; esta maquina roda 5.1
  # (Windows PowerShell), entao o bypass de certificado autoassinado precisa
  # ser feito via ServicePointManager, valido so' para esta sessao.
  if ($PSVersionTable.PSVersion.Major -lt 6) {
    Add-Type -TypeDefinition @"
using System.Net;
using System.Security.Cryptography.X509Certificates;
public class OrenQuestTrustAll : ICertificatePolicy {
    public bool CheckValidationResult(ServicePoint sp, X509Certificate cert, WebRequest req, int problem) { return true; }
}
"@ -ErrorAction SilentlyContinue
    [System.Net.ServicePointManager]::CertificatePolicy = New-Object OrenQuestTrustAll
    Invoke-RestMethod -Uri "https://127.0.0.1:8443/api/health" -TimeoutSec 3 | Out-Null
  } else {
    Invoke-RestMethod -Uri "https://127.0.0.1:8443/api/health" -TimeoutSec 3 -SkipCertificateCheck | Out-Null
  }
} catch {
  throw "Webapp HTTPS do Quest (:8443) nao esta no ar. Execute .\run_quest_win.ps1 em outra janela antes de usar este atalho."
}

# Rele a rede apos confirmar que o webapp esta pronto, para nao publicar um
# endereco obsoleto se o adaptador reconectou nesse meio-tempo.
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
