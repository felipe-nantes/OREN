[CmdletBinding()]
param(
    [string]$Venv = ".venv-win",
    [string]$Config = "configs\medgemma_local_4b.yaml",
    [int]$Port = 8001,
    [int]$WaitSeconds = 600
)

$ErrorActionPreference = "Stop"
$repo = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$python = Join-Path $repo "$Venv\Scripts\python.exe"
$configPath = Join-Path $repo $Config
$runtime = Join-Path $repo ".local\docker"
$pidFile = Join-Path $runtime "medgemma_host.pid"
$stdout = Join-Path $runtime "medgemma_host.stdout.log"
$stderr = Join-Path $runtime "medgemma_host.stderr.log"
New-Item -ItemType Directory -Force -Path $runtime | Out-Null

if (-not (Test-Path -LiteralPath $python)) { throw "Python environment missing: $python" }
if (-not (Test-Path -LiteralPath $configPath)) { throw "MedGemma config missing: $configPath" }

try {
    $health = Invoke-RestMethod "http://127.0.0.1:$Port/health" -TimeoutSec 3
    if ($health.status -eq "ready" -and $health.model_loaded) {
        Write-Host "MedGemma host gateway is already ready on port $Port."
        exit 0
    }
} catch { }

$process = Start-Process -FilePath $python -WorkingDirectory $repo -WindowStyle Hidden -PassThru `
    -ArgumentList @("tools\medgemma_server.py", "--config", $Config, "--host", "127.0.0.1", "--port", "$Port") `
    -RedirectStandardOutput $stdout -RedirectStandardError $stderr
[IO.File]::WriteAllText($pidFile, "$($process.Id)`n", [Text.UTF8Encoding]::new($false))

$deadline = [DateTime]::UtcNow.AddSeconds($WaitSeconds)
while ([DateTime]::UtcNow -lt $deadline) {
    if ($process.HasExited) {
        $detail = if (Test-Path $stderr) { (Get-Content $stderr -Tail 30) -join "`n" } else { "" }
        throw "MedGemma gateway exited during startup.`n$detail"
    }
    try {
        $health = Invoke-RestMethod "http://127.0.0.1:$Port/health" -TimeoutSec 5
        if ($health.status -eq "ready" -and $health.model_loaded) {
            Write-Host "MedGemma host gateway ready (PID $($process.Id))." -ForegroundColor Green
            exit 0
        }
        if ($health.status -eq "failed") { throw "MedGemma load failed: $($health.load_error)" }
    } catch {
        if ($_.Exception.Message -like "MedGemma load failed:*") { throw }
    }
    Start-Sleep -Seconds 3
}
throw "Timeout waiting for MedGemma host gateway. See $stderr"
