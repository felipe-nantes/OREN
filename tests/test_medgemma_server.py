import base64
import io

from fastapi.testclient import TestClient
from PIL import Image

from tools.medgemma_server import MedGemmaRuntime, create_app


def _png_base64():
    stream = io.BytesIO()
    Image.new("RGB", (16, 16), "black").save(stream, format="PNG")
    return base64.b64encode(stream.getvalue()).decode("ascii")


def _jpeg_base64():
    stream = io.BytesIO()
    Image.new("RGB", (16, 16), "black").save(stream, format="JPEG")
    return base64.b64encode(stream.getvalue()).decode("ascii")


def test_local_gateway_health_and_contract(monkeypatch):
    def fake_load(self):
        self.model = object()
        self.processor = object()
        self.load_error = None

    monkeypatch.setattr(MedGemmaRuntime, "load", fake_load)
    def fake_generate(self, _image, _prompt, _tokens, _response_prefix=None):
        self.last_generation_timings = {"queue_seconds": 0.25, "generation_seconds": 1.5}
        return '{"resultado_hipotese":"INCONCLUSIVA"}'

    monkeypatch.setattr(MedGemmaRuntime, "generate", fake_generate)
    app = create_app("configs/medgemma_local_4b.yaml")
    with TestClient(app) as client:
        health = client.get("/health")
        assert health.status_code == 200
        assert health.json()["status"] == "ready"
        response = client.post(
            "/generate",
            json={
                "contract": "dtwin-medgemma-v1",
                "model_id": "google/medgemma-1.5-4b-it",
                "model_version": "MedGemma 1.5 4B Instruction-Tuned",
                "prompt": "research only",
                "image": {"mime_type": "image/png", "base64": _png_base64()},
                "generation": {"max_output_tokens": 32},
            },
        )
        assert response.status_code == 200
        assert response.json()["model_id"] == "google/medgemma-1.5-4b-it"
        assert response.json()["timings_seconds"] == {
            "queue_seconds": 0.25, "generation_seconds": 1.5,
        }


def test_local_gateway_forwards_restricted_json_response_prefix(monkeypatch):
    observed = []

    def fake_load(self):
        self.model = object()
        self.processor = object()
        self.load_error = None

    def fake_generate(self, _image, _prompt, _tokens, response_prefix=None):
        observed.append(response_prefix)
        return '{"resultado_hipotese":"NEGATIVA"}'

    monkeypatch.setattr(MedGemmaRuntime, "load", fake_load)
    monkeypatch.setattr(MedGemmaRuntime, "generate", fake_generate)
    app = create_app("configs/medgemma_local_4b.yaml")
    with TestClient(app) as client:
        payload = {
            "contract": "dtwin-medgemma-v1",
            "model_id": "google/medgemma-1.5-4b-it",
            "model_version": "MedGemma 1.5 4B Instruction-Tuned",
            "prompt": "research only",
            "image": {"mime_type": "image/png", "base64": _png_base64()},
            "generation": {"max_output_tokens": 32, "response_prefix": "{"},
        }
        assert client.post("/generate", json=payload).status_code == 200
        assert observed == ["{"]

        payload["generation"]["response_prefix"] = "diagnosis:"
        assert client.post("/generate", json=payload).status_code == 422

        payload["generation"]["response_prefix"] = '{"resultado_hipotese":"'
        assert client.post("/generate", json=payload).status_code == 200


def test_local_gateway_scores_only_authorized_choices(monkeypatch):
    observed = []

    def fake_load(self):
        self.model = object()
        self.processor = object()
        self.load_error = None

    def fake_choose(self, _image, _prompt, choices):
        observed.append(choices)
        return {
            "choice": "B",
            "choice_probabilities": {
                "A": 0.1, "B": 0.8, "C": 0.1,
            },
        }

    monkeypatch.setattr(MedGemmaRuntime, "load", fake_load)
    monkeypatch.setattr(MedGemmaRuntime, "choose", fake_choose)
    app = create_app("configs/medgemma_local_4b.yaml")
    with TestClient(app) as client:
        payload = {
            "contract": "dtwin-medgemma-v1",
            "model_id": "google/medgemma-1.5-4b-it",
            "model_version": "MedGemma 1.5 4B Instruction-Tuned",
            "prompt": "research only",
            "image": {"mime_type": "image/png", "base64": _png_base64()},
            "generation": {
                "max_output_tokens": 1,
                "choices": ["A", "B", "C"],
            },
        }
        response = client.post("/generate", json=payload)
        assert response.status_code == 200
        assert response.json()["choice"] == "B"
        assert observed == [["A", "B", "C"]]

        payload["generation"]["choices"] = ["NEGATIVA", "POSITIVA"]
        assert client.post("/generate", json=payload).status_code == 400


