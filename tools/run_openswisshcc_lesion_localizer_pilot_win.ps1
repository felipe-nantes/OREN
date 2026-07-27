param(
    [int]$Count = 10,
    [string]$Output = "casos/qualification/openswisshcc_v1/calibration/dev_v10_lesion_localizer_pilot10_blind"
)

$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Python = Join-Path $Root ".venv-win/Scripts/python.exe"

if (-not (Test-Path -LiteralPath $Python)) {
    throw "Python do ARGOS não encontrado: $Python"
}

$env:PYTHONDONTWRITEBYTECODE = "1"
$env:PYTHONPATH = $Root

& $Python -B -c "from tools.run_openswisshcc_lesion_localizer_pilot import main; raise SystemExit(main())" `
    --manifest (Join-Path $Root "casos/qualification/openswisshcc_v1/prepared/development_v1/manifests/development_inputs.jsonl") `
    --inputs-root (Join-Path $Root "casos/qualification/openswisshcc_v1/prepared/development_v1/inputs") `
    --selection-plan (Join-Path $Root "casos/qualification/openswisshcc_v1/prepared/development_experiment_v9/chunk_plan.json") `
    --out (Join-Path $Root $Output) `
    --count $Count `
    --expected-source-case-count 88 `
    --expected-primary-case-count 87 `
    --max-localizer-seconds 90

exit $LASTEXITCODE

