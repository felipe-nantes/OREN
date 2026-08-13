[CmdletBinding()]
param(
    [ValidateSet("Build", "Update", "Query", "Explain", "Path", "Status", "HookCheck")]
    [string]$Action = "Status",
    [string]$Question,
    [string]$From,
    [string]$To,
    [ValidateRange(1, 32)]
    [int]$MaxWorkers = 4
)

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$graphifyExe = Join-Path $projectRoot ".local\graphify-venv\Scripts\graphify.exe"
$graphPath = Join-Path $projectRoot "graphify-out\graph.json"

if (-not (Test-Path -LiteralPath $graphifyExe)) {
    throw "Graphify is not installed. Run: powershell -ExecutionPolicy Bypass -File tools\setup_graphify_argos.ps1"
}

Push-Location $projectRoot
try {
    switch ($Action) {
        "Build" {
            # Deliberately code-only: prevents medical documents/images from entering
            # this engineering graph and avoids external LLM/API transmission.
            & $graphifyExe extract . --code-only --max-workers $MaxWorkers
        }
        "Update" {
            if (-not (Test-Path -LiteralPath $graphPath)) {
                throw "No graph exists yet. Run with -Action Build first."
            }
            & $graphifyExe update .
        }
        "Query" {
            if ([string]::IsNullOrWhiteSpace($Question)) {
                throw "-Question is required for Query."
            }
            & $graphifyExe query $Question --graph $graphPath
        }
        "Explain" {
            if ([string]::IsNullOrWhiteSpace($Question)) {
                throw "-Question is required for Explain."
            }
            & $graphifyExe explain $Question --graph $graphPath
        }
        "Path" {
            if ([string]::IsNullOrWhiteSpace($From) -or [string]::IsNullOrWhiteSpace($To)) {
                throw "-From and -To are required for Path."
            }
            & $graphifyExe path $From $To --graph $graphPath
        }
        "HookCheck" {
            & $graphifyExe hook-check
        }
        "Status" {
            $version = (& $graphifyExe --version).Trim()
            [pscustomobject]@{
                installed = $true
                version = $version
                graph_exists = Test-Path -LiteralPath $graphPath
                graph_path = $graphPath
            } | ConvertTo-Json
        }
    }

    if ($LASTEXITCODE -ne 0) {
        throw "Graphify action '$Action' failed with exit code $LASTEXITCODE."
    }
}
finally {
    Pop-Location
}
