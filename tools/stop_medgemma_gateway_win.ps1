[CmdletBinding()]
param([int]$Port = 8001)

$ErrorActionPreference = "Stop"
$repo = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$pidFile = Join-Path $repo ".local\docker\medgemma_host.pid"

if (-not (Test-Path -LiteralPath $pidFile)) {
    $listener = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    if ($listener) {
        throw "Port $Port is occupied, but no ARGOS-managed MedGemma PID file exists. Stop it manually."
    }
    Write-Host "MedGemma host gateway is already stopped."
    exit 0
}

$rootPid = [int](Get-Content -LiteralPath $pidFile -TotalCount 1)
$all = @(Get-CimInstance Win32_Process)
$queue = [Collections.Generic.Queue[int]]::new()
$queue.Enqueue($rootPid)
$tree = [Collections.Generic.List[int]]::new()
while ($queue.Count -gt 0) {
    $current = $queue.Dequeue()
    if (-not $tree.Contains($current)) { $tree.Add($current) }
    foreach ($child in $all | Where-Object ParentProcessId -eq $current) {
        $queue.Enqueue([int]$child.ProcessId)
    }
}
for ($index = $tree.Count - 1; $index -ge 0; $index--) {
    Stop-Process -Id $tree[$index] -Force -ErrorAction SilentlyContinue
}
Remove-Item -LiteralPath $pidFile -Force -ErrorAction SilentlyContinue

$deadline = [DateTime]::UtcNow.AddSeconds(30)
do {
    Start-Sleep -Milliseconds 500
    $listener = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
} while ($listener -and [DateTime]::UtcNow -lt $deadline)
if ($listener) { throw "MedGemma host gateway did not release port $Port." }
Write-Host "MedGemma host gateway stopped." -ForegroundColor Green
