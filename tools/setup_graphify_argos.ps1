[CmdletBinding()]
param(
    [string]$RepositoryUrl = "https://github.com/Graphify-Labs/graphify.git",
    [string]$Commit = "7fe58b0b0f3873be9a21c30106b8b8527c353aa6",
    [switch]$SkipCodexInstall
)

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$sourceDir = Join-Path $projectRoot ".codex-tmp\graphify-source"
$venvDir = Join-Path $projectRoot ".local\graphify-venv"
$pythonExe = Join-Path $venvDir "Scripts\python.exe"
$graphifyExe = Join-Path $venvDir "Scripts\graphify.exe"

function Invoke-Checked {
    param([Parameter(Mandatory = $true)][scriptblock]$Command)
    & $Command
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed with exit code $LASTEXITCODE."
    }
}

Push-Location $projectRoot
try {
    if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
        throw "Git is required to install Graphify."
    }

    if (-not (Test-Path -LiteralPath (Join-Path $sourceDir ".git"))) {
        New-Item -ItemType Directory -Force -Path (Split-Path $sourceDir) | Out-Null
        Invoke-Checked { git clone --filter=blob:none --no-checkout $RepositoryUrl $sourceDir }
    }

    Push-Location $sourceDir
    try {
        Invoke-Checked { git fetch --depth 1 origin $Commit }
        Invoke-Checked { git checkout --detach --force $Commit }
        $installedCommit = (git rev-parse HEAD).Trim()
        if ($installedCommit -ne $Commit) {
            throw "Graphify checkout mismatch: expected $Commit, got $installedCommit."
        }
    }
    finally {
        Pop-Location
    }

    if (-not (Test-Path -LiteralPath $pythonExe)) {
        Invoke-Checked { py -3 -m venv $venvDir }
    }

    Invoke-Checked { & $pythonExe -m pip install --upgrade pip }
    Invoke-Checked { & $pythonExe -m pip install "$sourceDir[neo4j]" }

    if (-not $SkipCodexInstall) {
        Invoke-Checked { & $graphifyExe install --project --platform codex }
        $agentsFile = Join-Path $projectRoot "AGENTS.md"
        $runtimeMarker = "### ARGOS runtime"
        if ((Test-Path -LiteralPath $agentsFile) -and
            -not (Select-String -LiteralPath $agentsFile -SimpleMatch $runtimeMarker -Quiet)) {
            Add-Content -LiteralPath $agentsFile -Encoding utf8 -Value @"

### ARGOS runtime

Graphify is installed in an isolated environment. Use
``tools/graphify_argos.ps1`` for Build, Update, Query, Explain and Path actions.
The graph is engineering-only and must never ingest medical datasets, DICOM,
NIfTI, lesion masks, case outputs or protected benchmark labels.
"@
        }
    }

    $version = (& $graphifyExe --version).Trim()
    Write-Host "Graphify ready: $version"
    Write-Host "Pinned commit: $Commit"
    Write-Host "Executable: $graphifyExe"
}
finally {
    Pop-Location
}
