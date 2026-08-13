[CmdletBinding()]
param(
    [string]$Output = ".env.docker",
    [switch]$Force
)

$ErrorActionPreference = "Stop"
$repo = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$outputPath = Join-Path $repo $Output

function DockerPath([string]$PathValue) {
    return ([System.IO.Path]::GetFullPath($PathValue)).Replace("\", "/")
}

if ((Test-Path -LiteralPath $outputPath) -and -not $Force) {
    Write-Host "Docker environment already exists: $outputPath"
    exit 0
}

$cases = Join-Path $repo "casos"
$state = Join-Path $env:LOCALAPPDATA "ARGOS\docker-state"
$totalseg = Join-Path $env:USERPROFILE ".totalsegmentator"
$mrsegmentator = Join-Path $env:USERPROFILE ".mrsegmentator"
$hfHub = Join-Path $env:USERPROFILE ".cache\huggingface\hub"
$certs = Join-Path $repo ".local\quest_https"

foreach ($directory in @($cases, $state, "$state\neo4j\data", "$state\neo4j\logs")) {
    New-Item -ItemType Directory -Force -Path $directory | Out-Null
}
foreach ($required in @($totalseg, $mrsegmentator, $hfHub, $certs)) {
    if (-not (Test-Path -LiteralPath $required)) {
        throw "Required external volume does not exist: $required"
    }
}

$passwordBytes = [byte[]]::new(30)
$rng = [Security.Cryptography.RandomNumberGenerator]::Create()
try {
    $rng.GetBytes($passwordBytes)
}
finally {
    $rng.Dispose()
}
$password = [Convert]::ToBase64String($passwordBytes).Replace("/", "A").Replace("+", "B").TrimEnd("=")

$content = @"
ARGOS_CASES_DIR=$(DockerPath $cases)
ARGOS_DOCKER_STATE_DIR=$(DockerPath $state)
TOTALSEG_HOME_DIR=$(DockerPath $totalseg)
MRSEGMENTATOR_HOME_DIR=$(DockerPath $mrsegmentator)
HF_HUB_DIR=$(DockerPath $hfHub)
QUEST_CERT_DIR=$(DockerPath $certs)
NEO4J_PASSWORD=$password
MEDGEMMA_BASE_URL=http://host.docker.internal:8001
"@

[IO.File]::WriteAllText($outputPath, $content, [Text.UTF8Encoding]::new($false))
Write-Host "Docker environment created: $outputPath"
Write-Host "Medical data and model weights remain external bind mounts."
