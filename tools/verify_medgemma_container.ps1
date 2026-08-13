[CmdletBinding()]
param(
    [string]$EnvFile = ".env.docker",
    [int]$WaitSeconds = 600
)

$ErrorActionPreference = "Stop"
$repo = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $repo
$dockerBin = "C:\Program Files\Docker\Docker\resources\bin"
if (-not (Get-Command docker -ErrorAction SilentlyContinue) -and (Test-Path $dockerBin)) {
    $env:PATH = "$dockerBin;$env:PATH"
}
$dockerExe = (Get-Command docker -CommandType Application | Select-Object -First 1).Source
$resultPath = Join-Path $repo "artifacts\docker-validation\medgemma-container-verification.json"
New-Item -ItemType Directory -Force -Path (Split-Path $resultPath) | Out-Null
$testFailure = $null

function Invoke-DockerStrict([string[]]$Arguments) {
    $previous = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    $output = & $script:dockerExe @Arguments 2>&1
    $code = $LASTEXITCODE
    $ErrorActionPreference = $previous
    if ($code -ne 0) { throw "docker $($Arguments -join ' ') failed: $($output -join [Environment]::NewLine)" }
    return $output
}

try {
    & powershell -NoProfile -ExecutionPolicy Bypass -File tools\stop_medgemma_gateway_win.ps1
    if ($LASTEXITCODE -ne 0) { throw "Could not stop host MedGemma" }
    $env:MEDGEMMA_BASE_URL = "http://medgemma:8001"
    Invoke-DockerStrict @("compose", "--env-file", $EnvFile, "--profile", "medgemma-container", "up", "-d", "--force-recreate", "medgemma", "argos", "proxy") | Out-Null

    $deadline = [DateTime]::UtcNow.AddSeconds($WaitSeconds)
    $health = $null
    while ([DateTime]::UtcNow -lt $deadline) {
        try {
            $raw = Invoke-DockerStrict @(
                "compose", "--env-file", $EnvFile, "--profile", "medgemma-container",
                "exec", "-T", "medgemma", "python", "-c",
                "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8001/health',timeout=5).read().decode())"
            )
            $health = ($raw -join "`n") | ConvertFrom-Json
            if ($health.status -eq "ready" -and $health.model_loaded) { break }
            if ($health.status -eq "failed") { throw "Container model failed: $($health.load_error)" }
        } catch {
            if ($_.Exception.Message -like "Container model failed:*") { throw }
        }
        Start-Sleep -Seconds 5
    }
    if (-not $health -or $health.status -ne "ready") {
        throw "Container MedGemma did not become ready within $WaitSeconds seconds"
    }

    $argosHealth = Invoke-RestMethod "http://127.0.0.1:8080/api/health" -TimeoutSec 15
    if ($argosHealth.backend -ne "pronto") { throw "ARGOS did not reach container MedGemma" }
    $gpuLines = Invoke-DockerStrict @(
        "compose", "--env-file", $EnvFile, "--profile", "medgemma-container",
        "exec", "-T", "medgemma", "python", "-c",
        "import torch; print(torch.cuda.is_available()); print(torch.cuda.get_device_name(0)); print(torch.cuda.memory_allocated())"
    )
    if ($gpuLines[0] -ne "True") { throw "Container MedGemma has no CUDA" }
    $result = [ordered]@{
        schema = "argos-medgemma-container-verification-v1"
        passed = $true
        health = $health
        argos_backend = $argosHealth.backend
        cuda_available = $true
        gpu = $gpuLines[1]
        allocated_bytes = [int64]$gpuLines[2]
        host_port_exposed = $false
    }
    [IO.File]::WriteAllText(
        $resultPath,
        ($result | ConvertTo-Json -Depth 8),
        [Text.UTF8Encoding]::new($false)
    )
} catch {
    $testFailure = $_
} finally {
    try {
        Invoke-DockerStrict @("compose", "--env-file", $EnvFile, "--profile", "medgemma-container", "stop", "medgemma") | Out-Null
        Remove-Item Env:MEDGEMMA_BASE_URL -ErrorAction SilentlyContinue
        & powershell -NoProfile -ExecutionPolicy Bypass -File tools\start_medgemma_gateway_win.ps1
        if ($LASTEXITCODE -ne 0) { throw "Host MedGemma restoration failed" }
        Invoke-DockerStrict @("compose", "--env-file", $EnvFile, "up", "-d", "--force-recreate", "argos", "proxy") | Out-Null
        $restoreDeadline = [DateTime]::UtcNow.AddMinutes(5)
        do {
            Start-Sleep -Seconds 3
            try {
                $restored = Invoke-RestMethod "http://127.0.0.1:8080/api/health" -TimeoutSec 10
            } catch { $restored = $null }
        } while (
            (!$restored -or $restored.backend -ne "pronto") -and
            [DateTime]::UtcNow -lt $restoreDeadline
        )
        if (-not $restored -or $restored.backend -ne "pronto") {
            throw "Hybrid host mode did not recover"
        }
    } catch {
        if ($testFailure) {
            $testFailure = [Exception]::new(
                "$($testFailure.Exception.Message); restoration also failed: $($_.Exception.Message)"
            )
        } else { $testFailure = $_ }
    }
}

if ($testFailure) { throw $testFailure }
Get-Content -LiteralPath $resultPath -Raw
