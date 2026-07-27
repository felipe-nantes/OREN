from pathlib import Path

import yaml


def test_phase13_verification_config_pins_phase5() -> None:
    config = yaml.safe_load(
        Path("configs/training/phase13_verification_v1.yaml").read_text(
            encoding="utf-8"
        )
    )
    assert len(config["phase5_prediction_freeze_sha256"]) == 64
    assert len(config["phase5_evaluation_sha256"]) == 64
    assert config["expected_case_count"] == 467
    assert config["lesion_masks_read"] == 0