def test_balanced_choice_rotates_every_label_through_every_code(monkeypatch):
    runtime = MedGemmaRuntime({"medgemma": {}})
    seen_prompts = []

    def fake_choose(_image, prompt, choices):
        seen_prompts.append(prompt)
        negative_code = next(code for code in choices if f"{code}=NEGATIVA" in prompt)
        probabilities = {code: 0.1 for code in choices}
        probabilities[negative_code] = 0.8
        return {"choice": negative_code, "choice_probabilities": probabilities}

    monkeypatch.setattr(runtime, "choose", fake_choose)
    result = runtime.choose_balanced(None, "pesquisa")

    assert result["choice"] == "NEGATIVA"
    assert result["choice_probabilities"]["NEGATIVA"] == 0.8
    assert result["choice_aggregation"] == "latin_square_mean_v1"
    assert len(seen_prompts) == 3
    for label in ("POSITIVA", "NEGATIVA", "INCONCLUSIVA"):
        assert sum(f"{code}={label}" in prompt for prompt in seen_prompts for code in "ABC") == 3


def test_local_gateway_forwards_balanced_semantic_choices(monkeypatch):
    def fake_load(self):
        self.model = object()
        self.processor = object()
        self.load_error = None

    def fake_balanced(self, _image, _prompt):
        return {
            "choice": "NEGATIVA",
            "choice_probabilities": {
                "POSITIVA": 0.1, "NEGATIVA": 0.8, "INCONCLUSIVA": 0.1,
            },
            "choice_aggregation": "latin_square_mean_v1",
        }

    monkeypatch.setattr(MedGemmaRuntime, "load", fake_load)
    monkeypatch.setattr(MedGemmaRuntime, "choose_balanced", fake_balanced)
    app = create_app("configs/medgemma_local_4b.yaml")
    with TestClient(app) as client:
        payload = {
            "contract": "dtwin-medgemma-v1",
            "model_id": "google/medgemma-1.5-4b-it",
            "model_version": "MedGemma 1.5 4B Instruction-Tuned",
            "prompt": "research only",
            "image": {"mime_type": "image/png", "base64": _png_base64()},
            "generation": {
                "max_output_tokens": 1,
                "choices": ["POSITIVA", "NEGATIVA", "INCONCLUSIVA"],
                "balanced_choices": True,
            },
        }
        response = client.post("/generate", json=payload)
        assert response.status_code == 200
        assert response.json()["choice"] == "NEGATIVA"


def test_local_gateway_rejects_wrong_model(monkeypatch):
    monkeypatch.setattr(
        MedGemmaRuntime,
        "load",
        lambda self: (setattr(self, "model", object()), setattr(self, "processor", object())),
    )
    app = create_app("configs/medgemma_local_4b.yaml")
    with TestClient(app) as client:
        response = client.post(
            "/generate",
            json={
                "contract": "dtwin-medgemma-v1",
                "model_id": "wrong/model",
                "model_version": "Wrong model",
                "prompt": "research only",
                "image": {"mime_type": "image/png", "base64": _png_base64()},
                "generation": {"max_output_tokens": 32},
            },
        )
        assert response.status_code == 409


def test_local_gateway_rejects_non_png_payload(monkeypatch):
    monkeypatch.setattr(
        MedGemmaRuntime,
        "load",
        lambda self: (setattr(self, "model", object()), setattr(self, "processor", object())),
    )
    app = create_app("configs/medgemma_local_4b.yaml")
    with TestClient(app) as client:
        response = client.post(
            "/generate",
            json={
                "contract": "dtwin-medgemma-v1",
                "model_id": "google/medgemma-1.5-4b-it",
                "model_version": "MedGemma 1.5 4B Instruction-Tuned",
                "prompt": "research only",
                "image": {"mime_type": "image/png", "base64": _jpeg_base64()},
                "generation": {"max_output_tokens": 32},
            },
        )
        assert response.status_code == 400
        assert "PNG" in response.json()["detail"]
