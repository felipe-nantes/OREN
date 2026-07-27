import json
from pathlib import Path

import dtwin.benchmark.openswisshcc_highdimensional_batch_inference as runner
from dtwin.benchmark.openswisshcc_highdimensional_batch import BATCH_PROTOCOL_SCHEMA
from dtwin.benchmark.openswisshcc_highdimensional_inference import CONTRACT
from dtwin.core import PipelineError, sha256_of


CASE_IDS = [
    "anon-openswiss-0123456789abcdef",
    "anon-openswiss-fedcba9876543210",
]


def _fixture(tmp_path: Path):
    bundle_root = tmp_path / "bundle"
    bundle_root.mkdir()
    (bundle_root / "bundle.json").write_text("{}\n", encoding="utf-8")
    stacks = []
    for case_id in CASE_IDS:
        stack = bundle_root / "stacks" / case_id
        stack.mkdir(parents=True)
        (stack / "manifest.json").write_text("{}\n", encoding="utf-8")
        stacks.append({
            "case_id": case_id,
            "stack_manifest_sha256": sha256_of(stack / "manifest.json"),
            "slice_count": 5,
        })
    bundle = {
        "case_count": 2,
        "case_ids": CASE_IDS,
        "maximum_slices": 50,
        "bundle_signature": "b" * 64,
        "stacks": stacks,
    }
    base = {
        "schema": BATCH_PROTOCOL_SCHEMA,
        "status": "frozen_before_predictions",
        "bundle_sha256": sha256_of(bundle_root / "bundle.json"),
        "bundle_signature": bundle["bundle_signature"],
        "case_count": 2,
        "case_ids": CASE_IDS,
        "maximum_slices": 50,
        "model_id": "google/medgemma-1.5-4b-it",
        "model_version": "MedGemma 1.5 4B Instruction-Tuned",
        "contract": CONTRACT,
        "endpoint_url": "http://127.0.0.1:8001/generate-volume",
        "instruction": "instruction",
        "query": "query",
        "generation": {
            "max_output_tokens": 16,
            "response_prefix": '{"resultado_hipotese":"',
            "do_sample": False,
            "requests_per_case": 1,
            "automatic_retries": 0,
        },
        "time_gate_seconds_per_case": 180.0,
        "ground_truth_read": False,
        "metrics_calculated": False,
        "holdout_opened": False,
        "research_only": True,
        "clinical_use_allowed": False,
        "requires_human_review": True,
    }
    protocol = dict(base)
    protocol["protocol_signature"] = runner._canonical_hash(base)
    protocol_path = tmp_path / "protocol.json"
    protocol_path.write_text(json.dumps(protocol) + "\n", encoding="utf-8")
    return bundle_root, bundle, protocol_path


def _patch_runtime(monkeypatch, bundle, calls):
    monkeypatch.setattr(runner, "validate_highdimensional_blind_bundle", lambda _root: bundle)
    monkeypatch.setattr(runner, "load_screening_config", lambda _path: {"medgemma": {
        "healthcheck_url": "http://127.0.0.1:8001/health",
        "model_id": "google/medgemma-1.5-4b-it",
        "model_version": "MedGemma 1.5 4B Instruction-Tuned",
    }})
    monkeypatch.setattr(
        runner,
        "validate_highdimensional_stack",
        lambda stack: ({"case_id": Path(stack).name, "slice_count": 5}, [b"png"] * 5),
    )

    def request_json(request, timeout):
        if request.full_url.endswith("/health"):
            return {
                "status": "ready",
                "model_id": "google/medgemma-1.5-4b-it",
                "model_version": "MedGemma 1.5 4B Instruction-Tuned",
                "volume_contract": CONTRACT,
                "volume_supported": True,
            }
        calls.append((json.loads(request.data.decode("utf-8")), timeout))
        label = "NEGATIVA" if len(calls) == 1 else "POSITIVA"
        return {
            "contract": CONTRACT,
            "model_id": "google/medgemma-1.5-4b-it",
            "model_version": "MedGemma 1.5 4B Instruction-Tuned",
            "slice_count": 5,
            "output": json.dumps({"resultado_hipotese": label}),
            "timings_seconds": {"generation_seconds": 1.0},
            "research_only": True,
            "clinical_use_allowed": False,
            "requires_human_review": True,
        }

    monkeypatch.setattr(runner, "_request_json", request_json)


def test_batch_runner_is_resumable_and_never_repeats_completed_case(tmp_path, monkeypatch):
    bundle_root, bundle, protocol_path = _fixture(tmp_path)
    calls = []
    _patch_runtime(monkeypatch, bundle, calls)
    output = tmp_path / "predictions"

    first = runner.run_highdimensional_blind_batch(
        bundle_root=bundle_root,
        protocol_path=protocol_path,
        config_path=Path("ignored"),
        output_root=output,
        max_new_cases=1,
    )
    second = runner.run_highdimensional_blind_batch(
        bundle_root=bundle_root,
        protocol_path=protocol_path,
        config_path=Path("ignored"),
        output_root=output,
        max_new_cases=1,
    )
    third = runner.run_highdimensional_blind_batch(
        bundle_root=bundle_root,
        protocol_path=protocol_path,
        config_path=Path("ignored"),
        output_root=output,
    )

    assert first["status"] == "partial"
    assert first["completed_case_count"] == 1
    assert second["status"] == "complete"
    assert third["status"] == "complete"
    assert len(calls) == 2
    assert all(len(payload["images"]) == 5 for payload, _timeout in calls)
    assert all(timeout == 180.0 for _payload, timeout in calls)
    summary = json.loads((output / "summary.json").read_text(encoding="utf-8"))
    assert summary["classification_counts_without_ground_truth"] == {
        "POSITIVA": 1,
        "NEGATIVA": 1,
        "INCONCLUSIVA": 0,
    }
    assert summary["ground_truth_read"] is False
    assert summary["holdout_opened"] is False


def test_batch_runner_refuses_protocol_tampering(tmp_path, monkeypatch):
    bundle_root, bundle, protocol_path = _fixture(tmp_path)
    calls = []
    _patch_runtime(monkeypatch, bundle, calls)
    value = json.loads(protocol_path.read_text(encoding="utf-8"))
    value["query"] = "tampered"
    protocol_path.write_text(json.dumps(value), encoding="utf-8")

    try:
        runner.run_highdimensional_blind_batch(
            bundle_root=bundle_root,
            protocol_path=protocol_path,
            config_path=Path("ignored"),
            output_root=tmp_path / "output",
        )
    except PipelineError as exc:
        assert "Assinatura" in str(exc)
    else:
        raise AssertionError("Protocolo adulterado deveria ser recusado")


def test_batch_runner_refuses_nonpositive_chunk_size(tmp_path):
    bundle_root, _bundle, protocol_path = _fixture(tmp_path)
    try:
        runner.run_highdimensional_blind_batch(
            bundle_root=bundle_root,
            protocol_path=protocol_path,
            config_path=Path("ignored"),
            output_root=tmp_path / "output",
            max_new_cases=0,
        )
    except PipelineError as exc:
        assert "positivo" in str(exc)
    else:
        raise AssertionError("Chunk não positivo deveria ser recusado")
