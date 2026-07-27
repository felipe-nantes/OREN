from pathlib import Path

import pytest

from dtwin.core import PipelineError
from dtwin.learning.medsiglip_partial_finetune import (
    aggregate_probabilities,
    load_partial_config,
)


def test_partial_config_is_pinned_and_safe() -> None:
    config = load_partial_config(
        Path("configs/training/medsiglip_partial_finetune_v1.yaml")
    )
    assert config["trainable_last_blocks"] == 1
    assert config["local_files_only"] is True
    assert config["lesion_masks_read"] == 0
    assert config["research_only"] is True
    lora = load_partial_config(Path("configs/training/medsiglip_lora_v1.yaml"))
    assert lora["adapter_mode"] == "lora_qv"
    assert lora["head_initialization"] == "fold_train_logistic"


def test_panel_aggregations_are_deterministic() -> None:
    values = [0.2, 0.8, 0.6]
    assert aggregate_probabilities(values, "mean") == pytest.approx(0.5333333333)
    assert aggregate_probabilities(values, "max") == 0.8
    assert aggregate_probabilities(values, "top2_mean") == pytest.approx(0.7)
    with pytest.raises(PipelineError):
        aggregate_probabilities(values, "unknown")


def test_partial_config_rejects_lesion_mask_access(tmp_path: Path) -> None:
    source = Path("configs/training/medsiglip_partial_finetune_v1.yaml")
    invalid = tmp_path / "invalid.yaml"
    invalid.write_text(
        source.read_text(encoding="utf-8").replace(
            "lesion_masks_read: 0", "lesion_masks_read: 1"
        ),
        encoding="utf-8",
    )
    with pytest.raises(PipelineError, match="Máscara"):
        load_partial_config(invalid)
