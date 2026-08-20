import hashlib
import json
from pathlib import Path

from dtwin.benchmark.openswisshcc_fallback import REVIEW_FALLBACK_VERSION
from dtwin.benchmark.openswisshcc_freeze import (
    create_experiment_freeze,
    verify_experiment_freeze,
)
from dtwin.benchmark.openswisshcc_inference import _validated_config

MULTI = Path("configs/medgemma_local_4b_multiphase_fast_pathology.yaml")
FALLBACK = Path("configs/medgemma_local_4b_venous_review_fallback_pathology.yaml")
CONTRAST = Path("configs/medgemma_local_4b_venous_review_fallback_high_contrast_pathology.yaml")
EXTRAS = {"venous_single_phase_fallback_high_contrast": CONTRAST}


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _candidate(root, case_id, config, kind="multiphase_rgb"):
    case = root / case_id
    case.mkdir(parents=True)
    panel = case / "panel.png"
    panel.write_bytes(case_id.encode())
    payload = {
        "case_id": case_id,
        "candidate_signature": f"signature-{case_id}",
        "candidate_version": "candidate-v1",
        "candidate_kind": kind,
        "panel_filename": panel.name,
        "panel_sha256": _sha(panel),
        "panel_bytes": panel.stat().st_size,
        "config_sha256": _sha(config),
        "research_only": True,
        "clinical_use_allowed": False,
    }
    (case / "candidate_manifest.json").write_text(json.dumps(payload), encoding="utf-8")


def test_freeze_and_verify_bind_two_fallback_config_variants(tmp_path):
    panels = tmp_path / "panels"
    _candidate(panels, "anon-multi", MULTI)
    _candidate(panels, "anon-fallback", FALLBACK, "venous_single_phase_fallback")
    _candidate(panels, "anon-contrast", CONTRAST, "venous_single_phase_fallback")
    path = tmp_path / "freeze.json"
    frozen = create_experiment_freeze(
        panel_root=panels,
        multiphase_config=MULTI,
        fallback_config=FALLBACK,
        additional_configs=EXTRAS,
        output_path=path,
        expected_case_count=3,
        experiment_version="variant-v3",
    )
    assert set(frozen["configs"]) == {
        "multiphase_rgb",
        "venous_single_phase_fallback",
        "venous_single_phase_fallback_high_contrast",
    }
    assert verify_experiment_freeze(
        freeze_path=path,
        panel_root=panels,
        multiphase_config=MULTI,
        fallback_config=FALLBACK,
        additional_configs=EXTRAS,
        expected_case_count=3,
    )["experiment_signature"] == frozen["experiment_signature"]


def test_case_validator_accepts_review_fallback_version_with_exact_hash():
    candidate = {
        "candidate_kind": "venous_single_phase_fallback",
        "candidate_version": REVIEW_FALLBACK_VERSION,
        "config_sha256": _sha(CONTRAST),
    }
    config, effective_hash = _validated_config(candidate, CONTRAST)
    assert config["panel"]["mode"] == "single_grayscale"
    assert config["panel"]["window_percentile_low"] == 20.0
    assert effective_hash
