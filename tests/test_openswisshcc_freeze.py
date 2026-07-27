import hashlib
import json
from pathlib import Path

import pytest

from dtwin.benchmark.openswisshcc_freeze import (
    create_experiment_freeze,
    verify_experiment_freeze,
)
from dtwin.core import PipelineError


MULTI = Path("configs/medgemma_local_4b_multiphase_fast_pathology.yaml")
FALLBACK = Path("configs/medgemma_local_4b_venous_fallback_pathology.yaml")


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _candidate(root: Path, case_id: str, *, fallback: bool) -> Path:
    case = root / case_id
    case.mkdir(parents=True)
    panel = case / "panel.png"
    panel.write_bytes(case_id.encode())
    config = FALLBACK if fallback else MULTI
    manifest = {
        "case_id": case_id,
        "candidate_signature": f"signature-{case_id}",
        "candidate_version": "fallback-v1" if fallback else "multiphase-v1",
        "panel_filename": panel.name,
        "panel_sha256": _sha(panel),
        "panel_bytes": panel.stat().st_size,
        "config_sha256": _sha(config),
        "research_only": True,
        "clinical_use_allowed": False,
    }
    if fallback:
        manifest["candidate_kind"] = "venous_single_phase_fallback"
    (case / "candidate_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return panel


def test_freeze_binds_effective_configs_and_panel_bytes(tmp_path):
    panels = tmp_path / "panels"
    _candidate(panels, "anon-multi", fallback=False)
    _candidate(panels, "anon-fallback", fallback=True)
    path = tmp_path / "freeze.json"
    result = create_experiment_freeze(
        panel_root=panels,
        multiphase_config=MULTI,
        fallback_config=FALLBACK,
        output_path=path,
        expected_case_count=2,
    )
    assert result["case_count"] == 2
    assert result["ground_truth_read"] is False
    assert set(result["configs"]) == {"multiphase_rgb", "venous_single_phase_fallback"}
    assert all(item["config_effective_sha256"] for item in result["candidates"])
    assert verify_experiment_freeze(
        freeze_path=path,
        panel_root=panels,
        multiphase_config=MULTI,
        fallback_config=FALLBACK,
        expected_case_count=2,
    )["experiment_signature"] == result["experiment_signature"]


def test_freeze_detects_panel_change(tmp_path):
    panels = tmp_path / "panels"
    panel = _candidate(panels, "anon-multi", fallback=False)
    path = tmp_path / "freeze.json"
    create_experiment_freeze(
        panel_root=panels,
        multiphase_config=MULTI,
        fallback_config=FALLBACK,
        output_path=path,
        expected_case_count=1,
    )
    panel.write_bytes(b"changed")
    with pytest.raises(PipelineError, match="Hash do painel"):
        verify_experiment_freeze(
            freeze_path=path,
            panel_root=panels,
            multiphase_config=MULTI,
            fallback_config=FALLBACK,
            expected_case_count=1,
        )


def test_freeze_rejects_tampered_effective_hash(tmp_path):
    panels = tmp_path / "panels"
    _candidate(panels, "anon-multi", fallback=False)
    path = tmp_path / "freeze.json"
    create_experiment_freeze(
        panel_root=panels,
        multiphase_config=MULTI,
        fallback_config=FALLBACK,
        output_path=path,
        expected_case_count=1,
    )
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["configs"]["multiphase_rgb"]["effective_sha256"] = "0" * 64
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(PipelineError, match="Assinatura"):
        verify_experiment_freeze(
            freeze_path=path,
            panel_root=panels,
            multiphase_config=MULTI,
            fallback_config=FALLBACK,
            expected_case_count=1,
        )


def test_freeze_refuses_incomplete_expected_cohort(tmp_path):
    panels = tmp_path / "panels"
    _candidate(panels, "anon-multi", fallback=False)
    with pytest.raises(PipelineError, match="Coorte incompleta"):
        create_experiment_freeze(
            panel_root=panels,
            multiphase_config=MULTI,
            fallback_config=FALLBACK,
            output_path=tmp_path / "freeze.json",
            expected_case_count=2,
        )
