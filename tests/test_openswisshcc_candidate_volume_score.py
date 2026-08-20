from __future__ import annotations

import json
from pathlib import Path

import pytest
from PIL import Image

import dtwin.benchmark.openswisshcc_candidate_volume_score as score
from dtwin.benchmark.openswisshcc_candidate_volume import (
    CANDIDATE_SCHEMA,
    CASE_SCHEMA,
    COHORT_SCHEMA,
)
from dtwin.benchmark.openswisshcc_candidate_volume import CONTRACT as INPUT_CONTRACT
from dtwin.benchmark.openswisshcc_highdimensional_inference import _canonical_hash
from dtwin.benchmark.openswisshcc_volume_score import CONTRACT, SCORING_METHOD
from dtwin.core import PipelineError, sha256_of

CASE_ID = "anon-openswiss-0123456789abcdef"


def _json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _bundle(tmp_path: Path, stack_count: int = 1):
    root = tmp_path / "bundle"
    case_dir = root / CASE_ID
    case_dir.mkdir(parents=True)
    stack_records = []
    for number in range(1, stack_count + 1):
        candidate_dir = case_dir / f"candidate_{number:03d}"
        candidate_dir.mkdir()
        frames = []
        for order in range(1, 6):
            filename = f"frame_{order:03d}_t1_venous_z{order:04d}.png"
            path = candidate_dir / filename
            Image.new("RGB", (384, 384), (order * 10, order * 10, order * 10)).save(path, "PNG")
            frames.append({
                "order": order,
                "group_order": order,
                "filename": filename,
                "source_index_z": order,
                "sha256": sha256_of(path),
                "bytes": path.stat().st_size,
                "width": 384,
                "height": 384,
                "mode": "RGB",
            })
        candidate = {
            "schema": CANDIDATE_SCHEMA,
            "contract": INPUT_CONTRACT,
            "case_id": CASE_ID,
            "candidate_number": number,
            "candidate_total": stack_count,
            "frame_count": 5,
            "fallback_no_candidate": False,
            "groups": [{"role": "t1_venous", "category": "dynamic", "frame_count": 5, "frames": frames}],
            "gate": {
                "passed": True,
                "candidate_contour_rendered": False,
                "ground_truth_read": False,
                "dataset_lesion_mask_used": False,
                "phi_metadata_included": False,
            },
            "research_only": True,
            "clinical_use_allowed": False,
            "requires_human_review": True,
        }
        manifest_path = candidate_dir / "manifest.json"
        _json(manifest_path, candidate)
        stack_records.append({
            "candidate_number": number,
            "relative_directory": candidate_dir.name,
            "manifest_sha256": sha256_of(manifest_path),
            "frame_count": 5,
            "component_rank": number,
            "component_voxels": 10,
            "fallback_no_candidate": False,
        })
    case = {
        "schema": CASE_SCHEMA,
        "contract": INPUT_CONTRACT,
        "case_id": CASE_ID,
        "candidate_stack_count": stack_count,
        "candidate_stacks": stack_records,
        "gate": {
            "passed": True,
            "ground_truth_read": False,
            "dataset_lesion_mask_used": False,
            "phi_metadata_included": False,
        },
    }
    case_manifest = case_dir / "case_manifest.json"
    _json(case_manifest, case)
    cohort = {
        "schema": COHORT_SCHEMA,
        "contract": INPUT_CONTRACT,
        "case_count": 1,
        "candidate_stack_count": stack_count,
        "cases": [{"case_id": CASE_ID, "candidate_stack_count": stack_count, "case_manifest_sha256": sha256_of(case_manifest), "gallery_candidates": []}],
        "gallery_signature": "b" * 64,
        "ground_truth_read": False,
        "dataset_lesion_mask_used": False,
        "holdout_opened": False,
        "inference_executed": False,
        "research_only": True,
        "clinical_use_allowed": False,
        "requires_human_review": True,
    }
    _json(root / "cohort_manifest.json", cohort)
    return root


def _review(path: Path, bundle: dict, *, approved=True):
    value = {
        "schema": score.REVIEW_SCHEMA,
        "status": "approved_for_blind_4b_scoring" if approved else "pending",
        "reviewer": "jm",
        "reviewed_at_utc": "2026-07-16T12:00:00+00:00",
        "confirmations": {"alignment": True, "continuity": True, "contrast": True, "no_phi": True},
        "cohort_sha256": bundle["cohort_sha256"],
        "gallery_signature": bundle["cohort"]["gallery_signature"],
        "case_count": bundle["case_count"],
        "candidate_stack_count": bundle["candidate_stack_count"],
        "ground_truth_read": False,
        "dataset_lesion_mask_used": False,
        "holdout_opened": False,
        "research_only": True,
        "clinical_use_allowed": False,
    }
    value["review_signature"] = _canonical_hash(value)
    _json(path, value)
    return value


