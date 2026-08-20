import json
from pathlib import Path

import pytest

import dtwin.benchmark.openswisshcc_volume_score as score
from dtwin.core import PipelineError, sha256_of

CASE_IDS = [
    "anon-openswiss-0123456789abcdef",
    "anon-openswiss-fedcba9876543210",
]
MODEL_ID = "google/medgemma-1.5-4b-it"
MODEL_VERSION = "MedGemma 1.5 4B Instruction-Tuned"


def _fixture(tmp_path: Path):
    bundle_root = tmp_path / "bundle"
    bundle_root.mkdir()
    (bundle_root / "bundle.json").write_text("{}\n", encoding="utf-8")
    stacks = []
    for case_id in CASE_IDS:
        stack = bundle_root / "stacks" / case_id
        stack.mkdir(parents=True)
        (stack / "manifest.json").write_text("{}\n", encoding="utf-8")
        stacks.append(
            {
                "case_id": case_id,
                "stack_manifest_sha256": sha256_of(stack / "manifest.json"),
                "slice_count": 5,
            }
        )
    bundle = {
        "case_count": 2,
        "case_ids": CASE_IDS,
        "maximum_slices": 50,
        "bundle_signature": "b" * 64,
        "stacks": stacks,
    }
    base = {
        "schema": score.PROTOCOL_SCHEMA,
        "status": "frozen_before_scores",
        "bundle_sha256": sha256_of(bundle_root / "bundle.json"),
        "bundle_signature": bundle["bundle_signature"],
        "case_count": 2,
        "case_ids": CASE_IDS,
        "maximum_slices": 50,
        "model_id": MODEL_ID,
        "model_version": MODEL_VERSION,
        "contract": score.CONTRACT,
        "endpoint_url": "http://127.0.0.1:8001/score-volume",
        "instruction": score.INSTRUCTION,
        "query": score.QUERY,
        "scoring": {
            "response_prefix": score.RESPONSE_PREFIX,
            "choices": list(score.CHOICES),
            "method": score.SCORING_METHOD,
            "requests_per_case": 1,
            "automatic_retries": 0,
            "determinism_pilot_repetitions": 2,
            "probability_tolerance": score.PROBABILITY_TOLERANCE,
        },
        "time_gate_seconds_per_request": score.TIME_GATE_SECONDS,
        "ground_truth_read": False,
        "metrics_calculated": False,
        "holdout_opened": False,
        "research_only": True,
        "clinical_use_allowed": False,
        "requires_human_review": True,
    }
    protocol = dict(base)
    protocol["protocol_signature"] = score._canonical_hash(base)
    protocol_path = tmp_path / "protocol.json"
    protocol_path.write_text(json.dumps(protocol) + "\n", encoding="utf-8")
    return bundle_root, bundle, protocol, protocol_path


def _response(probabilities=None, *, choice="NEGATIVA", tie=False):
    probabilities = probabilities or {
        "POSITIVA": 0.1,
        "NEGATIVA": 0.8,
        "INCONCLUSIVA": 0.1,
    }
    return {
        "contract": score.CONTRACT,
        "model_id": MODEL_ID,
        "model_version": MODEL_VERSION,
        "slice_count": 5,
        "choice": choice,
        "choice_probabilities": probabilities,
        "scoring_method": score.SCORING_METHOD,
        "choice_token_metadata": {
            label: {"first_token_id": index + 10, "token_count": index + 1}
            for index, label in enumerate(score.CHOICES)
        },
        "tie_detected": tie,
        "timings_seconds": {"generation_seconds": 1.0},
        "research_only": True,
        "clinical_use_allowed": False,
        "requires_human_review": True,
    }


