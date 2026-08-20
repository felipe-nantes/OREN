from pathlib import Path

import pytest

from dtwin.benchmark import openswisshcc_multisequence_freeze as freeze
from dtwin.core import PipelineError

REVIEW={"review_signature":"review","source_cohort_signature":"cohort","case_count":88,"panel_count":2149}

def test_v9_config_is_exact_4b_no_retry_and_freeze_verifies(tmp_path,monkeypatch):
    monkeypatch.setattr(freeze,"verify_multisequence_review",lambda **kwargs: REVIEW)
    config=Path("configs/medgemma_local_4b_multisequence_v9_pairwise.yaml")
    out=tmp_path/"freeze.json"
    result=freeze.create_multisequence_freeze(panel_root=tmp_path,review_path=tmp_path/"review.json",config_path=config,output_path=out,experiment_version="dev-v9",max_case_seconds=180)
    assert result["config"]["model_id"]=="google/medgemma-1.5-4b-it"
    assert result["config"]["timeout_seconds"]==120
    assert result["config"]["max_retries"]==0
    assert result["config"]["response_validation_max_retries"]==0
    assert freeze.verify_multisequence_freeze(panel_root=tmp_path,review_path=tmp_path/"review.json",config_path=config,freeze_path=out)["experiment_signature"]==result["experiment_signature"]

def test_freeze_rejects_budget_above_180(tmp_path,monkeypatch):
    monkeypatch.setattr(freeze,"verify_multisequence_review",lambda **kwargs: REVIEW)
    with pytest.raises(PipelineError,match="max_case_seconds"):
        freeze.create_multisequence_freeze(panel_root=tmp_path,review_path=tmp_path/"r",config_path=Path("configs/medgemma_local_4b_multisequence_v9_pairwise.yaml"),output_path=tmp_path/"f",experiment_version="v9",max_case_seconds=181)
