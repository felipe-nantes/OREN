[CmdletBinding()]
param(
    [string]$Output,
    [switch]$IncludeAmd64Images,
    [switch]$IncludeMacArm64Image
)

$ErrorActionPreference = "Stop"
$repo = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
if (-not $Output) {
    $stamp = [DateTime]::UtcNow.ToString("yyyyMMdd-HHmmss")
    $Output = Join-Path $repo "artifacts\portable\argos-portable-$stamp"
}
$outputPath = [IO.Path]::GetFullPath($Output)
if (Test-Path -LiteralPath $outputPath) {
    throw "Output already exists; choose a new directory: $outputPath"
}

$source = Join-Path $outputPath "source"
$images = Join-Path $outputPath "images"
New-Item -ItemType Directory -Force -Path $source, $images | Out-Null

$forbiddenParts = @(
    ".git", ".local", ".medgemma", ".venv", ".venv-win", ".venv-mrseg",
    "__pycache__", "casos", "data", "artifacts", "experiments", "benchmarks",
    ".codex-tmp", ".tmp", ".pytest_cache"
)
$forbiddenExtensions = @(
    ".dcm", ".dicom", ".nii", ".nii.gz", ".nrrd", ".mha", ".mhd", ".stl", ".vtk",
    ".vtp", ".glb", ".gltf", ".png", ".jpg", ".jpeg", ".webp", ".pt",
    ".pth", ".safetensors", ".zip", ".7z"
)

function Copy-PortableTree([string]$RelativeRoot) {
    $root = Join-Path $repo $RelativeRoot
    if (-not (Test-Path -LiteralPath $root)) { return }
    Get-ChildItem -LiteralPath $root -Recurse -File | ForEach-Object {
        $relative = $_.FullName.Substring($repo.Length + 1)
        $parts = $relative -split '[\\/]'
        $lower = $_.Name.ToLowerInvariant()
        $forbiddenPart = @($parts | Where-Object { $_ -in $forbiddenParts }).Count -gt 0
        $forbiddenExtension = @($forbiddenExtensions | Where-Object { $lower.EndsWith($_) }).Count -gt 0
        if (-not $forbiddenPart -and -not $forbiddenExtension) {
            $destination = Join-Path $source $relative
            New-Item -ItemType Directory -Force -Path ([IO.Path]::GetDirectoryName($destination)) | Out-Null
            Copy-Item -LiteralPath $_.FullName -Destination $destination
        }
    }
}

foreach ($directory in @("configs", "docker", "dtwin", "profiles", "tests", "tools", "viewer", "webapp")) {
    Copy-PortableTree $directory
}

$rootFiles = @(
    ".dockerignore", ".gitattributes", ".gitignore", ".graphifyignore",
    "AGENTS.md", "compose.yaml", "compose.portable.yaml", "digital_twin.py",
    "INICIAR_OREN.cmd", "INICIAR_OREN_QUEST.cmd", "pyproject.toml", "README.md",
    "requirements.txt", "RUNBOOK_MAC.md", "run_mac.sh", "run_quest_http_win.ps1",
    "run_quest_win.ps1", "run_win.ps1", "setup_quest_https.ps1"
)
foreach ($name in $rootFiles) {
    $path = Join-Path $repo $name
    if (Test-Path -LiteralPath $path) { Copy-Item -LiteralPath $path -Destination (Join-Path $source $name) }
}
foreach ($name in @(
    "229_DOCKER_ARGOS_END_TO_END.md",
    "231_TRANSFERIR_DOCKER_ARGOS_OUTRO_PC.md",
    "232_DOCKER_PORTATIL_MAC_E_OUTROS.md"
)) {
    $path = Join-Path $repo "docs\$name"
    if (Test-Path -LiteralPath $path) {
        New-Item -ItemType Directory -Force -Path (Join-Path $source "docs") | Out-Null
        Copy-Item -LiteralPath $path -Destination (Join-Path $source "docs\$name")
    }
}

$dockerBin = "C:\Program Files\Docker\Docker\resources\bin"
if (-not (Get-Command docker -ErrorAction SilentlyContinue) -and (Test-Path $dockerBin)) {
    $env:PATH = "$dockerBin;$env:PATH"
}
if ($IncludeAmd64Images -or $IncludeMacArm64Image) {
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { throw "Docker CLI not found." }
    docker info *> $null
    if ($LASTEXITCODE -ne 0) { throw "Docker Desktop engine is not running." }
}

if ($IncludeAmd64Images) {
    $required = @("argos-runtime:local", "nginx:1.27-alpine", "neo4j:5.26-community")
    foreach ($image in $required) {
        docker image inspect $image *> $null
        if ($LASTEXITCODE -ne 0) { throw "Required image is absent: $image" }
    }
    $tar = Join-Path $images "argos-runtime-amd64.tar"
    docker image save -o $tar @required
    if ($LASTEXITCODE -ne 0) { throw "Failed to export AMD64 images." }
}

if ($IncludeMacArm64Image) {
    $existingArchitecture = docker image inspect argos-runtime-portable:arm64 `
        --format '{{.Architecture}}' 2>$null | Select-Object -First 1
    if ($LASTEXITCODE -ne 0 -or $existingArchitecture -ne "arm64") {
        docker buildx build --platform linux/arm64 --load `
            -f docker/Dockerfile.argos-portable `
            -t argos-runtime-portable:arm64 .
        if ($LASTEXITCODE -ne 0) { throw "Failed to build the ARM64 portable image." }
    }
    $tar = Join-Path $images "argos-runtime-portable-arm64.tar"
    docker image save -o $tar argos-runtime-portable:arm64
    if ($LASTEXITCODE -ne 0) { throw "Failed to export the ARM64 portable image." }
}

$commit = (git -C $repo rev-parse HEAD 2>$null | Select-Object -First 1)
$dirty = [bool](git -C $repo status --porcelain 2>$null)
$metadata = [ordered]@{
    schema = "argos-portable-bundle-v1"
    generated_at_utc = [DateTime]::UtcNow.ToString("o")
    source_commit = $commit
    source_dirty = $dirty
    contains_medical_data = $false
    contains_model_weights = $false
    contains_private_keys = $false
    amd64_images = [bool]$IncludeAmd64Images
    arm64_runtime_image = [bool]$IncludeMacArm64Image
}
[IO.File]::WriteAllText(
    (Join-Path $outputPath "bundle.json"),
    ($metadata | ConvertTo-Json -Depth 4),
    [Text.UTF8Encoding]::new($false)
)

$zip = Join-Path $outputPath "argos-source.zip"
Compress-Archive -Path (Join-Path $source "*") -DestinationPath $zip -CompressionLevel Optimal

$checksumLines = Get-ChildItem -LiteralPath $outputPath -Recurse -File |
    Where-Object { $_.Name -ne "checksums.sha256" } |
    Sort-Object FullName |
    ForEach-Object {
        $hash = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
        $relative = $_.FullName.Substring($outputPath.Length + 1).Replace("\", "/")
        "$hash  $relative"
    }
[IO.File]::WriteAllLines(
    (Join-Path $outputPath "checksums.sha256"),
    $checksumLines,
    [Text.UTF8Encoding]::new($false)
)

Write-Host "Portable ARGOS bundle created: $outputPath" -ForegroundColor Green
Write-Host "No DICOM, cases, model weights, .env.docker or HTTPS private keys were included."
