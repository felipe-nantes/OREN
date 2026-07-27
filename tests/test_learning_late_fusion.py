from __future__ import annotations

import pytest
import yaml

from dtwin.core import PipelineError
from dtwin.learning.late_fusion import _metrics, load_fusion_config


def test_fusion_config_requires_weights_sum_one(tmp_path):
    path = tmp_path / "fusion.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "schema": "argos-hybrid-late-fusion-config-v1",
                "weights": {"v23": 0.8, "medsiglip_phase5": 0.3},
                "weight_selection": "fixed_before_fusion_evaluation",
                "technical_failures_count_as_errors": True,
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(PipelineError, match="somar um"):
        load_fusion_config(path)


def test_metrics_count_failures_as_errors():
    rows = [
        {"case_id": "p", "prediction": "POSITIVE", "technical_failure": False},
        {"case_id": "n", "prediction": "TECHNICAL_FAILURE", "technical_failure": True},
    ]
    result = _metrics(rows, {"p": "POSITIVE", "n": "NEGATIVE"})
    assert result["tp"] == 1
    assert result["fp"] == 1
    assert result["technical_failures"] == 1


def test_metrics_gate_requires_both_axes():
    rows = [
        {"case_id": "p1", "prediction": "POSITIVE", "technical_failure": False},
        {"case_id": "p2", "prediction": "POSITIVE", "technical_failure": False},
        {"case_id": "n1", "prediction": "NEGATIVE", "technical_failure": False},
        {"case_id": "n2", "prediction": "POSITIVE", "technical_failure": False},
    ]
    result = _metrics(
        rows,
        {"p1": "POSITIVE", "p2": "POSITIVE", "n1": "NEGATIVE", "n2": "NEGATIVE"},
    )
    assert result["sensitivity"] == 1.0
    assert result["specificity"] == 0.5
    assert result["passed_75_75"] is False
