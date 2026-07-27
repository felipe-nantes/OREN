from __future__ import annotations

import json
from pathlib import Path

import pytest
from PIL import Image

from dtwin.benchmark import chaos_v21_signals as module
from dtwin.core import PipelineError


def test_context_fails_before_config_or_model_when_review_is_missing(monkeypatch, tmp_path: Path):
    calls = {"config": 0}

    def reject_review(**_kwargs):
        raise PipelineError("Revisao humana CHAOS v21 ausente")

    def config(_path):
        calls["config"] += 1
        return {}

    monkeypatch.setattr(module, "verify_chaos_v21_review", reject_review)
    monkeypatch.setattr(module, "_validate_config", config)
    with pytest.raises(PipelineError, match="Revisao humana"):
        module.verify_chaos_v21_signal_context(
            panel_root=tmp_path / "panels", gallery_root=tmp_path / "gallery",
            review_path=tmp_path / "review.json", prepared_root=tmp_path / "prepared",
            medgemma_config_path=tmp_path / "mg.yaml",
            medsiglip_config_path=tmp_path / "ms.yaml", expected_case_count=20,
        )
    assert calls["config"] == 0


def test_localizer_manifest_uses_t2_spir_without_lesion_or_label(monkeypatch, tmp_path: Path):
    prepared = tmp_path / "prepared"
    case_id = "anon-public-test"
    case = prepared / case_id
    case.mkdir(parents=True)
    paths = {}
    for role in ("t1_in", "t1_out", "t2_spir", "liver_mask"):
        path = case / f"{role}.nii.gz"
        path.write_bytes(role.encode())
        paths[role] = path
    cohort = {"cases": [{"case_id": case_id}]}
    (prepared / "cohort_manifest.json").write_text(json.dumps(cohort), encoding="utf-8")
    context = {"case_ids": [case_id], "review_signature": "r" * 64}
    monkeypatch.setattr(module, "verify_chaos_v21_signal_context", lambda **_kwargs: context)
    monkeypatch.setattr(module, "_case_files", lambda *_args, **_kwargs: ({}, paths))
    out = tmp_path / "localizer_inputs.jsonl"
    result = module.build_chaos_v21_localizer_input_manifest(
        panel_root=tmp_path, gallery_root=tmp_path, review_path=tmp_path,
        prepared_root=prepared, medgemma_config_path=tmp_path,
        medsiglip_config_path=tmp_path, output_path=out, expected_case_count=1,
    )
    row = json.loads(out.read_text(encoding="utf-8"))
    assert result["input_role"] == "t2_spir"
    assert {item["role"] for item in row["files"]} == {"t2_spir", "liver_mask"}
    assert "not T1 venous" in row["localizer_input_semantics"]
    assert row["ground_truth_read"] is False
    assert row["lesion_mask_available"] is False


class _MedGemma:
    model_id = "google/medgemma-1.5-4b-it"
    model_version = "MedGemma 1.5 4B"

    def score_panel(self, _panel_path, _prompt):
        return {"choice_probabilities": {"POSITIVA": 0.2, "NEGATIVA": 0.7, "INCONCLUSIVA": 0.1}}


def test_chaos_context_emits_separate_medgemma_schemas(tmp_path: Path):
    panel_root = tmp_path / "panels"
    panel = panel_root / "anon-public-test" / "panel.png"
    panel.parent.mkdir(parents=True)
    Image.new("RGB", (32, 32), "black").save(panel)
    context = {
        "cohort": {"cases": [{
            "case_id": "anon-public-test", "panel": "anon-public-test/panel.png",
            "panel_sha256": module._sha256(panel),
        }]},
        "case_ids": ["anon-public-test"], "review_signature": "r" * 64,
        "medgemma_config": {"prompt": {"template": "score"}},
        "medgemma_case_schema": module.MEDGEMMA_CASE_SCHEMA,
        "medgemma_run_schema": module.MEDGEMMA_RUN_SCHEMA,
    }
    result = module.run_v21_medgemma_scores(
        context=context, panel_root=panel_root,
        output_root=tmp_path / "scores", scorer=_MedGemma(),
    )
    row = json.loads((tmp_path / "scores/scores.jsonl").read_text())
    assert result["schema"] == module.MEDGEMMA_RUN_SCHEMA
    assert row["schema"] == module.MEDGEMMA_CASE_SCHEMA
    assert row["ground_truth_read"] is False
