from __future__ import annotations

import json

import pytest

from dtwin.benchmark import openswisshcc_axial_atlas_chunk_score as chunk_score
from dtwin.benchmark.openswisshcc_axial_atlas_chunk_score import (
    CHUNK_SIZE,
    MAX_CHUNKS,
    partition_frame_indices,
)
from dtwin.core import PipelineError


@pytest.mark.parametrize(
    ("count", "expected"),
    [
        (5, [list(range(5))]),
        (9, [list(range(9))]),
        (10, [list(range(5)), list(range(5, 10))]),
        (11, [list(range(6)), list(range(6, 11))]),
        (20, [list(range(0, 5)), list(range(5, 10)), list(range(10, 15)), list(range(15, 20))]),
    ],
)
def test_partition_is_deterministic_and_exact(count, expected):
    assert partition_frame_indices(count) == expected
    flattened = [index for chunk in expected for index in chunk]
    assert flattened == list(range(count))
    assert len(set(flattened)) == count


@pytest.mark.parametrize("invalid", [0, 1, 4, -1, True, 1.5])
def test_partition_rejects_invalid_counts(invalid):
    with pytest.raises(PipelineError):
        partition_frame_indices(invalid)


def test_full_atlas_fits_frozen_request_budget():
    chunks = partition_frame_indices(CHUNK_SIZE * MAX_CHUNKS)
    assert len(chunks) == MAX_CHUNKS
    assert all(len(chunk) >= CHUNK_SIZE for chunk in chunks)


def _response(slice_count: int, positive: float) -> dict:
    negative = 0.9 - positive
    probabilities = {
        "POSITIVA": positive,
        "NEGATIVA": negative,
        "INCONCLUSIVA": 0.1,
    }
    choice = max(probabilities, key=probabilities.get)
    return {
        "contract": "dtwin-medgemma-volume-score-v1",
        "model_id": "model",
        "model_version": "version",
        "slice_count": slice_count,
        "scoring_method": "first_token_restricted_softmax_v1",
        "choice": choice,
        "choice_probabilities": probabilities,
        "choice_token_metadata": {
            "POSITIVA": {"first_token_id": 1, "token_count": 2},
            "NEGATIVA": {"first_token_id": 2, "token_count": 2},
            "INCONCLUSIVA": {"first_token_id": 3, "token_count": 3},
        },
        "tie_detected": False,
        "timings_seconds": {"generation_seconds": 0.1, "queue_seconds": 0.0},
        "research_only": True,
        "clinical_use_allowed": False,
        "requires_human_review": True,
    }


def _case(frame_count: int = 20) -> dict:
    return {
        "case_id": "anon-case",
        "case_dir": None,
        "manifest": {},
        "manifest_sha256": "manifest",
        "atlas_set_sha256": "atlas",
        "frame_count": frame_count,
    }


def _protocol() -> dict:
    return {
        "model_id": "model",
        "model_version": "version",
        "instruction": "instruction",
        "endpoint_url": "http://127.0.0.1:8001/score-volume",
        "aggregation": "maximum_chunk_log_odds_positive_vs_negative",
        "protocol_signature": "signature",
    }


def test_score_case_calls_each_chunk_once_and_aggregates_max(monkeypatch, tmp_path):
    monkeypatch.setattr(chunk_score, "_validate_case_frames", lambda *_: [b"png"] * 20)
    calls = []

    def fake_request(request, timeout):
        assert timeout == 180.0
        payload = json.loads(request.data)
        calls.append(payload)
        return _response(len(payload["images"]), 0.2 + 0.1 * len(calls))

    monkeypatch.setattr(chunk_score, "_request_json", fake_request)
    output = tmp_path / "prediction.json"
    result = chunk_score._score_case(
        case=_case(),
        protocol=_protocol(),
        health={"model_id": "model"},
        out_path=output,
    )
    assert len(calls) == 4
    assert all(len(call["images"]) == 5 for call in calls)
    assert result["represented_frame_numbers"] == list(range(1, 21))
    assert result["selected_chunk_number"] == 4
    assert result["log_odds_positive_vs_negative"] == max(
        item["log_odds_positive_vs_negative"] for item in result["chunks"]
    )
    assert output.is_file()


def test_intermediate_chunk_failure_invalidates_case(monkeypatch, tmp_path):
    monkeypatch.setattr(chunk_score, "_validate_case_frames", lambda *_: [b"png"] * 10)
    calls = 0

    def fake_request(request, timeout):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise PipelineError("falha técnica simulada")
        return _response(len(json.loads(request.data)["images"]), 0.2)

    monkeypatch.setattr(chunk_score, "_request_json", fake_request)
    output = tmp_path / "prediction.json"
    with pytest.raises(PipelineError, match="simulada"):
        chunk_score._score_case(
            case=_case(10),
            protocol=_protocol(),
            health={"model_id": "model"},
            out_path=output,
        )
    assert calls == 2
    assert not output.exists()
