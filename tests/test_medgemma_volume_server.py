import base64
import io

from fastapi.testclient import TestClient
from PIL import Image

import tools.medgemma_server as server
from tools.medgemma_server import MedGemmaRuntime, _build_volume_messages, create_app


def _image_base64(*, size=(16, 16), format="PNG"):
    stream = io.BytesIO()
    Image.new("RGB", size, "black").save(stream, format=format)
    return base64.b64encode(stream.getvalue()).decode("ascii")


def _payload(*, count=5, encoded=None):
    value = encoded or _image_base64()
    return {
        "contract": "dtwin-medgemma-volume-v1",
        "model_id": "google/medgemma-1.5-4b-it",
        "model_version": "MedGemma 1.5 4B Instruction-Tuned",
        "instruction": "Avalie a pilha axial exclusivamente para pesquisa.",
        "images": [
            {"mime_type": "image/png", "base64": value}
            for _ in range(count)
        ],
        "query": "Responda com o objeto estruturado solicitado.",
        "generation": {"max_output_tokens": 32},
    }


def _patch_runtime(monkeypatch, observed=None):
    def fake_load(self):
        self.model = object()
        self.processor = object()
        self.load_error = None

    def fake_generate_volume(
        self, images, instruction, query, tokens, response_prefix=None
    ):
        if observed is not None:
            observed.update(
                images=images,
                instruction=instruction,
                query=query,
                tokens=tokens,
                response_prefix=response_prefix,
            )
        self.last_generation_timings = {
            "queue_seconds": 0.1,
            "generation_seconds": 2.0,
        }
        return '{"resultado_hipotese":"INCONCLUSIVA"}'

    monkeypatch.setattr(MedGemmaRuntime, "load", fake_load)
    monkeypatch.setattr(MedGemmaRuntime, "generate_volume", fake_generate_volume)


def test_volume_messages_follow_official_interleaving():
    images = [object(), object(), object()]
    messages = _build_volume_messages(images, "INSTRUCAO", "CONSULTA")

    assert len(messages) == 1
    assert messages[0]["role"] == "user"
    content = messages[0]["content"]
    assert content[0]["type"] == "text"
    assert content[0]["text"].endswith("INSTRUCAO")
    assert content[-1] == {"type": "text", "text": "CONSULTA"}
    assert content[1:7] == [
        {"type": "image", "image": images[0]},
        {"type": "text", "text": "SLICE 1"},
        {"type": "image", "image": images[1]},
        {"type": "text", "text": "SLICE 2"},
        {"type": "image", "image": images[2]},
        {"type": "text", "text": "SLICE 3"},
    ]


def test_volume_endpoint_accepts_five_ordered_pngs(monkeypatch):
    observed = {}
    _patch_runtime(monkeypatch, observed)
    app = create_app("configs/medgemma_local_4b.yaml")

    with TestClient(app) as client:
        health = client.get("/health")
        assert health.status_code == 200
        assert health.json()["contract"] == "dtwin-medgemma-v1"
        assert health.json()["volume_contract"] == "dtwin-medgemma-volume-v1"
        assert health.json()["volume_supported"] is True

        response = client.post("/generate-volume", json=_payload())

    assert response.status_code == 200
    body = response.json()
    assert body["contract"] == "dtwin-medgemma-volume-v1"
    assert body["slice_count"] == 5
    assert body["research_only"] is True
    assert body["clinical_use_allowed"] is False
    assert body["requires_human_review"] is True
    assert body["timings_seconds"]["generation_seconds"] == 2.0
    assert len(observed["images"]) == 5
    assert all(image.mode == "RGB" for image in observed["images"])
    assert observed["tokens"] == 32


def test_volume_endpoint_enforces_five_to_eighty_five_images(monkeypatch):
    _patch_runtime(monkeypatch)
    app = create_app("configs/medgemma_local_4b.yaml")

    with TestClient(app) as client:
        assert client.post("/generate-volume", json=_payload(count=4)).status_code == 422
        assert client.post("/generate-volume", json=_payload(count=86)).status_code == 422


def test_volume_endpoint_rejects_non_png_and_over_512(monkeypatch):
    _patch_runtime(monkeypatch)
    app = create_app("configs/medgemma_local_4b.yaml")

    with TestClient(app) as client:
        jpeg = client.post(
            "/generate-volume",
            json=_payload(encoded=_image_base64(format="JPEG")),
        )
        too_large = client.post(
            "/generate-volume",
            json=_payload(encoded=_image_base64(size=(513, 1))),
        )

    assert jpeg.status_code == 400
    assert "PNG" in jpeg.json()["detail"]
    assert too_large.status_code == 400
    assert "512x512" in too_large.json()["detail"]


def test_volume_endpoint_forbids_phi_bearing_extra_fields(monkeypatch):
    _patch_runtime(monkeypatch)
    app = create_app("configs/medgemma_local_4b.yaml")
    payload = _payload()
    payload["images"][0]["filename"] = "patient-name_slice-001.png"

    with TestClient(app) as client:
        response = client.post("/generate-volume", json=payload)

    assert response.status_code == 422


def test_volume_endpoint_rejects_wrong_model(monkeypatch):
    _patch_runtime(monkeypatch)
    app = create_app("configs/medgemma_local_4b.yaml")
    payload = _payload()
    payload["model_id"] = "wrong/model"

    with TestClient(app) as client:
        response = client.post("/generate-volume", json=payload)

    assert response.status_code == 409


def test_volume_endpoint_enforces_aggregate_pixel_limit(monkeypatch):
    _patch_runtime(monkeypatch)
    config = server.load_screening_config("configs/medgemma_local_4b.yaml")
    config["medgemma"]["max_volume_pixels"] = 4 * 16 * 16
    monkeypatch.setattr(server, "load_screening_config", lambda _path: config)
    app = create_app("ignored.yaml")

    with TestClient(app) as client:
        response = client.post("/generate-volume", json=_payload())

    assert response.status_code == 400
    assert "max_volume_pixels" in response.json()["detail"]