def _protocol():
    return {
        "model_id": "google/medgemma-1.5-4b-it",
        "model_version": "test",
        "endpoint_url": "http://127.0.0.1:8001/score-volume",
        "instruction": score.INSTRUCTION,
        "scoring": {"response_prefix": '{"resultado_hipotese":"'},
        "protocol_signature": "c" * 64,
    }


def _response(choice="POSITIVA", positive=0.8, negative=0.1, inconclusive=0.1, slice_count=5):
    probabilities = {"POSITIVA": positive, "NEGATIVA": negative, "INCONCLUSIVA": inconclusive}
    return {
        "contract": CONTRACT,
        "model_id": "google/medgemma-1.5-4b-it",
        "model_version": "test",
        "slice_count": slice_count,
        "choice": choice,
        "choice_probabilities": probabilities,
        "scoring_method": SCORING_METHOD,
        "choice_token_metadata": {
            "POSITIVA": {"first_token_id": 1, "token_count": 2},
            "NEGATIVA": {"first_token_id": 2, "token_count": 2},
            "INCONCLUSIVA": {"first_token_id": 3, "token_count": 3},
        },
        "tie_detected": False,
        "research_only": True,
        "clinical_use_allowed": False,
        "requires_human_review": True,
    }


def test_bundle_validator_checks_all_hashes_and_safety(tmp_path):
    root = _bundle(tmp_path, 3)
    bundle = score.validate_candidate_volume_bundle(root)
    assert bundle["case_count"] == 1
    assert bundle["candidate_stack_count"] == 3
    frame = root / CASE_ID / "candidate_002" / "frame_001_t1_venous_z0001.png"
    frame.write_bytes(frame.read_bytes() + b"tampered")
    with pytest.raises(PipelineError, match="adulterado"):
        score.validate_candidate_volume_bundle(root)


def test_human_review_is_required_and_cryptographically_bound(tmp_path):
    bundle = score.validate_candidate_volume_bundle(_bundle(tmp_path))
    review_path = tmp_path / "review.json"
    _review(review_path, bundle, approved=False)
    with pytest.raises(PipelineError, match="Revisao humana"):
        score.validate_candidate_volume_review(review_path, bundle)
    _review(review_path, bundle, approved=True)
    assert score.validate_candidate_volume_review(review_path, bundle)["reviewer"] == "jm"
    value = json.loads(review_path.read_text())
    value["reviewer"] = "changed"
    _json(review_path, value)
    with pytest.raises(PipelineError, match="Assinatura"):
        score.validate_candidate_volume_review(review_path, bundle)


def test_candidate_query_contains_frame_map_and_no_positive_assumption(tmp_path):
    bundle = score.validate_candidate_volume_bundle(_bundle(tmp_path))
    stack = bundle["cases"][0]["candidate_stacks"][0]
    manifest, _ = score._validate_candidate_stack(stack["candidate_dir"], stack)
    query = score.candidate_query(manifest)
    assert "1-5=t1_venous" in query
    assert "candidato automatico" in query
    assert "somente se" in query


def test_aggregation_uses_maximum_positive_negative_log_odds():
    candidates = [
        {"candidate_number": 1, "classification": "NEGATIVA", "choice_probabilities": {"POSITIVA": 0.1, "NEGATIVA": 0.8, "INCONCLUSIVA": 0.1}, "log_odds_positive_vs_negative": score.candidate_log_odds({"POSITIVA": 0.1, "NEGATIVA": 0.8})},
        {"candidate_number": 2, "classification": "POSITIVA", "choice_probabilities": {"POSITIVA": 0.7, "NEGATIVA": 0.2, "INCONCLUSIVA": 0.1}, "log_odds_positive_vs_negative": score.candidate_log_odds({"POSITIVA": 0.7, "NEGATIVA": 0.2})},
    ]
    result = score.aggregate_candidate_scores(candidates)
    assert result["selected_candidate_number"] == 2
    assert result["case_score"] > 0


def test_freeze_binds_bundle_review_model_prompt_and_time_gate(tmp_path, monkeypatch):
    root = _bundle(tmp_path)
    bundle = score.validate_candidate_volume_bundle(root)
    review_path = tmp_path / "review.json"
    _review(review_path, bundle)
    monkeypatch.setattr(score, "load_screening_config", lambda _: {"medgemma": {"model_id": "google/medgemma-1.5-4b-it", "model_version": "test", "endpoint_url": "http://127.0.0.1:8001/generate"}})
    protocol = score.freeze_candidate_volume_score_protocol(bundle_root=root, review_path=review_path, config_path=tmp_path / "config.yaml", out_path=tmp_path / "protocol.json")
    assert protocol["case_time_gate_seconds"] == 180.0
    assert protocol["scoring"]["requests_per_candidate"] == 1
    assert protocol["scoring"]["automatic_retries"] == 0
    assert protocol["scoring"]["aggregation"] == score.AGGREGATION_METHOD
    assert len(protocol["protocol_signature"]) == 64


