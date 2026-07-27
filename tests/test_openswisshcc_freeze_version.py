import hashlib
import json
from pathlib import Path

from dtwin.benchmark.openswisshcc_freeze import create_experiment_freeze


MULTI = Path("configs/medgemma_local_4b_multiphase_fast_pathology.yaml")
FALLBACK = Path("configs/medgemma_local_4b_venous_review_fallback_pathology.yaml")


def test_freeze_persists_explicit_experiment_version(tmp_path):
    root = tmp_path / "panels"
    case = root / "anon-version-test"
    case.mkdir(parents=True)
    panel = case / "panel.png"
    panel.write_bytes(b"panel")
    digest = hashlib.sha256(panel.read_bytes()).hexdigest()
    (case / "candidate_manifest.json").write_text(
        json.dumps(
            {
                "case_id": case.name,
                "candidate_signature": "candidate-signature",
                "candidate_version": "candidate-v1",
                "panel_filename": panel.name,
                "panel_sha256": digest,
                "panel_bytes": panel.stat().st_size,
                "config_sha256": hashlib.sha256(MULTI.read_bytes()).hexdigest(),
                "research_only": True,
                "clinical_use_allowed": False,
            }
        ),
        encoding="utf-8",
    )
    result = create_experiment_freeze(
        panel_root=root,
        multiphase_config=MULTI,
        fallback_config=FALLBACK,
        output_path=tmp_path / "freeze.json",
        expected_case_count=1,
        experiment_version="custom-development-v2",
    )
    assert result["experiment_version"] == "custom-development-v2"
    assert result["ground_truth_read"] is False
