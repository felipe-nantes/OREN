from __future__ import annotations

import json
from pathlib import Path

import pytest
from PIL import Image

from dtwin.benchmark import chaos_v21_panels as module
from dtwin.core import PipelineError


def _valid_config() -> dict:
    return {
        "panel": {
            "mode": "multiphase_fusion", "strategy": "uniform_9", "axial_slices": 9,
            "fusion": {"channel_map": {"red": "t1in", "green": "t1out", "blue": "t2spir"}},
        },
        "medgemma": {
            "response_mode": "choice_classification",
            "model_id": "google/medgemma-1.5-4b-it", "model_parameter_scale": "4B",
            "timeout_seconds": 120, "max_retries": 0,
        },
        "rag": {"enabled": False},
        "prompt": {"template": "Estas imagens nao sao fases dinamicas."},
    }


def test_validate_config_requires_actual_chaos_sequence_semantics(monkeypatch, tmp_path: Path):
    config = _valid_config()
    monkeypatch.setattr(module, "load_screening_config", lambda _: config)
    assert module._validate_config(tmp_path / "config.yaml") == config
    config["panel"]["fusion"]["channel_map"]["blue"] = "del"
    with pytest.raises(PipelineError, match="semantica T1/T2"):
        module._validate_config(tmp_path / "config.yaml")


def test_case_files_requires_ground_truth_class_to_remain_unread(tmp_path: Path):
    root = tmp_path.resolve()
    case = root / "anon-public-test"
    case.mkdir()
    files = []
    for role in ("t1_in", "t1_out", "t2_spir", "liver_mask"):
        path = case / f"{role}.nii.gz"
        path.write_bytes(role.encode())
        files.append({
            "role": role, "relative_path": f"anon-public-test/{path.name}",
            "sha256": module._sha256(path),
        })
    manifest = {
        "case_id": "anon-public-test", "lesion_mask_present": False,
        "pathology_label_present": False, "ground_truth_class_read": True,
        "files": files,
    }
    manifest_path = case / "input_manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    record = {
        "case_id": "anon-public-test",
        "case_manifest": "anon-public-test/input_manifest.json",
        "case_manifest_sha256": module._sha256(manifest_path),
    }
    with pytest.raises(PipelineError, match="isolamento"):
        module._case_files(root, record)


def _panel_cohort(panel_root: Path, *, expected_hash: str | None = None) -> Path:
    case = panel_root / "anon-public-test"
    case.mkdir(parents=True)
    image = case / "panel.png"
    Image.new("RGB", (64, 64), "black").save(image)
    cohort = {
        "schema": module.COHORT_SCHEMA,
        "status": "complete_pending_human_review",
        "ground_truth_read": False, "holdout_opened": False,
        "combined_primary_metric_allowed": False,
        "cases": [{
            "case_id": "anon-public-test", "panel": "anon-public-test/panel.png",
            "panel_sha256": expected_hash or module._sha256(image),
        }],
    }
    (panel_root / "cohort_manifest.json").write_text(json.dumps(cohort), encoding="utf-8")
    return image


def test_gallery_is_blind_and_states_non_dynamic_rgb_semantics(tmp_path: Path):
    panel_root = tmp_path / "panels"
    _panel_cohort(panel_root)
    result = module.build_chaos_uniform9_gallery(
        panel_root=panel_root, output_dir=tmp_path / "gallery"
    )
    assert result["approved"] is False
    assert result["ground_truth_read"] is False
    assert result["combined_primary_metric_allowed"] is False
    text = (tmp_path / "gallery/index.html").read_text(encoding="utf-8")
    assert "Não avalie diagnóstico" in text
    assert "Não são fases dinâmicas" in text
    assert "POSITIVE" not in text and "NEGATIVE" not in text


def test_gallery_rejects_changed_panel(tmp_path: Path):
    panel_root = tmp_path / "panels"
    _panel_cohort(panel_root, expected_hash="0" * 64)
    with pytest.raises(PipelineError, match="adulterado"):
        module.build_chaos_uniform9_gallery(
            panel_root=panel_root, output_dir=tmp_path / "gallery"
        )
