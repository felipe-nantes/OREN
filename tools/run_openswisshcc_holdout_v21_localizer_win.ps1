param(
    [string]$PreparedRoot = "casos/qualification/openswisshcc_v1/prepared",
    [string]$WeightsDir = "$HOME/.totalsegmentator/nnunet/results"
)

$ErrorActionPreference = "Stop"
$python = (Resolve-Path ".venv-win/Scripts/python.exe").Path
$runtime = Join-Path $PreparedRoot "holdout_v21_totalseg_runtime"
$logs = Join-Path $PreparedRoot "holdout_v21_logs"
New-Item -ItemType Directory -Force -Path $logs | Out-Null

$arguments = @(
    "tools/run_openswisshcc_holdout_v21_isolated_localizer.py",
    "--panels", (Join-Path $PreparedRoot "holdout_uniform9_panels_v21"),
    "--gallery", (Join-Path $PreparedRoot "holdout_review_gallery_v21"),
    "--review", (Join-Path $PreparedRoot "holdout_uniform9_review_v21.json"),
    "--prepared", (Join-Path $PreparedRoot "holdout_blind_v1"),
    "--prepared-audit", "casos/qualification/openswisshcc_v1/audits/holdout_blind_v1_audit.json",
    "--multiphase-config", "configs/medgemma_local_4b_multiphase_uniform9_choice_v21.yaml",
    "--fallback-config", "configs/medgemma_local_4b_venous_uniform9_choice_v21.yaml",
    "--medsiglip-config", "configs/medsiglip_liver_zero_shot.yaml",
    "--calibrator", (Join-Path $PreparedRoot "public_independent_freezes_v21/v11_external_calibrator.json"),
    "--manifest", (Join-Path $PreparedRoot "holdout_v21_localizer_inputs.jsonl"),
    "--out", (Join-Path $PreparedRoot "holdout_v21_localizer"),
    "--totalseg-home", $runtime,
    "--totalseg-weights", $WeightsDir
)

& $python @arguments `
    1> (Join-Path $logs "localizer_isolated_stdout.log") `
    2> (Join-Path $logs "localizer_isolated_stderr.log")
exit $LASTEXITCODE