def test_case_scores_each_candidate_once_and_publishes_only_complete_result(tmp_path, monkeypatch):
    bundle = score.validate_candidate_volume_bundle(_bundle(tmp_path, 3))
    responses = [
        _response("NEGATIVA", 0.1, 0.8, 0.1),
        _response("POSITIVA", 0.7, 0.2, 0.1),
        _response("INCONCLUSIVA", 0.2, 0.3, 0.5),
    ]
    calls = []
    monkeypatch.setattr(score, "_request_json", lambda request, timeout: calls.append(timeout) or responses.pop(0))
    prediction_path = tmp_path / "prediction.json"
    result = score._score_case(case=bundle["cases"][0], protocol=_protocol(), health={"model_id": "google/medgemma-1.5-4b-it"}, prediction_path=prediction_path)
    assert len(calls) == 3
    assert result["aggregation"]["selected_candidate_number"] == 2
    assert prediction_path.is_file()
    assert result["ground_truth_read"] is False


def test_intermediate_failure_does_not_publish_partial_case(tmp_path, monkeypatch):
    bundle = score.validate_candidate_volume_bundle(_bundle(tmp_path, 3))
    responses = [_response("NEGATIVA", 0.1, 0.8, 0.1), {"invalid": True}]
    monkeypatch.setattr(score, "_request_json", lambda request, timeout: responses.pop(0))
    path = tmp_path / "prediction.json"
    with pytest.raises(PipelineError):
        score._score_case(case=bundle["cases"][0], protocol=_protocol(), health={}, prediction_path=path)
    assert not path.exists()


def test_case_level_180_second_gate_prevents_publication(tmp_path, monkeypatch):
    bundle = score.validate_candidate_volume_bundle(_bundle(tmp_path))
    moments = iter([0.0, 0.0, 0.0, 181.0, 181.0])
    monkeypatch.setattr(score.time, "monotonic", lambda: next(moments))
    monkeypatch.setattr(score, "_request_json", lambda request, timeout: _response())
    path = tmp_path / "prediction.json"
    with pytest.raises(PipelineError, match="gate temporal"):
        score._score_case(case=bundle["cases"][0], protocol=_protocol(), health={}, prediction_path=path)
    assert not path.exists()


def test_run_context_refuses_mixing_protocols_in_same_output(tmp_path):
    bundle = score.validate_candidate_volume_bundle(_bundle(tmp_path))
    output_root = tmp_path / "run"
    output_root.mkdir()
    protocol = _protocol()
    score._ensure_run_context(output_root, protocol, bundle)
    changed = {**protocol, "protocol_signature": "d" * 64}
    with pytest.raises(PipelineError, match="outro protocolo"):
        score._ensure_run_context(output_root, changed, bundle)


def test_reused_prediction_revalidates_candidate_hash_and_log_odds(tmp_path, monkeypatch):
    bundle = score.validate_candidate_volume_bundle(_bundle(tmp_path))
    case = bundle["cases"][0]
    monkeypatch.setattr(score, "_request_json", lambda request, timeout: _response())
    path = tmp_path / "prediction.json"
    result = score._score_case(case=case, protocol=_protocol(), health={}, prediction_path=path)
    assert score._validate_existing_prediction(path, case, _protocol()) == result

    tampered = json.loads(path.read_text(encoding="utf-8"))
    tampered["candidate_results"][0]["candidate_manifest_sha256"] = "0" * 64
    _json(path, tampered)
    with pytest.raises(PipelineError, match="stack candidato"):
        score._validate_existing_prediction(path, case, _protocol())

    _json(path, result)
    tampered = json.loads(path.read_text(encoding="utf-8"))
    tampered["candidate_results"][0]["log_odds_positive_vs_negative"] += 0.5
    tampered["aggregation"] = score.aggregate_candidate_scores(tampered["candidate_results"])
    _json(path, tampered)
    with pytest.raises(PipelineError, match="log-odds adulterado"):
        score._validate_existing_prediction(path, case, _protocol())

def test_complete_progress_uses_distinct_summary_schema(tmp_path):
    output = tmp_path / "run"
    predictions = output / "predictions"
    predictions.mkdir(parents=True)
    case_id = "anon-summary"
    _json(predictions / f"{case_id}.json", {"case_id": case_id})
    result = score._write_progress(
        output,
        {"protocol_signature": "a" * 64},
        {"case_count": 1},
        [
            {
                "case_id": case_id,
                "aggregation": {
                    "case_score": 0.25,
                    "selected_candidate_number": 1,
                },
                "scoring_elapsed_seconds": 12.5,
                "candidate_stack_count": 1,
            }
        ],
    )
    progress = json.loads((output / "progress.json").read_text(encoding="utf-8"))
    summary = json.loads((output / "summary.json").read_text(encoding="utf-8"))
    assert progress["schema"] == score.PROGRESS_SCHEMA
    assert summary["schema"] == score.SUMMARY_SCHEMA
    assert result == summary
