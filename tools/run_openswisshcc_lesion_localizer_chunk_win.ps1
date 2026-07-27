param(
    [Parameter(Mandatory = $true)]
    [ValidateRange(1, 11)]
    [int]$ChunkNumber,
    [string]$ChunksRoot = "casos/qualification/openswisshcc_v1/calibration/dev_v10_lesion_localizer_full87_chunks"
)

$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Python = Join-Path $Root ".venv-win/Scripts/python.exe"
if (-not (Test-Path -LiteralPath $Python)) {
    throw "Python do ARGOS nao encontrado: $Python"
}

$env:PYTHONDONTWRITEBYTECODE = "1"
$env:PYTHONPATH = $Root
$ChunkName = "chunk_{0:D3}" -f $ChunkNumber

& $Python -B -c "from tools.run_openswisshcc_lesion_localizer_chunk import main; raise SystemExit(main())" `
    --manifest (Join-Path $Root "casos/qualification/openswisshcc_v1/prepared/development_v1/manifests/development_inputs.jsonl") `
    --inputs-root (Join-Path $Root "casos/qualification/openswisshcc_v1/prepared/development_v1/inputs") `
    --selection-plan (Join-Path $Root "casos/qualification/openswisshcc_v1/prepared/development_experiment_v9/chunk_plan.json") `
    --chunk-number $ChunkNumber `
    --out (Join-Path (Join-Path $Root $ChunksRoot) $ChunkName) `
    --expected-source-case-count 88 `
    --expected-primary-case-count 87 `
    --max-localizer-seconds 90

exit $LASTEXITCODE