def _patch_context(monkeypatch, bundle, responses, calls):
    monkeypatch.setattr(score, "validate_highdimensional_blind_bundle", lambda _root: bundle)
    monkeypatch.setattr(
        score,
        "load_screening_config",
        lambda _path: {
            "medgemma": {
                "endpoint_url": "http://127.0.0.1:8001/generate",
                "healthcheck_url": "http://127.0.0.1:8001/health",
                "model_id": MODEL_ID,
                "model_version": MODEL_VERSION,
            }
        },
    )
    monkeypatch.setattr(
        score,
        "validate_highdimensional_stack",
        lambda stack: ({"case_id": Path(stack).name, "slice_count": 5}, [b"png"] * 5),
    )

    def request_json(request, timeout):
        if request.full_url.endswith("/health"):
            return {
                "status": "ready",
                "model_id": MODEL_ID,
                "model_version": MODEL_VERSION,
                "volume_score_contract": score.CONTRACT,
                "volume_score_method": score.SCORING_METHOD,
                "volume_score_supported": True,
            }
        payload = json.loads(request.data.decode("utf-8"))
        calls.append((request.full_url, payload, timeout))
        index = min(len(calls) - 1, len(responses) - 1)
        return responses[index]

    monkeypatch.setattr(score, "_request_json", request_json)


def test_freeze_volume_score_protocol_is_signed_and_refuses_overwrite(tmp_path, monkeypatch):
    bundle_root, bundle, _protocol, _protocol_path = _fixture(tmp_path)
    monkeypatch.setattr(score, "validate_highdimensional_blind_bundle", lambda _root: bundle)
    monkeypatch.setattr(
        score,
        "load_screening_config",
        lambda _path: {
            "medgemma": {
                "endpoint_url": "http://127.0.0.1:8001/generate",
                "model_id": MODEL_ID,
                "model_version": MODEL_VERSION,
            }
        },
    )
    out = tmp_path / "frozen.json"

    frozen = score.freeze_volume_score_protocol(
        bundle_root=bundle_root,
        config_path=Path("ignored"),
        out_path=out,
    )
    repeated = score.freeze_volume_score_protocol(
        bundle_root=bundle_root,
        config_path=Path("ignored"),
        out_path=out,
    )

    assert repeated == frozen
    assert frozen["endpoint_url"].endswith("/score-volume")
    assert frozen["scoring"]["choices"] == list(score.CHOICES)
    assert frozen["ground_truth_read"] is False
    assert frozen["holdout_opened"] is False
    assert score._load_protocol(out) == frozen

    tampered = dict(frozen, query="alterada")
    out.write_text(json.dumps(tampered), encoding="utf-8")
    with pytest.raises(PipelineError, match="diverge"):
        score.freeze_volume_score_protocol(
            bundle_root=bundle_root,
            config_path=Path("ignored"),
            out_path=out,
        )


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda value: value["choice_probabilities"].update(NEGATIVA=float("nan")), "finita"),
        (lambda value: value["choice_probabilities"].update(NEGATIVA=0.7), "somam 1"),
        (lambda value: value.update(choice="POSITIVA"), "argmax"),
        (
            lambda value: value["choice_token_metadata"]["NEGATIVA"].update(first_token_id=10),
            "distintos",
        ),
        (lambda value: value.update(tie_detected=True), "empate"),
    ],
)
def test_score_response_rejects_invalid_probabilities_choice_and_tokens(
    tmp_path, mutation, message
):
    _bundle_root, _bundle, protocol, _protocol_path = _fixture(tmp_path)
    response = _response()
    mutation(response)

    with pytest.raises(PipelineError, match=message):
        score._validate_score_response(response, protocol=protocol, slice_count=5)


def test_score_response_accepts_fixed_order_tie(tmp_path):
    _bundle_root, _bundle, protocol, _protocol_path = _fixture(tmp_path)
    response = _response(
        {"POSITIVA": 0.4, "NEGATIVA": 0.4, "INCONCLUSIVA": 0.2},
        choice="POSITIVA",
        tie=True,
    )

    validated = score._validate_score_response(response, protocol=protocol, slice_count=5)

    assert validated["classification"] == "POSITIVA"
    assert validated["tie_detected"] is True


