from __future__ import annotations

import json

import pytest

from dtwin.benchmark import openswisshcc_axial_atlas_rag_score as rag_score
from dtwin.core import PipelineError


def _context() -> dict:
    return {
        "enabled": True,
        "created_utc": "ignored",
        "retriever": "bm25",
        "corpus_version": "v1",
        "index_path": "rag/index.json",
        "index_sha256": "index",
        "retrieval_eval": "docs/eval.yaml",
        "retrieval_eval_sha256": "eval",
        "top_k": 1,
        "max_sources": 1,
        "max_chunk_chars": 100,
        "min_score": 0.0,
        "source_count": 1,
        "query_count": 1,
        "context_sha256": "context",
        "queries": [
            {
                "id": "mimic",
                "query": "vascular mimic",
                "kept_results": [{"chunk_id": "chunk-1"}],
            }
        ],
        "sources": [
            {
                "source_id": "S1",
                "chunk_id": "chunk-1",
                "doc_id": "doc-1",
                "sha256": "source",
                "text": "Vascular structures can mimic focal lesions.",
                "score": 2.5,
            }
        ],
    }


def test_rag_fingerprint_is_deterministic_and_excludes_timestamp():
    first = rag_score.rag_fingerprint(_context())
    changed = _context()
    changed["created_utc"] = "different"
    assert rag_score.rag_fingerprint(changed) == first
    assert first["sources"][0]["text_sha256"] == rag_score._text_sha256(
        "Vascular structures can mimic focal lesions."
    )


def test_rag_fingerprint_rejects_disabled_or_empty_context():
    with pytest.raises(PipelineError):
        rag_score.rag_fingerprint({"enabled": False})
    empty = _context()
    empty["sources"] = []
    with pytest.raises(PipelineError):
        rag_score.rag_fingerprint(empty)


def _response(slice_count: int) -> dict:
    return {
        "contract": "dtwin-medgemma-volume-score-v1",
        "model_id": "model",
        "model_version": "version",
        "slice_count": slice_count,
        "scoring_method": "first_token_restricted_softmax_v1",
        "choice": "POSITIVA",
        "choice_probabilities": {
            "POSITIVA": 0.6,
            "NEGATIVA": 0.3,
            "INCONCLUSIVA": 0.1,
        },
        "choice_token_metadata": {
            "POSITIVA": {"first_token_id": 1, "token_count": 2},
            "NEGATIVA": {"first_token_id": 2, "token_count": 2},
            "INCONCLUSIVA": {"first_token_id": 3, "token_count": 3},
        },
        "tie_detected": False,
        "timings_seconds": {"generation_seconds": 0.1},
        "research_only": True,
        "clinical_use_allowed": False,
        "requires_human_review": True,
    }


def _case() -> dict:
    return {
        "case_id": "anon-case",
        "case_dir": None,
        "manifest": {},
        "manifest_sha256": "manifest",
        "atlas_set_sha256": "atlas",
        "frame_count": 5,
    }


def _protocol() -> dict:
    return {
        "model_id": "model",
        "model_version": "version",
        "instruction": "frozen RAG instruction",
        "endpoint_url": "http://127.0.0.1:8001/score-volume",
        "scoring": {"response_prefix": '{\"resultado_hipotese\":\"'},
        "protocol_signature": "signature",
        "rag_fingerprint": {"context_sha256": "context"},
        "rag_addendum_sha256": "addendum",
    }


def test_score_case_uses_frozen_rag_once_without_labels(monkeypatch, tmp_path):
    monkeypatch.setattr(rag_score, "_validate_case_frames", lambda *_: [b"png"] * 5)
    monkeypatch.setattr(rag_score, "atlas_query", lambda _: "query")
    calls = []

    def fake_request(request, timeout):
        calls.append(json.loads(request.data))
        assert timeout == 180.0
        return _response(5)

    monkeypatch.setattr(rag_score, "_request_json", fake_request)
    output = tmp_path / "prediction.json"
    result = rag_score._score_case(
        case=_case(),
        protocol=_protocol(),
        health={"model_id": "model"},
        output_path=output,
    )
    assert len(calls) == 1
    assert calls[0]["instruction"] == "frozen RAG instruction"
    assert len(calls[0]["images"]) == 5
    assert result["ground_truth_read_during_inference"] is False
    assert result["lesion_mask_read_during_inference"] is False
    assert result["holdout_opened"] is False
    assert output.is_file()


def test_existing_prediction_rejects_rag_hash_tampering(monkeypatch, tmp_path):
    monkeypatch.setattr(rag_score, "atlas_query", lambda _: "query")
    path = tmp_path / "prediction.json"
    payload = {
        "schema_version": rag_score.PREDICTION_SCHEMA,
        "status": "technical_passed",
        "case_id": "anon-case",
        "protocol_signature": "signature",
        "atlas_manifest_sha256": "manifest",
        "atlas_set_sha256": "atlas",
        "frame_count": 5,
        "query_sha256": rag_score._canonical_hash({"query": "query"}),
        "rag_context_sha256": "tampered",
        "rag_addendum_sha256": "addendum",
        "time_gate_passed": True,
        "request_elapsed_seconds": 1.0,
        "ground_truth_read_during_inference": False,
        "lesion_mask_read_during_inference": False,
        "metrics_calculated_during_inference": False,
        "holdout_opened": False,
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(PipelineError, match="contaminada"):
        rag_score._validate_existing(path, _case(), _protocol())

