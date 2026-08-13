[CmdletBinding()]
param(
    [string]$EnvFile = ".env.docker",
    [switch]$SkipGpu,
    [switch]$SkipMedGemma,
    [switch]$SkipGraphify
)

$ErrorActionPreference = "Stop"
$repo = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $repo
$dockerBin = "C:\Program Files\Docker\Docker\resources\bin"
if (-not (Get-Command docker -ErrorAction SilentlyContinue) -and (Test-Path $dockerBin)) {
    $env:PATH = "$dockerBin;$env:PATH"
}
$resultDir = Join-Path $repo "artifacts\docker-validation"
New-Item -ItemType Directory -Force -Path $resultDir | Out-Null
$results = [ordered]@{
    schema = "argos-docker-runtime-verification-v1"
    generated_at_utc = [DateTime]::UtcNow.ToString("o")
    checks = [ordered]@{}
}

function Check([string]$Name, [scriptblock]$Action) {
    try {
        $value = & $Action
        $script:results.checks[$Name] = @{ passed = $true; detail = ($value | Out-String).Trim() }
        Write-Host "PASS $Name" -ForegroundColor Green
    } catch {
        $script:results.checks[$Name] = @{ passed = $false; detail = $_.Exception.Message }
        Write-Host "FAIL $Name - $($_.Exception.Message)" -ForegroundColor Red
    }
}

