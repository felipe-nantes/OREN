from __future__ import annotations

from pathlib import Path

import pytest

from dtwin.benchmark.openswisshcc_alignment import _sha256
from dtwin.benchmark.openswisshcc_volumetric_pairwise import (
    PAIRWISE_SCHEMA,
    PAIR_BANK,
    _axial_indices,
    run_volumetric_pairwise_scores,
)
from dtwin.core import PipelineError
from tests.test_openswisshcc_volumetric_inference import CONFIGS, _frozen


class FakePairwiseScorer:
    model_id = "google/medgemma-1.5-4b-it"
    model_version = "test"

    def __init__(self):
        self.calls: list[str] = []

    def score_panel(self, panel_path: Path, prompt: str, pairs):
        self.calls.append(panel_path.name)
        assert "ground truth" in prompt
        assert pairs == PAIR_BANK
        return {
            "schema": PAIRWISE_SCHEMA,
            "panel_sha256": _sha256(panel_path),
            "pairs": [
                {"pair_id": pair["pair_id"], "positive_probability": 0.4}
                for pair in pairs
            ],
            "final_decision": None,
            "ground_truth_read": False,
        }


def test_pairwise_scores_every_panel_without_decision_or_labels(tmp_path: Path):
    root, case_id, review, freeze, _ = _frozen(tmp_path)
    out = tmp_path / "pairwise"
    scorer = FakePairwiseScorer()
    summary = run_volumetric_pairwise_scores(
        panel_root=root,
        review_path=review,
        freeze_path=freeze,
        config_paths=CONFIGS,
        output_root=out,
        scorer=scorer,
        expected_case_count=1,
    )
    assert summary["status"] == "complete"
    assert summary["panel_image_count"] == 2
    assert summary["ground_truth_read"] is False
    assert summary["metrics_calculated"] is False
    assert summary["final_decision"] is None
    assert scorer.calls == ["panel_001.png", "panel_002.png"]
    assert (out / case_id / "pairwise_manifest.json").is_file()
    assert (out / case_id / "pairwise_panel_scores.json").is_file()


def test_axial_indices_can_derive_legacy_contiguous_interval():
    assert _axial_indices({"axial_interval": [7, 9]}) == [7, 8, 9]


@pytest.mark.parametrize(
    "source",
    [
        {},
        {"axial_interval": [9, 7]},
        {"axial_interval": [1, 10]},
        {"axial_indices": [1, 1]},
    ],
)
def test_axial_indices_fail_closed(source):
    with pytest.raises(PipelineError):
        _axial_indices(source)
