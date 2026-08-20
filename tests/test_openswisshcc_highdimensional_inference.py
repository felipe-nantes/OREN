import json
from pathlib import Path

from PIL import Image

import dtwin.benchmark.openswisshcc_highdimensional_inference as inference
from dtwin.benchmark.openswisshcc_highdimensional import CONTRACT, SCHEMA
from dtwin.core import PipelineError, sha256_of

CASE_ID = "anon-openswiss-0123456789abcdef"


def _stack(tmp_path: Path):
    root = tmp_path / "stack"
    root.mkdir()
    images = []
    for order in range(1, 6):
        path = root / f"slice_{order:03d}.png"
        Image.new("RGB", (16, 16), (order, order, order)).save(path, format="PNG")
        images.append({
            "order": order,
            "source_index_lps_z": order,
            "filename": path.name,
            "sha256": sha256_of(path),
            "bytes": path.stat().st_size,
            "width": 16,
            "height": 16,
            "mode": "RGB",
            "contains_liver_mask": True,
        })
    manifest = {
        "schema": SCHEMA,
        "contract": CONTRACT,
        "case_id": CASE_ID,
        "sampling": {"strategy": "test", "selected_indices_lps_z": [1, 2, 3, 4, 5]},
        "slice_count": 5,
        "images": images,
        "gate": {
            "passed": True,
            "ground_truth_used": False,
            "lesion_mask_used": False,
            "phi_metadata_included": False,
        },
        "research_only": True,
        "clinical_use_allowed": False,
        "requires_human_review": True,
    }
    (root / "manifest.json").write_text(
        json.dumps(manifest, sort_keys=True) + "\n", encoding="utf-8"
    )
    return root


def _config(endpoint="http://127.0.0.1:8001/generate"):
    return {"medgemma": {
        "endpoint_url": endpoint,
        "healthcheck_url": "http://127.0.0.1:8001/health",
        "model_id": "google/medgemma-1.5-4b-it",
        "model_version": "MedGemma 1.5 4B Instruction-Tuned",
    }}


class _Response:
    def __init__(self, value):
        self.value = value

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return json.dumps(self.value).encode("utf-8")


def test_freeze_is_signed_idempotent_and_local_only(tmp_path, monkeypatch):
    stack = _stack(tmp_path)
    monkeypatch.setattr(inference, "load_screening_config", lambda _path: _config())
    out = tmp_path / "protocol.json"

    first = inference.freeze_highdimensional_protocol(
        stack_dir=stack, config_path=Path("ignored"), out_path=out
    )
    second = inference.freeze_highdimensional_protocol(
        stack_dir=stack, config_path=Path("ignored"), out_path=out
    )

    assert first == second
    assert len(first["protocol_signature"]) == 64
    assert first["ground_truth_read"] is False
    assert first["holdout_opened"] is False
    assert first["endpoint_url"].endswith("/generate-volume")

    monkeypatch.setattr(
        inference,
        "load_screening_config",
        lambda _path: _config("https://external.example/generate"),
    )
    try:
        inference.freeze_highdimensional_protocol(
            stack_dir=stack,
            config_path=Path("ignored"),
            out_path=tmp_path / "external.json",
        )
    except PipelineError as exc:
        assert "exclusivamente local" in str(exc)
    else:
        raise AssertionError("Endpoint externo deveria ser recusado")


def test_run_pilot_validates_health_payload_and_output(tmp_path, monkeypatch):
    stack = _stack(tmp_path)
    monkeypatch.setattr(inference, "load_screening_config", lambda _path: _config())
    protocol_path = tmp_path / "protocol.json"
    protocol = inference.freeze_highdimensional_protocol(
        stack_dir=stack, config_path=Path("ignored"), out_path=protocol_path
    )
    observed = {}

    def fake_urlopen(request, timeout):
        if request.full_url.endswith("/health"):
            return _Response({
                "status": "ready",
                "model_id": protocol["model_id"],
                "model_version": protocol["model_version"],
                "volume_contract": CONTRACT,
                "volume_supported": True,
            })
        payload = json.loads(request.data.decode("utf-8"))
        observed.update(payload=payload, timeout=timeout)
        return _Response({
            "contract": CONTRACT,
            "model_id": protocol["model_id"],
            "model_version": protocol["model_version"],
            "slice_count": 5,
            "output": '{"resultado_hipotese":"NEGATIVA"}',
            "timings_seconds": {"generation_seconds": 1.0},
            "research_only": True,
            "clinical_use_allowed": False,
            "requires_human_review": True,
        })

    monkeypatch.setattr(inference, "urlopen", fake_urlopen)
    result = inference.run_highdimensional_pilot(
        stack_dir=stack,
        protocol_path=protocol_path,
        config_path=Path("ignored"),
        out_path=tmp_path / "result.json",
    )

    assert result["status"] == "technical_passed"
    assert result["classification"] == "NEGATIVA"
    assert result["ground_truth_read"] is False
    assert result["metrics_calculated"] is False
    assert len(observed["payload"]["images"]) == 5
    assert observed["payload"]["generation"]["response_prefix"] == inference.RESPONSE_PREFIX
    assert observed["timeout"] == 180.0


def test_run_refuses_protocol_tampering(tmp_path, monkeypatch):
    stack = _stack(tmp_path)
    monkeypatch.setattr(inference, "load_screening_config", lambda _path: _config())
    protocol_path = tmp_path / "protocol.json"
    inference.freeze_highdimensional_protocol(
        stack_dir=stack, config_path=Path("ignored"), out_path=protocol_path
    )
    protocol = json.loads(protocol_path.read_text(encoding="utf-8"))
    protocol["query"] = "alterado após congelamento"
    protocol_path.write_text(json.dumps(protocol), encoding="utf-8")

    try:
        inference.run_highdimensional_pilot(
            stack_dir=stack,
            protocol_path=protocol_path,
            config_path=Path("ignored"),
            out_path=tmp_path / "result.json",
        )
    except PipelineError as exc:
        assert "Assinatura" in str(exc)
    else:
        raise AssertionError("Protocolo adulterado deveria ser recusado")
