import json
import time
from pathlib import Path

import pytest
from PIL import Image

from dtwin.benchmark.openswisshcc_alignment import _sha256
from dtwin.benchmark.openswisshcc_lesion_localizer import CASE_SCHEMA as LOCALIZER_CASE_SCHEMA
from dtwin.benchmark.openswisshcc_localizer_roi_freeze import QUESTION_BANK, SCORING_PROTOCOL
from dtwin.benchmark import openswisshcc_localizer_roi_inference as inference
from dtwin.core import PipelineError


class FakeScorer:
    model_id = "google/medgemma-1.5-4b-it"
    model_version = "test"

    def __init__(self, sleep_seconds=0.0, invalid=False):
        self.prompts = []
        self.sleep_seconds = sleep_seconds
        self.invalid = invalid

    def score_choice(self, panel_path, prompt):
        self.prompts.append(prompt)
        if self.sleep_seconds:
            time.sleep(self.sleep_seconds)
        if self.invalid:
            return {"choice": "A", "choice_probabilities": {"A": 0.8, "B": 0.3}}
        a_line = next(line for line in prompt.splitlines() if line.startswith("A = "))
        mapping_ab = a_line in {
            "A = focal lesion supported",
            "A = cross-sequence focal abnormality supported",
            "A = focal lesion behavior supported",
            "A = lesion-supporting enhancement evolution",
        }
        return {"choice": "A" if mapping_ab else "B", "choice_probabilities": {"A": 0.8, "B": 0.2} if mapping_ab else {"A": 0.3, "B": 0.7}}


def _gallery(root: Path, case_id: str, representation: str, fallback=False):
    case_dir = root / case_id
    case_dir.mkdir(parents=True)
    path = case_dir / "panel.png"
    Image.new("RGB", (64, 64), (20, 30, 40)).save(path, "PNG")
    roles = ["t1_venous", "t2_blade", "dwi_trace_run_03", "dwi_adc"] if representation == "morphology" else ["t1_native", "t1_arterial_registered", "t1_venous", "t1_delayed_registered"]
    panel = {
        "panel_number": 1,
        "panel_total": 1,
        "image": "panel.png",
        "sha256": _sha256(path),
        "bytes": path.stat().st_size,
        "fallback_no_candidate": fallback,
        "tiles": [{"role": role, "available_in_fov": True} for role in roles],
    }
    manifest_name = "roi_manifest.json" if representation == "morphology" else "enhancement_roi_manifest.json"
    (case_dir / manifest_name).write_text(json.dumps({"case_id": case_id, "panels": [panel]}))


def _foundation(tmp_path, monkeypatch, fallback=False, max_scoring=90.0):
    case_id = "anon-a"
    morphology = tmp_path / "morphology"
    enhancement = tmp_path / "enhancement"
    _gallery(morphology, case_id, "morphology", fallback)
    _gallery(enhancement, case_id, "enhancement", fallback)
    localizer = tmp_path / "localizer" / case_id
    localizer.mkdir(parents=True)
    localizer_manifest = {
        "schema": LOCALIZER_CASE_SCHEMA,
        "case_id": case_id,
        "status": "candidate_scores_only_no_decision",
        "elapsed_seconds": 12.5,
        "ground_truth_read": False,
        "ground_truth_lesion_mask_used": False,
        "final_decision": None,
    }
    (localizer / "localizer_manifest.json").write_text(json.dumps(localizer_manifest))
    review = {"review_signature": "review", "cases": [{"case_id": case_id, "panel_count": 1, "fallback_no_candidate": fallback}]}
    freeze = {
        "experiment_signature": "experiment",
        "question_bank": list(QUESTION_BANK),
        "scoring_protocol": SCORING_PROTOCOL,
        "max_upstream_seconds": 90.0,
        "max_scoring_seconds": max_scoring,
        "max_end_to_end_seconds": 180.0,
    }
    monkeypatch.setattr(inference, "verify_paired_review", lambda **kwargs: review)
    monkeypatch.setattr(inference, "verify_roi_freeze", lambda **kwargs: freeze)
    return morphology, enhancement, localizer, case_id


def _run(tmp_path, monkeypatch, scorer, **kwargs):
    morphology, enhancement, localizer_case, case_id = _foundation(tmp_path, monkeypatch, **kwargs)
    output = tmp_path / "output"
    summary = inference.run_roi_scores(morphology_root=morphology, enhancement_root=enhancement, review_path=tmp_path / "review", freeze_path=tmp_path / "freeze", config_path=tmp_path / "config", localizer_run=localizer_case.parent, output_root=output, scorer=scorer, expected_case_count=1)
    return output, summary, case_id


def test_runner_scores_four_questions_with_two_mirrored_mappings(tmp_path, monkeypatch):
    scorer = FakeScorer()
    output, summary, case_id = _run(tmp_path, monkeypatch, scorer)
    scores = json.loads((output / case_id / "mirrored_ab_scores.json").read_text())
    manifest = json.loads((output / case_id / "mirrored_ab_manifest.json").read_text())
    questions = scores[0]["questions"]
    assert len(questions) == 4
    assert len(scorer.prompts) == 8
    assert all(question["score"]["semantic_positive_probability"] == pytest.approx(0.75) for question in questions)
    assert manifest["mapping_call_count"] == 8
    assert manifest["final_decision"] is None
    assert manifest["ground_truth_read"] is False
    assert manifest["end_to_end_measurement_complete"] is False
    assert summary["end_to_end_time_gate_evaluable"] is False


def test_fallback_prompt_explicitly_states_no_candidate(tmp_path, monkeypatch):
    scorer = FakeScorer()
    _run(tmp_path, monkeypatch, scorer, fallback=True)
    assert scorer.prompts
    assert all("produced no candidate" in prompt and "no yellow outline" in prompt for prompt in scorer.prompts)


def test_invalid_probabilities_abort_without_publishing_output(tmp_path, monkeypatch):
    scorer = FakeScorer(invalid=True)
    morphology, enhancement, localizer_case, _ = _foundation(tmp_path, monkeypatch)
    output = tmp_path / "output"
    with pytest.raises(PipelineError, match="Probabilidades"):
        inference.run_roi_scores(morphology_root=morphology, enhancement_root=enhancement, review_path=tmp_path / "review", freeze_path=tmp_path / "freeze", config_path=tmp_path / "config", localizer_run=localizer_case.parent, output_root=output, scorer=scorer, expected_case_count=1)
    assert not output.exists()
    assert not list(tmp_path.glob("._v10ab_*"))


def test_scoring_timeout_aborts_atomically(tmp_path, monkeypatch):
    scorer = FakeScorer(sleep_seconds=0.01)
    morphology, enhancement, localizer_case, _ = _foundation(tmp_path, monkeypatch, max_scoring=0.001)
    output = tmp_path / "output"
    with pytest.raises(PipelineError, match="limite"):
        inference.run_roi_scores(morphology_root=morphology, enhancement_root=enhancement, review_path=tmp_path / "review", freeze_path=tmp_path / "freeze", config_path=tmp_path / "config", localizer_run=localizer_case.parent, output_root=output, scorer=scorer, expected_case_count=1)
    assert not output.exists()
    assert not list(tmp_path.glob("._v10ab_*"))
