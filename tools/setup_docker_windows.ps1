[CmdletBinding()]
param([switch]$Elevated)

$ErrorActionPreference = "Stop"
$scriptPath = $MyInvocation.MyCommand.Path
$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
    [Security.Principal.WindowsBuiltInRole]::Administrator
)

if (-not $isAdmin) {
    Write-Host "Administrator permission is required once to enable WSL 2."
    $arguments = @(
        "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", "`"$scriptPath`"", "-Elevated"
    )
    $process = Start-Process powershell.exe -Verb RunAs -ArgumentList $arguments -PassThru -Wait
    exit $process.ExitCode
}

Write-Host "Enabling/updating WSL 2..." -ForegroundColor Cyan
& wsl.exe --install --no-distribution
$wslExit = $LASTEXITCODE
if ($wslExit -notin @(0, 3010)) {
    throw "WSL installation failed with exit code $wslExit."
}

& wsl.exe --update
if ($LASTEXITCODE -ne 0 -and $wslExit -ne 3010) {
    throw "WSL update failed with exit code $LASTEXITCODE."
}

Write-Host "Installing Docker Desktop..." -ForegroundColor Cyan
& winget install --exact --id Docker.DockerDesktop --silent `
    --accept-package-agreements --accept-source-agreements
if ($LASTEXITCODE -ne 0) {
    throw "Docker Desktop installation failed with exit code $LASTEXITCODE."
}

$marker = Join-Path $env:LOCALAPPDATA "ARGOS\docker-install.json"
New-Item -ItemType Directory -Force -Path (Split-Path $marker) | Out-Null
[IO.File]::WriteAllText(
    $marker,
    (@{
        installed_at = [DateTime]::UtcNow.ToString("o")
        wsl_exit_code = $wslExit
        reboot_required = ($wslExit -eq 3010)
    } | ConvertTo-Json),
    [Text.UTF8Encoding]::new($false)
)

if ($wslExit -eq 3010) {
    Write-Host "Installation completed. Restart Windows before starting Docker Desktop." -ForegroundColor Yellow
} else {
    Write-Host "Installation completed. Start Docker Desktop from the Start menu." -ForegroundColor Green
}
