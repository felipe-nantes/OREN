from __future__ import annotations

import json
from pathlib import Path

import pytest
from PIL import Image

from dtwin.benchmark import liverhccseg_v21_panels as module
from dtwin.core import PipelineError


def test_validate_config_requires_uniform9_choice_4b(monkeypatch, tmp_path: Path):
    config = {
        "panel": {"mode": "multiphase_fusion", "strategy": "uniform_9", "axial_slices": 9},
        "medgemma": {
            "response_mode": "choice_classification", "model_id": "google/medgemma-1.5-4b-it",
            "model_parameter_scale": "4B", "timeout_seconds": 120, "max_retries": 0,
        },
        "rag": {"enabled": False},
    }
    monkeypatch.setattr(module, "load_screening_config", lambda _: config)
    assert module._validate_config(tmp_path / "config.yaml") == config
    config["panel"]["strategy"] = "volumetric_blocks"
    with pytest.raises(PipelineError, match="uniform_9"):
        module._validate_config(tmp_path / "config.yaml")


def test_case_files_rejects_lesion_filename(tmp_path: Path):
    root = tmp_path.resolve()
    case = root / "anon-public-test"
    case.mkdir()
    bad = case / "lesion_mask.nii.gz"
    bad.write_bytes(b"x")
    manifest = {
        "case_id": "anon-public-test", "lesion_mask_present": False, "pathology_label_present": False,
        "files": [{"role": "t1_arterial", "relative_path": "anon-public-test/lesion_mask.nii.gz", "sha256": module._sha256(bad)}],
    }
    manifest_path = case / "input_manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    record = {"case_id": "anon-public-test", "case_manifest": "anon-public-test/input_manifest.json", "case_manifest_sha256": module._sha256(manifest_path)}
    with pytest.raises(PipelineError, match="lesao"):
        module._case_files(root, record)


def test_gallery_is_label_blind_and_checks_hashes(tmp_path: Path):
    panel_root = tmp_path / "panels"
    case = panel_root / "anon-public-test"
    case.mkdir(parents=True)
    image = case / "panel.png"
    Image.new("RGB", (64, 64), "black").save(image)
    cohort = {
        "schema": module.COHORT_SCHEMA,
        "status": "complete_pending_human_review",
        "ground_truth_read": False,
        "holdout_opened": False,
        "cases": [{"case_id": "anon-public-test", "panel": "anon-public-test/panel.png", "panel_sha256": module._sha256(image)}],
    }
    (panel_root / "cohort_manifest.json").write_text(json.dumps(cohort), encoding="utf-8")
    result = module.build_liverhccseg_uniform9_gallery(panel_root=panel_root, output_dir=tmp_path / "gallery")
    assert result["approved"] is False
    assert result["ground_truth_read"] is False
    text = (tmp_path / "gallery/index.html").read_text(encoding="utf-8")
    assert "Não avalie diagnóstico" in text
    assert "POSITIVE" not in text


def test_gallery_rejects_changed_panel(tmp_path: Path):
    panel_root = tmp_path / "panels"
    case = panel_root / "anon-public-test"
    case.mkdir(parents=True)
    image = case / "panel.png"
    Image.new("RGB", (64, 64), "black").save(image)
    cohort = {
        "schema": module.COHORT_SCHEMA, "status": "complete_pending_human_review",
        "ground_truth_read": False, "holdout_opened": False,
        "cases": [{"case_id": "anon-public-test", "panel": "anon-public-test/panel.png", "panel_sha256": "0" * 64}],
    }
    (panel_root / "cohort_manifest.json").write_text(json.dumps(cohort), encoding="utf-8")
    with pytest.raises(PipelineError, match="adulterado"):
        module.build_liverhccseg_uniform9_gallery(panel_root=panel_root, output_dir=tmp_path / "gallery")