def test_blind_batch_is_resumable_and_never_sends_labels(tmp_path, monkeypatch):
    bundle_root, bundle, _protocol, protocol_path = _fixture(tmp_path)
    calls = []
    _patch_context(monkeypatch, bundle, [_response(), _response(choice="NEGATIVA")], calls)
    output = tmp_path / "run"

    first = score.run_volume_score_blind_batch(
        bundle_root=bundle_root,
        protocol_path=protocol_path,
        config_path=Path("ignored"),
        output_root=output,
        max_new_cases=1,
    )
    second = score.run_volume_score_blind_batch(
        bundle_root=bundle_root,
        protocol_path=protocol_path,
        config_path=Path("ignored"),
        output_root=output,
        max_new_cases=1,
    )
    third = score.run_volume_score_blind_batch(
        bundle_root=bundle_root,
        protocol_path=protocol_path,
        config_path=Path("ignored"),
        output_root=output,
    )

    assert first["status"] == "partial"
    assert second["status"] == "complete"
    assert third["status"] == "complete"
    assert len(calls) == 2
    for url, payload, timeout in calls:
        assert url.endswith("/score-volume")
        assert timeout == 180.0
        assert payload["scoring"] == {"response_prefix": score.RESPONSE_PREFIX}
        serialized = json.dumps(payload).lower()
        assert "ground_truth" not in serialized
        assert "label" not in serialized
        assert "lesion_mask" not in serialized
        assert len(payload["images"]) == 5
    summary = json.loads((output / "summary.json").read_text(encoding="utf-8"))
    assert summary["status"] == "blind_scores_complete"
    assert summary["case_count"] == 2
    assert summary["ground_truth_read"] is False
    assert summary["holdout_opened"] is False


def test_blind_batch_refuses_tampered_existing_score(tmp_path, monkeypatch):
    bundle_root, bundle, _protocol, protocol_path = _fixture(tmp_path)
    calls = []
    _patch_context(monkeypatch, bundle, [_response()], calls)
    output = tmp_path / "run"
    score.run_volume_score_blind_batch(
        bundle_root=bundle_root,
        protocol_path=protocol_path,
        config_path=Path("ignored"),
        output_root=output,
        max_new_cases=1,
    )
    path = output / "predictions" / f"{CASE_IDS[0]}.json"
    result = json.loads(path.read_text(encoding="utf-8"))
    result["choice_probabilities"]["NEGATIVA"] = 0.7
    path.write_text(json.dumps(result), encoding="utf-8")

    with pytest.raises(PipelineError, match="somam 1"):
        score.run_volume_score_blind_batch(
            bundle_root=bundle_root,
            protocol_path=protocol_path,
            config_path=Path("ignored"),
            output_root=output,
        )


def test_determinism_pilot_requires_two_equal_planned_replicates(tmp_path, monkeypatch):
    bundle_root, bundle, _protocol, protocol_path = _fixture(tmp_path)
    calls = []
    _patch_context(monkeypatch, bundle, [_response(), _response()], calls)

    result = score.run_volume_score_determinism_pilot(
        bundle_root=bundle_root,
        protocol_path=protocol_path,
        config_path=Path("ignored"),
        output_root=tmp_path / "pilot",
    )

    assert len(calls) == 2
    assert result["status"] == "technical_passed"
    assert result["deterministic"] is True
    assert result["all_time_gates_passed"] is True
    assert result["ground_truth_read"] is False


def test_determinism_pilot_persists_failure_before_aborting(tmp_path, monkeypatch):
    bundle_root, bundle, _protocol, protocol_path = _fixture(tmp_path)
    calls = []
    drifted = _response(
        {"POSITIVA": 0.10001, "NEGATIVA": 0.79999, "INCONCLUSIVA": 0.1}
    )
    _patch_context(monkeypatch, bundle, [_response(), drifted], calls)
    output = tmp_path / "pilot"

    with pytest.raises(PipelineError, match="determinístico"):
        score.run_volume_score_determinism_pilot(
            bundle_root=bundle_root,
            protocol_path=protocol_path,
            config_path=Path("ignored"),
            output_root=output,
        )

    summary = json.loads((output / "summary.json").read_text(encoding="utf-8"))
    assert summary["status"] == "technical_failed"
    assert summary["deterministic"] is False
    assert summary["holdout_opened"] is False


def test_batch_rejects_nonpositive_chunk_and_nonlocal_endpoint(tmp_path):
    bundle_root, _bundle, _protocol, protocol_path = _fixture(tmp_path)
    with pytest.raises(PipelineError, match="positivo"):
        score.run_volume_score_blind_batch(
            bundle_root=bundle_root,
            protocol_path=protocol_path,
            config_path=Path("ignored"),
            output_root=tmp_path / "run",
            max_new_cases=0,
        )
    with pytest.raises(PipelineError, match="exclusivamente local"):
        score._score_url("https://example.org/generate")

