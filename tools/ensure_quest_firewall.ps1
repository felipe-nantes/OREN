[CmdletBinding()]
param([int]$Port = 8443, [switch]$Elevated)
$ErrorActionPreference = "Stop"
$ruleName = "OREN Meta Quest HTTPS $Port"

$existing = Get-NetFirewallRule -DisplayName $ruleName -ErrorAction SilentlyContinue |
    Where-Object { $_.Enabled -eq 'True' -and $_.Direction -eq 'Inbound' -and $_.Action -eq 'Allow' } |
    Select-Object -First 1
if ($existing) {
    Write-Host "Firewall OREN pronto: TCP $Port, somente rede local." -ForegroundColor Green
    exit 0
}

$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
    [Security.Principal.WindowsBuiltInRole]::Administrator
)
if (-not $isAdmin) {
    if ($Elevated) { throw "Nao foi possivel obter permissao administrativa para o firewall." }
    $arguments = @(
        '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', ('"' + $PSCommandPath + '"'),
        '-Port', $Port, '-Elevated'
    )
    $process = Start-Process powershell.exe -Verb RunAs -Wait -PassThru -ArgumentList $arguments
    if ($process.ExitCode -ne 0) { throw "Regra de firewall nao foi criada." }
    Write-Host "Firewall OREN configurado para a rede local." -ForegroundColor Green
    exit 0
}

New-NetFirewallRule -DisplayName $ruleName -Group "OREN" -Direction Inbound -Action Allow `
    -Protocol TCP -LocalPort $Port -RemoteAddress LocalSubnet -Profile Any | Out-Null
Write-Host "Firewall OREN criado: TCP $Port, origem LocalSubnet." -ForegroundColor Green
