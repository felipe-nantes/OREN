from __future__ import annotations

from pathlib import Path

from dtwin.benchmark.openswisshcc_alignment import _sha256
from dtwin.benchmark.openswisshcc_volumetric_medsiglip import (
    run_volumetric_medsiglip_scores,
)
from tests.test_openswisshcc_volumetric_inference import CONFIGS, _frozen


class FakeScorer:
    calls: list[str] = []

    def __init__(self, _config, **_kwargs):
        pass

    def score_panel(self, panel_path: Path):
        self.calls.append(Path(panel_path).name)
        rows = [{
            "positive_mean_softmax": 0.2,
            "negative_mean_softmax": 0.1,
            "positive_probability": 0.6,
            "positive_pair_normalized": 0.6,
        } for _ in range(11)]
        return {
            "schema": "argos-medsiglip-scores-v2",
            "scoring_method": "softmax_logits_prompt_ensemble",
            "research_only": True,
            "clinical_use_allowed": False,
            "model_id": "fake",
            "panel_sha256": _sha256(panel_path),
            "view_order": [f"view-{i}" for i in range(11)],
            "scores": rows,
            "adjacent_axial_exploratory": {"is_final_decision": False},
            "final_decision": None,
            "requires_human_review": True,
        }


def test_batch_scores_every_panel_without_labels_or_decision(tmp_path: Path):
    root, case_id, review, freeze, _ = _frozen(tmp_path)
    model = tmp_path / "model"
    model.mkdir()
    (model / "model.safetensors").write_bytes(b"fake-weights")
    FakeScorer.calls = []
    out = tmp_path / "scores"
    summary = run_volumetric_medsiglip_scores(
        panel_root=root,
        review_path=review,
        freeze_path=freeze,
        medgemma_config_paths=CONFIGS,
        medsiglip_config_path=Path("configs/medsiglip_liver_volumetric_mimic_aware.yaml"),
        local_model_path=model,
        output_root=out,
        expected_case_count=1,
        device="cpu",
        scorer_factory=FakeScorer,
    )
    assert summary["status"] == "complete"
    assert summary["panel_image_count"] == 2
    assert summary["ground_truth_read"] is False
    assert summary["metrics_calculated"] is False
    assert summary["final_decision"] is None
    assert FakeScorer.calls == ["panel_001.png", "panel_002.png"]
    assert (out / case_id / "medsiglip_panel_scores.json").is_file()
