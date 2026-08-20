import base64
import io
from types import SimpleNamespace

import pytest
import torch
from fastapi.testclient import TestClient
from PIL import Image

from tools.medgemma_server import (
    VOLUME_SCORE_CHOICES,
    VOLUME_SCORE_METHOD,
    VOLUME_SCORE_PREFIX,
    MedGemmaRuntime,
    create_app,
)


def _image_base64(*, size=(16, 16), image_format="PNG"):
    stream = io.BytesIO()
    Image.new("RGB", size, "black").save(stream, format=image_format)
    return base64.b64encode(stream.getvalue()).decode("ascii")


def _payload(*, count=5, encoded=None):
    value = encoded or _image_base64()
    return {
        "contract": "dtwin-medgemma-volume-score-v1",
        "model_id": "google/medgemma-1.5-4b-it",
        "model_version": "MedGemma 1.5 4B Instruction-Tuned",
        "instruction": "Avalie a pilha axial exclusivamente para pesquisa.",
        "images": [
            {"mime_type": "image/png", "base64": value}
            for _ in range(count)
        ],
        "query": "Classifique somente a patologia alvo.",
        "scoring": {"response_prefix": VOLUME_SCORE_PREFIX},
    }


def _patch_runtime(monkeypatch, observed=None):
    def fake_load(self):
        self.model = object()
        self.processor = object()
        self.load_error = None

    def fake_score_volume(self, images, instruction, query, response_prefix):
        if observed is not None:
            observed.update(
                images=images,
                instruction=instruction,
                query=query,
                response_prefix=response_prefix,
            )
        self.last_generation_timings = {
            "queue_seconds": 0.1,
            "generation_seconds": 1.25,
        }
        return {
            "choice": "NEGATIVA",
            "choice_probabilities": {
                "POSITIVA": 0.1,
                "NEGATIVA": 0.8,
                "INCONCLUSIVA": 0.1,
            },
            "scoring_method": VOLUME_SCORE_METHOD,
            "choice_token_metadata": {
                label: {"first_token_id": index + 10, "token_count": 1}
                for index, label in enumerate(VOLUME_SCORE_CHOICES)
            },
            "tie_detected": False,
        }

    monkeypatch.setattr(MedGemmaRuntime, "load", fake_load)
    monkeypatch.setattr(MedGemmaRuntime, "score_volume", fake_score_volume)


def test_volume_score_endpoint_is_isolated_and_auditable(monkeypatch):
    observed = {}
    _patch_runtime(monkeypatch, observed)
    app = create_app("configs/medgemma_local_4b.yaml")

    with TestClient(app) as client:
        health = client.get("/health")
        response = client.post("/score-volume", json=_payload())

    assert health.status_code == 200
    assert health.json()["volume_score_supported"] is True
    assert health.json()["volume_score_contract"] == "dtwin-medgemma-volume-score-v1"
    assert health.json()["volume_score_max_image_edge"] == 768
    assert response.status_code == 200
    body = response.json()
    assert body["contract"] == "dtwin-medgemma-volume-score-v1"
    assert body["slice_count"] == 5
    assert body["choice"] == "NEGATIVA"
    assert body["scoring_method"] == VOLUME_SCORE_METHOD
    assert body["research_only"] is True
    assert body["clinical_use_allowed"] is False
    assert body["requires_human_review"] is True
    assert body["timings_seconds"]["generation_seconds"] == 1.25
    assert observed["response_prefix"] == VOLUME_SCORE_PREFIX
    assert len(observed["images"]) == 5
    assert all(image.mode == "RGB" for image in observed["images"])


def test_volume_score_contract_forbids_arbitrary_choices_prefix_and_phi(monkeypatch):
    _patch_runtime(monkeypatch)
    app = create_app("configs/medgemma_local_4b.yaml")
    choices_payload = _payload()
    choices_payload["scoring"]["choices"] = ["DOENTE", "SAUDAVEL"]
    prefix_payload = _payload()
    prefix_payload["scoring"]["response_prefix"] = "diagnostico:"
    phi_payload = _payload()
    phi_payload["images"][0]["patient_name"] = "Pessoa"

    with TestClient(app) as client:
        assert client.post("/score-volume", json=choices_payload).status_code == 422
        assert client.post("/score-volume", json=prefix_payload).status_code == 422
        assert client.post("/score-volume", json=phi_payload).status_code == 422