Check "compose_config" {
    docker compose --env-file $EnvFile config --quiet
    if ($LASTEXITCODE -ne 0) { throw "compose config failed" }
    "valid"
}
Check "containers_healthy" {
    $json = docker compose --env-file $EnvFile ps --format json | ConvertFrom-Json
    $required = @("argos", "proxy", "neo4j")
    foreach ($name in $required) {
        $item = @($json) | Where-Object Service -eq $name
        if (-not $item -or $item.State -ne "running") { throw "$name is not running" }
        if ($item.Health -and $item.Health -ne "healthy") { throw "$name health=$($item.Health)" }
    }
    ($json | ConvertTo-Json -Depth 5)
}
Check "desktop_http" {
    $body = & curl.exe -sS --max-time 15 -w "`n%{http_code}" "http://127.0.0.1:8080/api/health"
    $status = $body[-1]
    if ($status -ne "200") { throw "HTTP $status" }
    ($body[0..($body.Count - 2)] -join "`n")
}
Check "quest_https" {
    $response = & curl.exe -k -sS -o NUL -w "%{http_code}" "https://127.0.0.1:8443/api/health"
    if ($response -ne "200") { throw "HTTPS $response" }
    "HTTPS 200"
}
Check "quest_https_lan" {
    $lanIp = Get-NetIPAddress -AddressFamily IPv4 -ErrorAction Stop |
        Where-Object {
            $_.AddressState -eq "Preferred" -and
            $_.IPAddress -notlike "127.*" -and
            $_.IPAddress -notlike "169.254.*" -and
            $_.InterfaceAlias -notlike "vEthernet*"
        } |
        Select-Object -First 1 -ExpandProperty IPAddress
    if (-not $lanIp) { throw "No physical LAN IPv4 address found" }
    $response = & curl.exe -k -sS --max-time 15 -o NUL -w "%{http_code}" `
        "https://${lanIp}:8443/api/health"
    if ($response -ne "200") { throw "LAN HTTPS $response at $lanIp" }
    "https://${lanIp}:8443 -> 200"
}
Check "viewer_static" {
    $temporary = Join-Path $env:TEMP "argos-docker-viewer-$PID.html"
    try {
        $status = & curl.exe -sS --max-time 15 -o $temporary -w "%{http_code}" `
            "http://127.0.0.1:8080/viewer/index.html"
        if ($status -ne "200" -or (Get-Content -Raw $temporary) -notmatch "OREN") {
            throw "viewer unavailable (HTTP $status)"
        }
    } finally {
        Remove-Item $temporary -Force -ErrorAction SilentlyContinue
    }
    "viewer HTML served"
}
Check "segmentation_capability" {
    $capability = Invoke-RestMethod "http://127.0.0.1:8080/api/segmentation-visualization" -TimeoutSec 15
    if (-not $capability.available) { throw "MRSegmentator capability unavailable" }
    ($capability | ConvertTo-Json -Compress)
}
Check "runtime_non_root" {
    $identity = docker compose --env-file $EnvFile exec -T argos python -c `
        "import os,pwd; print(os.getuid()); print(pwd.getpwuid(os.getuid()).pw_name)"
    if ($LASTEXITCODE -ne 0 -or $identity[0] -eq "0" -or $identity[1] -ne "argos") {
        throw "ARGOS runtime is not the non-root argos user: $($identity -join ',')"
    }
    ($identity -join " / ")
}
Check "offline_model_policy" {
    $values = docker compose --env-file $EnvFile exec -T argos python -c `
        "import os; print(os.environ.get('HF_HUB_OFFLINE')); print(os.environ.get('TRANSFORMERS_OFFLINE'))"
    if ($LASTEXITCODE -ne 0 -or $values[0] -ne "1" -or $values[1] -ne "1") {
        throw "Offline model policy is not active"
    }
    "HF_HUB_OFFLINE=1; TRANSFORMERS_OFFLINE=1"
}
Check "volume_permissions" {
    $containerId = docker compose --env-file $EnvFile ps -q argos
    $inspect = docker inspect $containerId | ConvertFrom-Json
    $mounts = @($inspect[0].Mounts)
    $cases = $mounts | Where-Object Destination -eq "/opt/argos/casos"
    $totalseg = $mounts | Where-Object Destination -eq "/home/argos/.totalsegmentator"
    $mrseg = $mounts | Where-Object Destination -eq "/home/argos/.mrsegmentator"
    $hf = $mounts | Where-Object Destination -eq "/home/argos/.cache/huggingface/hub"
    if (-not $cases -or $cases.RW -ne $true) { throw "Cases volume is not RW" }
    foreach ($mount in @($totalseg, $mrseg, $hf)) {
        if (-not $mount -or $mount.RW -ne $false) {
            throw "A model-weights volume is not read-only"
        }
    }
    "cases=rw; model_weights=ro"
}
Check "image_excludes_medical_data" {
    $listing = docker run --rm --entrypoint python argos-runtime:local -c `
        "from pathlib import Path; root=Path('/opt/argos'); forbidden=['casos','data','datasets','dicom','dicoms','artifacts','experiments']; found=[str(p) for name in forbidden if (root/name).exists() for p in (root/name).rglob('*') if p.is_file()]; print(','.join(found)); raise SystemExit(bool(found))"
    if ($LASTEXITCODE -ne 0) { throw "Medical/generated files found in image: $listing" }
    "no medical/generated files in image layer"
}
Check "neo4j" {
    docker compose --env-file $EnvFile exec -T neo4j cypher-shell `
        -u neo4j -p ((Get-Content $EnvFile | Where-Object { $_ -like 'NEO4J_PASSWORD=*' }) -replace '^NEO4J_PASSWORD=', '') `
        "RETURN 1 AS ok;"
    if ($LASTEXITCODE -ne 0) { throw "Neo4j query failed" }
    "Cypher RETURN 1"
}
if (-not $SkipGpu) {
    Check "container_gpu" {
        docker compose --env-file $EnvFile exec -T argos python -c `
            "import torch; assert torch.cuda.is_available(); print(torch.cuda.get_device_name(0)); print(torch.cuda.get_device_properties(0).total_memory)"
        if ($LASTEXITCODE -ne 0) { throw "CUDA unavailable in ARGOS container" }
    }
}
if (-not $SkipMedGemma) {
    Check "medgemma_host" {
        $health = Invoke-RestMethod "http://127.0.0.1:8001/health" -TimeoutSec 15
        if ($health.status -ne "ready" -or -not $health.model_loaded) { throw "MedGemma not ready" }
        ($health | ConvertTo-Json -Compress)
    }
    Check "medgemma_from_container" {
        docker compose --env-file $EnvFile exec -T argos python -c `
            "import urllib.request; print(urllib.request.urlopen('http://host.docker.internal:8001/health',timeout=10).read().decode())"
        if ($LASTEXITCODE -ne 0) { throw "host gateway unreachable from container" }
    }
}
if (-not $SkipGraphify) {
    Check "graphify_container" {
        docker compose --env-file $EnvFile --profile tools run --rm graphify --version
        if ($LASTEXITCODE -ne 0) { throw "Graphify container failed" }
    }
}

$failed = @($results.checks.GetEnumerator() | Where-Object { -not $_.Value.passed })
$results["passed"] = $failed.Count -eq 0
$results["failed_count"] = $failed.Count
$resultPath = Join-Path $resultDir "runtime-verification.json"
[IO.File]::WriteAllText(
    $resultPath,
    ($results | ConvertTo-Json -Depth 8),
    [Text.UTF8Encoding]::new($false)
)
Write-Host "Verification report: $resultPath"
if ($failed.Count -gt 0) { exit 1 }
