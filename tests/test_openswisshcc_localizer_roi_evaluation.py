import json

import pytest

from dtwin.benchmark.openswisshcc_localizer_roi_evaluation import _load_selected_labels, _validate_blind_run, _validate_score
from dtwin.benchmark.openswisshcc_localizer_roi_freeze import QUESTION_BANK
from dtwin.benchmark.openswisshcc_localizer_roi_inference import RUN_SCHEMA, SCORE_SCHEMA
from dtwin.core import PipelineError


def _score(probability=0.7):
    question = QUESTION_BANK[0]
    return {
        "schema": SCORE_SCHEMA,
        "question_id": question["question_id"],
        "representation": question["representation"],
        "semantic_positive_probability": probability,
        "mappings": [
            {"mapping_id": "ab", "A_probability": 0.8, "B_probability": 0.2, "selected_token": "A", "positive_token": "A"},
            {"mapping_id": "ba", "A_probability": 0.4, "B_probability": 0.6, "selected_token": "B", "positive_token": "B"},
        ],
        "final_decision": None,
        "ground_truth_read": False,
    }


def test_validate_score_recomputes_mirrored_semantic_probability():
    probability, bias = _validate_score(_score(), QUESTION_BANK[0])
    assert probability == pytest.approx(0.7)
    assert bias == pytest.approx(0.2)


def test_validate_score_rejects_persisted_mean_inconsistent_with_mappings():
    with pytest.raises(PipelineError, match="Media semantica"):
        _validate_score(_score(0.9), QUESTION_BANK[0])


def test_selected_label_loader_validates_full_file_then_selects_pilot(tmp_path):
    rows = []
    for case_id, label in (("anon-a", "POSITIVE"), ("anon-b", "NEGATIVE"), ("anon-c", "NEGATIVE")):
        rows.append({"schema": "argos-openswisshcc-ground-truth-v1", "case_id": case_id, "public_subject_id": case_id, "label": label, "target_condition": "hcc_presence", "label_basis": "public", "review_status": "reviewed"})
    path = tmp_path / "labels.jsonl"
    path.write_text("\n".join(json.dumps(row) for row in rows))
    selected, digest = _load_selected_labels(path, ["anon-a", "anon-b"], 1, 1)
    assert set(selected) == {"anon-a", "anon-b"}
    assert len(digest) == 64


def test_blind_run_is_rejected_before_any_ground_truth_access(tmp_path):
    scores = tmp_path / "scores"
    scores.mkdir()
    (scores / "summary.json").write_text(json.dumps({
        "schema": RUN_SCHEMA,
        "status": "complete_scores_only_no_decision",
        "case_count": 1,
        "experiment_signature": "experiment",
        "review_signature": "review",
        "final_decision": "POSITIVE",
        "ground_truth_read": False,
        "metrics_calculated": False,
        "all_cases_within_scoring_budget": True,
        "end_to_end_time_gate_evaluable": False,
    }))
    with pytest.raises(PipelineError, match="completo, cego"):
        _validate_blind_run(scores_root=scores, freeze={"experiment_signature": "experiment", "question_bank": list(QUESTION_BANK)}, review={"review_signature": "review", "cases": [{"case_id": "anon-a"}]}, localizer_run=tmp_path / "localizer", expected_case_count=1)