def test_volume_score_endpoint_enforces_model_count_and_png_limits(monkeypatch):
    _patch_runtime(monkeypatch)
    app = create_app("configs/medgemma_local_4b.yaml")
    wrong_model = _payload()
    wrong_model["model_id"] = "wrong/model"

    with TestClient(app) as client:
        assert client.post("/score-volume", json=wrong_model).status_code == 409
        assert client.post("/score-volume", json=_payload(count=4)).status_code == 422
        assert client.post("/score-volume", json=_payload(count=86)).status_code == 422
        jpeg = client.post(
            "/score-volume",
            json=_payload(encoded=_image_base64(image_format="JPEG")),
        )
        oversized = client.post(
            "/score-volume",
            json=_payload(encoded=_image_base64(size=(769, 1))),
        )
        atlas_640 = client.post(
            "/score-volume",
            json=_payload(encoded=_image_base64(size=(640, 640))),
        )
        atlas_768 = client.post(
            "/score-volume",
            json=_payload(encoded=_image_base64(size=(768, 768))),
        )

    assert jpeg.status_code == 400
    assert "PNG" in jpeg.json()["detail"]
    assert oversized.status_code == 400
    assert "768x768" in oversized.json()["detail"]
    assert atlas_640.status_code == 200
    assert atlas_768.status_code == 200


class _DeviceBatch(dict):
    def to(self, _device):
        return self


class _FakeTokenizer:
    def __init__(self, mapping):
        self.mapping = mapping

    def __call__(self, text, *, add_special_tokens, return_tensors):
        assert add_special_tokens is False
        assert return_tensors == "pt"
        return {"input_ids": torch.tensor([self.mapping[text]], dtype=torch.long)}


class _FakeProcessor:
    def __init__(self, mapping):
        self.tokenizer = _FakeTokenizer(mapping)

    def apply_chat_template(self, *_args, **_kwargs):
        return _DeviceBatch(
            {
                "input_ids": torch.tensor([[1, 2]], dtype=torch.long),
                "attention_mask": torch.ones((1, 2), dtype=torch.long),
            }
        )


class _FakeModel:
    device = "cpu"

    def __init__(self, last_logits):
        self.last_logits = last_logits

    def __call__(self, **inputs):
        sequence_length = inputs["input_ids"].shape[-1]
        logits = torch.zeros((1, sequence_length, len(self.last_logits)), dtype=torch.float32)
        logits[0, -1, :] = torch.tensor(self.last_logits, dtype=torch.float32)
        return SimpleNamespace(logits=logits)


def _runtime_for_logits(mapping, logits):
    runtime = MedGemmaRuntime({"medgemma": {}})
    runtime.processor = _FakeProcessor(mapping)
    runtime.model = _FakeModel(logits)
    return runtime


def test_score_volume_uses_one_restricted_next_token_softmax():
    mapping = {
        VOLUME_SCORE_PREFIX: [4, 5],
        "POSITIVA": [6, 60],
        "NEGATIVA": [7],
        "INCONCLUSIVA": [8, 80, 81],
    }
    logits = [0.0] * 12
    logits[6], logits[7], logits[8] = 1.0, 3.0, 2.0
    runtime = _runtime_for_logits(mapping, logits)

    result = runtime.score_volume(
        [object()] * 5,
        "instrucao",
        "consulta",
        VOLUME_SCORE_PREFIX,
    )

    assert result["choice"] == "NEGATIVA"
    assert result["scoring_method"] == VOLUME_SCORE_METHOD
    assert result["choice_token_metadata"]["POSITIVA"]["token_count"] == 2
    assert result["choice_token_metadata"]["INCONCLUSIVA"]["first_token_id"] == 8
    assert sum(result["choice_probabilities"].values()) == pytest.approx(1.0, abs=1e-6)
    assert result["choice_probabilities"]["NEGATIVA"] > result["choice_probabilities"]["INCONCLUSIVA"]
    assert result["choice_probabilities"]["INCONCLUSIVA"] > result["choice_probabilities"]["POSITIVA"]


def test_score_volume_rejects_duplicate_first_tokens_and_nonfinite_logits():
    duplicate_mapping = {
        VOLUME_SCORE_PREFIX: [4],
        "POSITIVA": [6],
        "NEGATIVA": [6, 7],
        "INCONCLUSIVA": [8],
    }
    duplicate = _runtime_for_logits(duplicate_mapping, [0.0] * 10)
    with pytest.raises(ValueError, match="distintos"):
        duplicate.score_volume([object()] * 5, "i", "q", VOLUME_SCORE_PREFIX)

    valid_mapping = dict(duplicate_mapping, NEGATIVA=[7])
    logits = [0.0] * 10
    logits[7] = float("nan")
    nonfinite = _runtime_for_logits(valid_mapping, logits)
    with pytest.raises(ValueError, match="finitos"):
        nonfinite.score_volume([object()] * 5, "i", "q", VOLUME_SCORE_PREFIX)
