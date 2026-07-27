from pathlib import Path

import pytest

from dtwin.benchmark import openswisshcc_holdout_panels as module
from dtwin.core import PipelineError


def test_frozen_multiphase_and_fallback_configs_are_accepted():
    root = Path(__file__).parents[1]
    multi = module._validate_config(
        root / "configs" / "medgemma_local_4b_multiphase_uniform9_choice_v21.yaml",
        mode="multiphase_fusion",
    )
    fallback = module._validate_config(
        root / "configs" / "medgemma_local_4b_venous_uniform9_choice_v21.yaml",
        mode="single_grayscale",
    )
    assert multi["rag"]["enabled"] is False
    assert fallback["rag"]["enabled"] is False


def test_config_rejects_nonfrozen_response_mode():
    root = Path(__file__).parents[1]
    with pytest.raises(PipelineError, match="congelado"):
        module._validate_config(
            root / "configs" / "medgemma_local_4b_venous_review_fallback_pathology.yaml",
            mode="single_grayscale",
        )


def test_safe_file_rejects_traversal(tmp_path):
    with pytest.raises(PipelineError, match="inseguro"):
        module._safe_file(tmp_path, "../labels.jsonl")
