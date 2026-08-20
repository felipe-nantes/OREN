#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Gateway MedGemma compatível com v1/v13 e pontuação volumétrica v14.

O servidor histórico permanece em ``medgemma_server_base``. Esta camada captura
o mesmo runtime carregado por ele e adiciona um contrato isolado de pontuação,
sem carregar uma segunda cópia do modelo e sem alterar as rotas existentes.
"""
from __future__ import annotations

import argparse
import base64
import io
import math
import time
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

import tools.medgemma_server_base as _base
from tools.medgemma_server_base import *

VOLUME_SCORE_CONTRACT = "dtwin-medgemma-volume-score-v1"
VOLUME_SCORE_METHOD = "first_token_restricted_softmax_v1"
VOLUME_SCORE_PREFIX = '{"resultado_hipotese":"'
VOLUME_SCORE_CHOICES = ("POSITIVA", "NEGATIVA", "INCONCLUSIVA")
VOLUME_SCORE_MAX_IMAGE_EDGE = 768

# Compatibilidade com imports usados pelos testes e módulos v13.
_build_volume_messages = _base._build_volume_messages
_build_runtime = _base._build_runtime


class VolumeScoringPayload(BaseModel):
    """Pontuação protegida; o cliente não pode fornecer classes arbitrárias."""

    model_config = ConfigDict(extra="forbid")

    response_prefix: Literal['{"resultado_hipotese":"']


class VolumeScorePayload(BaseModel):
    """Contrato v14 isolado para evidência contínua sobre uma pilha 3D."""

    model_config = ConfigDict(extra="forbid")

    contract: Literal["dtwin-medgemma-volume-score-v1"]
    model_id: str
    model_version: str
    instruction: str = Field(min_length=1)
    images: list[VolumeImagePayload] = Field(min_length=5, max_length=85)
    query: str = Field(min_length=1)
    scoring: VolumeScoringPayload


def _score_volume(
    self,
    images: list,
    instruction: str,
    query: str,
    response_prefix: str,
) -> dict[str, object]:
    """Pontua o primeiro token das três classes em uma única passagem direta."""

    if not self.loaded:
        raise RuntimeError(self.load_error or "Modelo não carregado.")
    if response_prefix != VOLUME_SCORE_PREFIX:
        raise ValueError("response_prefix não autorizado para pontuação volumétrica.")

    import torch

    messages = _build_volume_messages(images, instruction, query)
    waiting_started = time.monotonic()
    with self.lock, torch.inference_mode():
        scoring_started = time.monotonic()
        inputs = self.processor.apply_chat_template(
            messages,
            add_generation_prompt=True,
            tokenize=True,
            return_dict=True,
            return_tensors="pt",
        ).to(self.model.device)
        prefix_ids = self.processor.tokenizer(
            response_prefix,
            add_special_tokens=False,
            return_tensors="pt",
        )["input_ids"].to(self.model.device)
        if prefix_ids.ndim != 2 or prefix_ids.shape[0] != inputs["input_ids"].shape[0]:
            raise ValueError("Batch incompatível ao aplicar response_prefix.")
        if prefix_ids.shape[-1] < 1:
            raise ValueError("response_prefix não produziu tokens.")
        inputs["input_ids"] = torch.cat((inputs["input_ids"], prefix_ids), dim=-1)
        if "attention_mask" in inputs:
            inputs["attention_mask"] = torch.cat(
                (
                    inputs["attention_mask"],
                    torch.ones_like(prefix_ids, device=self.model.device),
                ),
                dim=-1,
            )
        if "token_type_ids" in inputs:
            inputs["token_type_ids"] = torch.cat(
                (
                    inputs["token_type_ids"],
                    torch.zeros_like(prefix_ids, device=self.model.device),
                ),
                dim=-1,
            )

        token_ids: list[int] = []
        token_metadata: dict[str, dict[str, int]] = {}
        for label in VOLUME_SCORE_CHOICES:
            encoded = self.processor.tokenizer(
                label,
                add_special_tokens=False,
                return_tensors="pt",
            )["input_ids"]
            if encoded.ndim != 2 or encoded.shape[0] != 1 or encoded.shape[-1] < 1:
                raise ValueError(f"Classe {label} não produziu tokens válidos.")
            first_token_id = int(encoded[0, 0].item())
            token_ids.append(first_token_id)
            token_metadata[label] = {
                "first_token_id": first_token_id,
                "token_count": int(encoded.shape[-1]),
            }
        if len(set(token_ids)) != len(VOLUME_SCORE_CHOICES):
            raise ValueError("Os primeiros tokens das classes devem ser distintos.")

        output = self.model(**inputs)
        last_logits = output.logits[0, -1, :].float()
        if any(token_id < 0 or token_id >= last_logits.shape[-1] for token_id in token_ids):
            raise ValueError("Token de classe fora do vocabulário do modelo.")
        selected_logits = torch.stack([last_logits[token_id] for token_id in token_ids])
        if not bool(torch.isfinite(selected_logits).all().item()):
            raise ValueError("Logits das classes devem ser finitos.")
        probabilities = torch.softmax(selected_logits, dim=0)
        if not bool(torch.isfinite(probabilities).all().item()):
            raise ValueError("Probabilidades das classes devem ser finitas.")

        probability_values = [float(value.item()) for value in probabilities]
        if (
            any(value < 0.0 or value > 1.0 for value in probability_values)
            or not math.isclose(sum(probability_values), 1.0, rel_tol=0.0, abs_tol=1e-6)
        ):
            raise ValueError("Probabilidades restritas não formam distribuição válida.")
        best_index = int(torch.argmax(probabilities).item())
        maximum = selected_logits[best_index]
        tie_detected = int(torch.sum(selected_logits == maximum).item()) > 1
        self.last_generation_timings = {
            "queue_seconds": round(scoring_started - waiting_started, 4),
            "generation_seconds": round(time.monotonic() - scoring_started, 4),
        }
        return {
            "choice": VOLUME_SCORE_CHOICES[best_index],
            "choice_probabilities": {
                label: round(probability_values[index], 8)
                for index, label in enumerate(VOLUME_SCORE_CHOICES)
            },
            "scoring_method": VOLUME_SCORE_METHOD,
            "choice_token_metadata": token_metadata,
            "tie_detected": tie_detected,
        }


# O runtime capturado pelo servidor base é a mesma classe; acrescentar o método
# aqui evita uma segunda carga do modelo e preserva os endpoints anteriores.
MedGemmaRuntime.score_volume = _score_volume


def _augment_health_route(app, runtime) -> None:
    for route in app.routes:
        if getattr(route, "path", None) != "/health" or not hasattr(route, "dependant"):
            continue
        original = route.dependant.call

        def health_with_volume_score(_original=original):
            result = _original()
            if isinstance(result, dict):
                result = dict(result)
                result.update(
                    volume_score_contract=VOLUME_SCORE_CONTRACT,
                    volume_score_supported=isinstance(runtime, MedGemmaRuntime),
                    volume_score_method=VOLUME_SCORE_METHOD,
                    volume_score_max_image_edge=VOLUME_SCORE_MAX_IMAGE_EDGE,
                )
            return result

        route.endpoint = health_with_volume_score
        route.dependant.call = health_with_volume_score
        return
    raise PipelineError("Rota /health ausente no gateway MedGemma base.")


def create_app(config_path: Path):
    """Cria o app histórico e anexa o endpoint v14 ao mesmo runtime."""

    captured: dict[str, object] = {}
    original_builder = _base._build_runtime
    original_loader = _base.load_screening_config

    def capture_runtime(config: dict):
        runtime = original_builder(config)
        captured["runtime"] = runtime
        return runtime

    # Sincroniza o loader para preservar monkeypatches e comportamento legado.
    _base.load_screening_config = load_screening_config
    _base._build_runtime = capture_runtime
    try:
        app = _base.create_app(config_path)
    finally:
        _base._build_runtime = original_builder
        _base.load_screening_config = original_loader
    runtime = captured.get("runtime")
    if runtime is None:
        raise PipelineError("Runtime MedGemma não foi capturado na criação do app.")

    from fastapi import HTTPException
    from PIL import Image

    _augment_health_route(app, runtime)

    def decode_images(payload_images: list[VolumeImagePayload]) -> list:
        images = []
        total_bytes = 0
        total_pixels = 0
        per_image_bytes = int(runtime.med["max_input_bytes"])
        per_image_pixels = min(
            int(runtime.med.get("max_image_pixels", 4_000_000)),
            VOLUME_SCORE_MAX_IMAGE_EDGE * VOLUME_SCORE_MAX_IMAGE_EDGE,
        )
        max_total_bytes = int(runtime.med.get("max_volume_input_bytes", 96 * 1024 * 1024))
        max_total_pixels = int(runtime.med.get("max_volume_pixels", 85 * 512 * 512))
        for position, encoded in enumerate(payload_images, start=1):
            raw = base64.b64decode(encoded.base64, validate=True)
            if len(raw) > per_image_bytes:
                raise ValueError(f"Corte {position} excede max_input_bytes")
            total_bytes += len(raw)
            if total_bytes > max_total_bytes:
                raise ValueError("Volume excede max_volume_input_bytes")
            with Image.open(io.BytesIO(raw)) as source:
                if source.format != "PNG":
                    raise ValueError(f"Corte {position} deve ser um PNG válido")
                width, height = source.size
                if width > VOLUME_SCORE_MAX_IMAGE_EDGE or height > VOLUME_SCORE_MAX_IMAGE_EDGE:
                    raise ValueError(
                        f"Corte {position} excede {VOLUME_SCORE_MAX_IMAGE_EDGE}x"
                        f"{VOLUME_SCORE_MAX_IMAGE_EDGE} pixels"
                    )
                pixels = width * height
                if pixels > per_image_pixels:
                    raise ValueError(f"Corte {position} excede max_image_pixels")
                total_pixels += pixels
                if total_pixels > max_total_pixels:
                    raise ValueError("Volume excede max_volume_pixels")
                source.load()
                images.append(source.convert("RGB").copy())
        return images

    @app.post("/score-volume")
    def score_volume(payload: VolumeScorePayload):
        if not isinstance(runtime, MedGemmaRuntime):
            raise HTTPException(
                status_code=501,
                detail="Pontuação volumétrica exige o runtime Transformers.",
            )
        if not runtime.loaded:
            raise HTTPException(status_code=503, detail=runtime.load_error or "Modelo não carregado")
        if payload.model_id != runtime.med["model_id"]:
            raise HTTPException(status_code=409, detail="model_id não corresponde ao modelo carregado")
        if payload.model_version != runtime.med["model_version"]:
            raise HTTPException(status_code=409, detail="model_version não corresponde ao modelo carregado")
        prompt_chars = len(payload.instruction) + len(payload.query)
        if prompt_chars > int(runtime.med.get("max_prompt_chars", 12000)):
            raise HTTPException(status_code=413, detail="Instrução e consulta excedem max_prompt_chars")
        try:
            images = decode_images(payload.images)
            selection = runtime.score_volume(
                images,
                payload.instruction,
                payload.query,
                payload.scoring.response_prefix,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            log.exception("Falha de pontuação volumétrica MedGemma")
            raise HTTPException(
                status_code=500,
                detail=f"Pontuação volumétrica falhou: {type(exc).__name__}",
            ) from exc

        response = {
            "contract": VOLUME_SCORE_CONTRACT,
            "model_id": runtime.med["model_id"],
            "model_version": runtime.med["model_version"],
            "slice_count": len(images),
            **selection,
            "research_only": True,
            "clinical_use_allowed": False,
            "requires_human_review": True,
        }
        timings = getattr(runtime, "last_generation_timings", None)
        if isinstance(timings, dict) and timings:
            response["timings_seconds"] = timings
        return response

    return app


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Backend local MedGemma (modo Pesquisa).")
    parser.add_argument("--config", default="configs/medgemma_local_4b.yaml")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8001)
    args = parser.parse_args(argv)
    # Runtime nativo apenas: a interface fica restrita a loopback, sem excecao
    # (o Docker antigo abria 0.0.0.0 dentro da rede privada do container; sem
    # Docker essa excecao deixa de existir).
    allowed_hosts = {"127.0.0.1", "localhost", "::1"}
    if args.host not in allowed_hosts:
        print("[ABORTADO] O backend local só pode escutar em loopback.")
        return 1
    try:
        import uvicorn

        app = create_app(Path(args.config))
    except PipelineError as exc:
        print(f"[ABORTADO] {exc}")
        return 1
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
