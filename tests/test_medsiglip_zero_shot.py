
import numpy as np
import pytest
from PIL import Image, PngImagePlugin

from dtwin.core import PipelineError
from dtwin.medsiglip_zero_shot import (
    adjacent_axial_evidence,
    extract_panel_views,
    load_medsiglip_config,
    normalize_prompt_ensemble_scores,
)


def test_versioned_config_is_research_only_and_decision_disabled():
    config = load_medsiglip_config("configs/medsiglip_liver_zero_shot.yaml")
    assert config.model_id == "google/medsiglip-448"
    assert len(config.positive_prompts) == len(config.negative_prompts) == 3
    assert config.decision_enabled is False


def test_extracts_nine_axial_and_two_orthogonal_tiles(tmp_path):
    panel = Image.new("RGB", (400, 300))
    for index in range(12):
        color = (index, index, index)
        tile = Image.new("RGB", (100, 100), color)
        panel.paste(tile, ((index % 4) * 100, (index // 4) * 100))
    path = tmp_path / "panel.png"
    panel.save(path)
    views = extract_panel_views(path)
    assert len(views.axial) == 9
    assert views.axial[0].getpixel((50, 50)) == (0, 0, 0)
    assert views.axial[8].getpixel((50, 50)) == (10, 10, 10)
    assert views.coronal.getpixel((50, 50)) == (3, 3, 3)
    assert views.sagittal.getpixel((50, 50)) == (7, 7, 7)


def test_panel_with_png_metadata_is_rejected(tmp_path):
    path = tmp_path / "metadata.png"
    info = PngImagePlugin.PngInfo()
    info.add_text("PatientName", "must-not-pass")
    Image.new("RGB", (400, 300)).save(path, pnginfo=info)
    with pytest.raises(PipelineError, match="metadados"):
        extract_panel_views(path)


def test_prompt_ensemble_scores_use_softmax_probability_mass():
    raw_logits = np.log(np.array([[0.2, 0.2, 0.2, 0.1, 0.1, 0.2]]))
    result = normalize_prompt_ensemble_scores(raw_logits, positive_prompt_count=3)
    assert result == [
        {
            "positive_mean_softmax": 0.2,
            "negative_mean_softmax": 0.13333333,
            "positive_probability": 0.6,
            "positive_pair_normalized": 0.6,
        }
    ]


def test_prompt_ensemble_softmax_is_invariant_to_logit_offset():
    raw_logits = np.array([[2.0, 1.0, 0.0, -1.0, -2.0, -3.0]])
    original = normalize_prompt_ensemble_scores(raw_logits, positive_prompt_count=3)
    shifted = normalize_prompt_ensemble_scores(raw_logits + 1000.0, positive_prompt_count=3)
    assert original == shifted


def test_prompt_ensemble_rejects_non_finite_logits():
    with pytest.raises(PipelineError, match="não finitos"):
        normalize_prompt_ensemble_scores(
            np.array([[0.0, 0.0, np.nan, 0.0, 0.0, 0.0]]),
            positive_prompt_count=3,
        )


def test_adjacent_evidence_requires_consecutive_tiles_and_is_not_decision():
    values = [0.7, 0.2, 0.8, 0.9, 0.1, 0.8, 0.1, 0.8, 0.1, 0.2, 0.2]
    scores = [{"positive_pair_normalized": value} for value in values]
    result = adjacent_axial_evidence(scores, threshold=0.5, minimum_adjacent=2)
    assert result["longest_adjacent_run"] == 2
    assert result["exploratory_evidence_present"] is True
    assert result["is_final_decision"] is False


def test_invalid_score_shape_is_rejected():
    with pytest.raises(PipelineError, match="ensemble"):
        normalize_prompt_ensemble_scores(np.ones((2, 5)), positive_prompt_count=3)
