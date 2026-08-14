[CmdletBinding()]
param(
    [int]$StartupTimeoutSeconds = 300,
    [int]$PollIntervalSeconds = 3
)
$ErrorActionPreference = "Stop"

function Test-DockerEngineReady {
    $previousPreference = $ErrorActionPreference
    try {
        # No PowerShell 5, stderr de um executavel nativo pode virar ErrorRecord.
        # Engine desligado e um estado esperado desta sondagem, nao uma excecao.
        $ErrorActionPreference = "SilentlyContinue"
        & docker info *> $null
        return $LASTEXITCODE -eq 0
    } finally {
        $ErrorActionPreference = $previousPreference
    }
}

$dockerBin = "C:\Program Files\Docker\Docker\resources\bin"
if (-not (Get-Command docker -ErrorAction SilentlyContinue) -and (Test-Path $dockerBin)) {
    $env:PATH = "$dockerBin;$env:PATH"
}
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw "Docker CLI nao encontrado. Instale o Docker Desktop com tools\setup_docker_windows.ps1."
}

if (Test-DockerEngineReady) {
    Write-Host "Docker Engine ja esta pronto." -ForegroundColor Green
    exit 0
}

$desktopCandidates = @(
    (Join-Path $env:ProgramFiles "Docker\Docker\Docker Desktop.exe"),
    (Join-Path $env:LOCALAPPDATA "Docker\Docker Desktop.exe")
)
$desktopExe = $desktopCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $desktopExe) {
    throw "Docker Desktop nao encontrado. Execute tools\setup_docker_windows.ps1."
}

$desktopProcess = Get-Process -Name "Docker Desktop" -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $desktopProcess) {
    Write-Host "Docker Engine desligado. Iniciando Docker Desktop automaticamente..." -ForegroundColor Cyan
    Start-Process -FilePath $desktopExe -ArgumentList "--minimized" -WindowStyle Minimized | Out-Null
} else {
    Write-Host "Docker Desktop esta abrindo; aguardando o Engine..." -ForegroundColor Cyan
}

$deadline = [DateTime]::UtcNow.AddSeconds($StartupTimeoutSeconds)
$nextProgress = [DateTime]::UtcNow
while ([DateTime]::UtcNow -lt $deadline) {
    if (Test-DockerEngineReady) {
        Write-Host "Docker Engine pronto." -ForegroundColor Green
        exit 0
    }
    if ([DateTime]::UtcNow -ge $nextProgress) {
        $remaining = [Math]::Max(0, [int]($deadline - [DateTime]::UtcNow).TotalSeconds)
        Write-Host "Aguardando Docker Engine (limite restante: ${remaining}s)..." -ForegroundColor DarkCyan
        $nextProgress = [DateTime]::UtcNow.AddSeconds(15)
    }
    Start-Sleep -Seconds $PollIntervalSeconds
}

throw "Docker Desktop foi iniciado, mas o Engine nao ficou pronto em $StartupTimeoutSeconds segundos. Consulte o diagnostico do Docker Desktop."
