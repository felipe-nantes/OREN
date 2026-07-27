from __future__ import annotations

import json
from pathlib import Path

from PIL import Image

from dtwin.benchmark import liverhccseg_v21_signals as module


def _context(tmp_path: Path):
    panel_root = tmp_path / "panels"
    cases = []
    for index in range(2):
        case_id = f"anon-public-{index}"
        panel = panel_root / case_id / "panel.png"
        panel.parent.mkdir(parents=True)
        Image.new("RGB", (64, 64), "black").save(panel)
        cases.append({"case_id": case_id, "panel": f"{case_id}/panel.png", "panel_sha256": module._sha256(panel)})
    return panel_root, {
        "cohort": {"cases": cases}, "case_ids": [row["case_id"] for row in cases],
        "review_signature": "r" * 64,
        "medgemma_config": {"prompt": {"template": "score only"}},
    }


class _MedGemma:
    model_id = "google/medgemma-1.5-4b-it"
    model_version = "MedGemma 1.5 4B"

    def score_panel(self, panel_path, prompt):
        assert prompt == "score only"
        return {"choice_probabilities": {"POSITIVA": 0.2, "NEGATIVA": 0.5, "INCONCLUSIVA": 0.3}}


class _MedSigLIP:
    def score_panel(self, panel_path):
        scores = [{"positive_probability": 0.2}] * 10 + [{"positive_probability": 0.6}]
        return {
            "schema": "argos-medsiglip-scores-v2", "panel_sha256": module._sha256(panel_path),
            "scores": scores, "view_order": [f"axial_{i}" for i in range(9)] + ["coronal", "sagittal"],
            "final_decision": None, "research_only": True, "clinical_use_allowed": False,
        }


def test_medgemma_stage_persists_uncertainty_margin_without_decision(tmp_path: Path):
    panels, context = _context(tmp_path)
    result = module.run_v21_medgemma_scores(
        context=context, panel_root=panels, output_root=tmp_path / "mg", scorer=_MedGemma()
    )
    assert result["case_count"] == 2
    rows = [json.loads(line) for line in (tmp_path / "mg/scores.jsonl").read_text().splitlines()]
    assert rows[0]["raw_signal"] == -0.2
    assert rows[0]["final_decision"] is None
    assert rows[0]["ground_truth_read"] is False


def test_medsiglip_stage_persists_inverse_sagittal_without_decision(tmp_path: Path):
    panels, context = _context(tmp_path)
    result = module.run_v21_medsiglip_scores(
        context=context, panel_root=panels, output_root=tmp_path / "ms", scorer=_MedSigLIP()
    )
    assert result["case_count"] == 2
    rows = [json.loads(line) for line in (tmp_path / "ms/scores.jsonl").read_text().splitlines()]
    assert rows[0]["raw_signal"] == -0.6
    assert rows[0]["final_decision"] is None


def test_medgemma_stage_rejects_non_normalized_probabilities(tmp_path: Path):
    class Bad(_MedGemma):
        def score_panel(self, panel_path, prompt):
            return {"choice_probabilities": {"POSITIVA": 0.5, "NEGATIVA": 0.5, "INCONCLUSIVA": 0.5}}
    panels, context = _context(tmp_path)
    import pytest
    from dtwin.core import PipelineError
    with pytest.raises(PipelineError, match="somam 1"):
        module.run_v21_medgemma_scores(
            context=context, panel_root=panels, output_root=tmp_path / "bad", scorer=Bad()
        )
    assert not (tmp_path / "bad").exists()


def test_assemble_builds_exact_three_signals_and_time_gate(tmp_path: Path):
    panels, context = _context(tmp_path)
    context.update(
        protocol_case_count=3,
        technical_failure_case_count=1,
        technical_failure_case_ids=["anon-lld-technical-failure"],
    )
    module.run_v21_medgemma_scores(
        context=context, panel_root=panels, output_root=tmp_path / "mg", scorer=_MedGemma()
    )
    module.run_v21_medsiglip_scores(
        context=context, panel_root=panels, output_root=tmp_path / "ms", scorer=_MedSigLIP()
    )
    localizer = tmp_path / "localizer"
    localizer.mkdir()
    for index, case_id in enumerate(context["case_ids"]):
        case = localizer / case_id
        case.mkdir()
        manifest = {
            "schema": module.LOCALIZER_CASE_SCHEMA, "case_id": case_id,
            "features": {"total_candidate_volume_mm3": 0.0 if index == 0 else 99.0},
            "elapsed_seconds": 20.0, "ground_truth_lesion_mask_used": False,
            "ground_truth_read": False,
        }
        (case / "localizer_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    summary = {
        "schema": module.LOCALIZER_RUN_SCHEMA, "status": "complete_scores_only_no_decision",
        "case_ids": context["case_ids"], "selection_signature": context["review_signature"],
        "ground_truth_lesion_mask_used": False, "ground_truth_read": False,
    }
    (localizer / "summary.json").write_text(json.dumps(summary), encoding="utf-8")
    result = module.assemble_v21_raw_signals(
        context=context, medgemma_root=tmp_path / "mg", medsiglip_root=tmp_path / "ms",
        localizer_root=localizer, output_dir=tmp_path / "raw",
    )
    assert result["all_time_gates_180_seconds_passed"] is True
    assert result["protocol_case_count"] == 3
    assert result["technical_failure_case_count"] == 1
    assert result["technical_failures_count_as_primary_metric_errors"] is True
    rows = [json.loads(line) for line in (tmp_path / "raw/raw_signals.jsonl").read_text().splitlines()]
    assert list(rows[0]["signals"]) == [
        "localizer_v10_log_volume", "medgemma_v4_uncertainty_margin", "medsiglip_v5_inverse_sagittal"
    ]
    assert rows[0]["signals"]["localizer_v10_log_volume"] == 0.0
    assert rows[1]["signals"]["localizer_v10_log_volume"] > 4.6
    assert rows[0]["ground_truth_read"] is False
