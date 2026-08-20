#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Gateway HTTP local do MedGemma (contrato dtwin-medgemma-v1).

O modelo é carregado com a API oficial Transformers. Em GPU (device=cuda) usa
quantização NF4; em Apple Silicon (device=mps, opt-in de Pesquisa) usa bf16 sem
quantização, com carga integral e as mesmas travas anti-offload. Falhas de
licença, download, device ou memória ficam expostas em /health; nunca há resposta
clínica simulada ou fallback para outro modelo.
"""
from __future__ import annotations

import argparse
import base64
import io
import logging
import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from dtwin.core import PipelineError
from dtwin.medgemma_client import load_screening_config

log = logging.getLogger("dtwin.medgemma.server")


class ImagePayload(BaseModel):
    mime_type: Literal["image/png"]
    base64: str


class GenerationPayload(BaseModel):
    max_output_tokens: int = Field(ge=1)
    response_prefix: Literal["{", '{"resultado_hipotese":"'] | None = None
    choices: list[str] | None = None
    balanced_choices: bool = False


class GeneratePayload(BaseModel):
    contract: Literal["dtwin-medgemma-v1"]
    model_id: str
    model_version: str
    prompt: str
    image: ImagePayload
    generation: GenerationPayload


class VolumeImagePayload(BaseModel):
    """Imagem axial anônima; campos extras (nomes/UIDs) são proibidos."""

    model_config = ConfigDict(extra="forbid")

    mime_type: Literal["image/png"]
    base64: str


class VolumeGenerationPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_output_tokens: int = Field(ge=1)
    response_prefix: Literal["{", '{"resultado_hipotese":"'] | None = None


class VolumeGeneratePayload(BaseModel):
    """Contrato isolado para a representação 3D nativa do MedGemma 1.5."""

    model_config = ConfigDict(extra="forbid")

    contract: Literal["dtwin-medgemma-volume-v1"]
    model_id: str
    model_version: str
    instruction: str = Field(min_length=1)
    images: list[VolumeImagePayload] = Field(min_length=5, max_length=85)
    query: str = Field(min_length=1)
    generation: VolumeGenerationPayload


def _build_volume_messages(images: list, instruction: str, query: str) -> list[dict]:
    """Monta a sequência oficial: instrução, imagem/rótulo por corte e consulta."""

    safe_instruction = (
        "Você é um assistente de pesquisa em imagem médica. "
        "Não emita diagnóstico definitivo nem recomendação clínica.\n\n" + instruction
    )
    content: list[dict] = [{"type": "text", "text": safe_instruction}]
    for index, image in enumerate(images, start=1):
        content.append({"type": "image", "image": image})
        content.append({"type": "text", "text": f"SLICE {index}"})
    content.append({"type": "text", "text": query})
    return [{"role": "user", "content": content}]


class MedGemmaRuntime:
    def __init__(self, config: dict):
        self.config = config
        self.med = config["medgemma"]
        self.model = None
        self.processor = None
        self.load_error: str | None = None
        self.lock = threading.Lock()
        self.last_generation_timings: dict[str, float] = {}

    @property
    def loaded(self) -> bool:
        return self.model is not None and self.processor is not None

    def load(self) -> None:
        try:
            import torch
            from transformers import (
                AutoModelForImageTextToText,
                AutoProcessor,
                BitsAndBytesConfig,
            )

            device = self.med.get("device")
            quantization = self.med.get("quantization")
            model_id = self.med["model_id"]
            local_files_only = bool(self.med.get("local_files_only", False))

            if device == "cuda":
                if not torch.cuda.is_available():
                    raise RuntimeError("CUDA não está disponível; CPU fallback é proibido.")
                minimum_vram = float(self.med.get("minimum_cuda_memory_gb", 6.0))
                available_vram = torch.cuda.get_device_properties(0).total_memory / (1024**3)
                if available_vram < minimum_vram:
                    raise RuntimeError(
                        f"VRAM insuficiente ({available_vram:.1f} GiB < {minimum_vram:.1f} GiB)."
                    )
                if not torch.cuda.is_bf16_supported():
                    raise RuntimeError("A GPU não oferece suporte BF16 exigido pelo backend.")
                kwargs = {"dtype": torch.bfloat16, "device_map": "auto"}
                if quantization == "bitsandbytes-nf4":
                    kwargs["quantization_config"] = BitsAndBytesConfig(
                        load_in_4bit=True,
                        bnb_4bit_quant_type="nf4",
                        bnb_4bit_compute_dtype=torch.bfloat16,
                        bnb_4bit_use_double_quant=True,
                    )
                elif quantization not in {None, "none"}:
                    raise RuntimeError(f"Quantização não suportada: {quantization!r}")
            elif device == "mps":
                # Opt-in explícito para Apple Silicon (modo Pesquisa): carga INTEGRAL
                # em MPS, bf16, SEM quantização (bitsandbytes exige CUDA) e SEM
                # device_map/offload. As mesmas travas anti-fallback do caminho CUDA
                # continuam valendo — nenhuma parte do modelo vai para CPU/disco.
                if not torch.backends.mps.is_available():
                    raise RuntimeError("MPS não está disponível; verifique PyTorch/hardware.")
                if quantization not in {None, "none"}:
                    raise RuntimeError(
                        "Quantização bitsandbytes não é suportada em MPS; use quantization: none."
                    )
                kwargs = {"dtype": torch.bfloat16}
            else:
                raise RuntimeError("device deve ser 'cuda' ou 'mps'.")

            log.info(
                "Carregando %s (%s, device=%s)...",
                model_id, quantization or "sem quantização", device,
            )
            self.processor = AutoProcessor.from_pretrained(
                model_id, local_files_only=local_files_only
            )
            self.model = AutoModelForImageTextToText.from_pretrained(
                model_id, local_files_only=local_files_only, **kwargs
            )
            device_map = getattr(self.model, "hf_device_map", {}) or {}
            forbidden_devices = {
                str(dev).lower()
                for dev in device_map.values()
                if str(dev).lower() in {"cpu", "disk"}
            }
            if forbidden_devices:
                raise RuntimeError(
                    "O modelo foi parcialmente descarregado para CPU/disco; "
                    "fallback é proibido neste backend."
                )
            if device == "mps":
                self.model = self.model.to("mps")
                if getattr(self.model.device, "type", None) != "mps":
                    raise RuntimeError("O modelo não foi carregado integralmente em MPS.")
            elif not device_map and getattr(self.model.device, "type", None) != "cuda":
                raise RuntimeError("O modelo não foi carregado integralmente na GPU.")
            self.model.eval()
        except AttributeError:
            # Nome correto nas versões atuais; bloco separado mantém a falha clara
            # caso uma versão incompatível de Transformers seja instalada.
            self.model = None
            self.processor = None
            self.load_error = (
                "Transformers incompatível: AutoModelForImageTextToText indisponível. "
                "Reinstale o extra [medgemma]."
            )
            log.exception(self.load_error)
            return
        except Exception as exc:
            self.model = None
            self.processor = None
            self.load_error = f"{type(exc).__name__}: {exc}"
            log.exception("Falha ao carregar MedGemma")
            return
        self.load_error = None
        log.info("MedGemma carregado com sucesso (device=%s).", self.med.get("device"))

    def generate(
        self,
        image,
        prompt: str,
        max_new_tokens: int,
        response_prefix: str | None = None,
    ) -> str:
        if not self.loaded:
            raise RuntimeError(self.load_error or "Modelo não carregado.")
        import torch

        # O template oficial do MedGemma 1.5 usa uma única mensagem `user`.
        # Manter as salvaguardas no próprio texto evita incompatibilidade com
        # templates Gemma que não aceitam a função `system`.
        safe_prompt = (
            "Você é um assistente de pesquisa em imagem médica. "
            "Não emita diagnóstico definitivo nem recomendação clínica.\n\n" + prompt
        )
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "image", "image": image},
                    {"type": "text", "text": safe_prompt},
                ],
            }
        ]
        waiting_started = time.monotonic()
        with self.lock, torch.inference_mode():
            generation_started = time.monotonic()
            inputs = self.processor.apply_chat_template(
                messages,
                add_generation_prompt=True,
                tokenize=True,
                return_dict=True,
                return_tensors="pt",
            ).to(self.model.device)
            if response_prefix:
                # Prefixo causal: o modo compacto começa dentro do objeto JSON,
                # impedindo que o orçamento curto seja consumido por preâmbulo.
                prefix_ids = self.processor.tokenizer(
                    response_prefix,
                    add_special_tokens=False,
                    return_tensors="pt",
                )["input_ids"].to(self.model.device)
                if prefix_ids.shape[0] != inputs["input_ids"].shape[0]:
                    raise RuntimeError("Batch incompatível ao aplicar response_prefix.")
                inputs["input_ids"] = torch.cat((inputs["input_ids"], prefix_ids), dim=-1)
                if "attention_mask" in inputs:
                    prefix_mask = torch.ones_like(prefix_ids, device=self.model.device)
                    inputs["attention_mask"] = torch.cat(
                        (inputs["attention_mask"], prefix_mask), dim=-1
                    )
            input_len = inputs["input_ids"].shape[-1]
            generated = self.model.generate(
                **inputs,
                max_new_tokens=max_new_tokens,
                do_sample=False,
            )[0][input_len:]
            output = (
                (response_prefix or "")
                + self.processor.decode(generated, skip_special_tokens=True).strip()
            )
            self.last_generation_timings = {
                "queue_seconds": round(generation_started - waiting_started, 4),
                "generation_seconds": round(time.monotonic() - generation_started, 4),
            }
            return output

    def generate_volume(
        self,
        images: list,
        instruction: str,
        query: str,
        max_new_tokens: int,
        response_prefix: str | None = None,
    ) -> str:
        """Gera uma resposta única a partir de 5–85 cortes axiais ordenados."""

        if not self.loaded:
            raise RuntimeError(self.load_error or "Modelo não carregado.")
        import torch

        messages = _build_volume_messages(images, instruction, query)
        waiting_started = time.monotonic()
        with self.lock, torch.inference_mode():
            generation_started = time.monotonic()
            inputs = self.processor.apply_chat_template(
                messages,
                add_generation_prompt=True,
                tokenize=True,
                return_dict=True,
                return_tensors="pt",
            ).to(self.model.device)
            if response_prefix:
                prefix_ids = self.processor.tokenizer(
                    response_prefix,
                    add_special_tokens=False,
                    return_tensors="pt",
                )["input_ids"].to(self.model.device)
                if prefix_ids.shape[0] != inputs["input_ids"].shape[0]:
                    raise RuntimeError("Batch incompatível ao aplicar response_prefix.")
                inputs["input_ids"] = torch.cat((inputs["input_ids"], prefix_ids), dim=-1)
                if "attention_mask" in inputs:
                    prefix_mask = torch.ones_like(prefix_ids, device=self.model.device)
                    inputs["attention_mask"] = torch.cat(
                        (inputs["attention_mask"], prefix_mask), dim=-1
                    )
            input_len = inputs["input_ids"].shape[-1]
            generated = self.model.generate(
                **inputs,
                max_new_tokens=max_new_tokens,
                do_sample=False,
            )[0][input_len:]
            output = (
                (response_prefix or "")
                + self.processor.decode(generated, skip_special_tokens=True).strip()
            )
            self.last_generation_timings = {
                "queue_seconds": round(generation_started - waiting_started, 4),
                "generation_seconds": round(time.monotonic() - generation_started, 4),
            }
            return output

    def choose(self, image, prompt: str, choices: list[str]) -> dict[str, object]:
        """Pontua continuações fechadas sem gerar raciocínio livre."""
        if not self.loaded:
            raise RuntimeError(self.load_error or "Modelo não carregado.")
        import torch

        safe_prompt = (
            "Você é um assistente de pesquisa em imagem médica. "
            "Não emita diagnóstico definitivo nem recomendação clínica.\n\n" + prompt
        )
        messages = [{
            "role": "user",
            "content": [
                {"type": "image", "image": image},
                {"type": "text", "text": safe_prompt},
            ],
        }]
        waiting_started = time.monotonic()
        with self.lock, torch.inference_mode():
            scoring_started = time.monotonic()
            base = self.processor.apply_chat_template(
                messages,
                add_generation_prompt=True,
                tokenize=True,
                return_dict=True,
                return_tensors="pt",
            ).to(self.model.device)
            base_length = base["input_ids"].shape[-1]
            scores: list[float] = []
            for choice in choices:
                choice_ids = self.processor.tokenizer(
                    choice, add_special_tokens=False, return_tensors="pt"
                )["input_ids"].to(self.model.device)
                candidate = dict(base)
                candidate["input_ids"] = torch.cat((base["input_ids"], choice_ids), dim=-1)
                if "attention_mask" in base:
                    candidate["attention_mask"] = torch.cat(
                        (base["attention_mask"], torch.ones_like(choice_ids)), dim=-1
                    )
                if "token_type_ids" in base:
                    candidate["token_type_ids"] = torch.cat(
                        (base["token_type_ids"], torch.zeros_like(choice_ids)), dim=-1
                    )
                output = self.model(**candidate)
                token_logits = output.logits[
                    0, base_length - 1: base_length - 1 + choice_ids.shape[-1], :
                ]
                token_log_probs = torch.log_softmax(token_logits.float(), dim=-1)
                selected = token_log_probs.gather(1, choice_ids[0].unsqueeze(1)).squeeze(1)
                scores.append(float(selected.mean().item()))
                del output
            probabilities = torch.softmax(torch.tensor(scores, dtype=torch.float32), dim=0)
            best_index = int(torch.argmax(probabilities).item())
            self.last_generation_timings = {
                "queue_seconds": round(scoring_started - waiting_started, 4),
                "generation_seconds": round(time.monotonic() - scoring_started, 4),
            }
            return {
                "choice": choices[best_index],
                "choice_probabilities": {
                    choice: round(float(probabilities[index].item()), 6)
                    for index, choice in enumerate(choices)
                },
            }

    def choose_balanced(self, image, prompt: str) -> dict[str, object]:
        """Contrabalança classe, código e posição por um quadrado latino 3x3."""
        labels = ["POSITIVA", "NEGATIVA", "INCONCLUSIVA"]
        mappings = [
            {"A": labels[0], "B": labels[1], "C": labels[2]},
            {"A": labels[1], "B": labels[2], "C": labels[0]},
            {"A": labels[2], "B": labels[0], "C": labels[1]},
        ]
        started = time.monotonic()
        totals = {label: 0.0 for label in labels}
        rounds: list[dict[str, object]] = []
        for mapping in mappings:
            mapped_prompt = (
                f"{prompt}\n\nMAPEAMENTO DESTA RODADA: "
                f"A={mapping['A']}; B={mapping['B']}; C={mapping['C']}. "
                "A resposta permitida é somente A, B ou C."
            )
            result = self.choose(image, mapped_prompt, ["A", "B", "C"])
            code_probabilities = result["choice_probabilities"]
            for code, label in mapping.items():
                totals[label] += float(code_probabilities[code])
            rounds.append({
                "mapping": mapping,
                "choice_probabilities": code_probabilities,
            })
        probabilities = {label: round(totals[label] / 3.0, 6) for label in labels}
        choice = max(labels, key=lambda label: probabilities[label])
        self.last_generation_timings = {
            "queue_seconds": 0.0,
            "generation_seconds": round(time.monotonic() - started, 4),
        }
        return {
            "choice": choice,
            "choice_probabilities": probabilities,
            "choice_rounds": rounds,
            "choice_aggregation": "latin_square_mean_v1",
        }


class OllamaRuntime:
    """Runtime que delega a inferência a um daemon Ollama local (GGUF/Metal).

    Expõe a mesma interface interna de MedGemmaRuntime (``loaded``/``load``/
    ``generate``), mas em vez de carregar o modelo em processo via Transformers,
    encaminha imagem+prompt para a API do Ollama. Continua modo PESQUISA e
    fail-closed: se o daemon não responder, a tag não existir ou não tiver
    capacidade de visão, ``load_error`` é setado e ``/health`` expõe a falha.
    Nunca há resposta clínica simulada nem fallback para outro modelo.
    """

    def __init__(self, config: dict):
        self.config = config
        self.med = config["medgemma"]
        self.load_error: str | None = None
        self._ready = False
        self.lock = threading.Lock()
        self.base_url = str(self.med.get("ollama_url", "http://127.0.0.1:11434")).rstrip("/")
        self.tag = str(self.med.get("ollama_model") or self.med["model_id"])

    @property
    def loaded(self) -> bool:
        return self._ready

    def unload(self) -> None:
        self._ready = False

    def load(self) -> None:
        import json as _json
        from urllib.error import HTTPError, URLError
        from urllib.request import Request, urlopen

        try:
            request = Request(
                f"{self.base_url}/api/show",
                data=_json.dumps({"name": self.tag}).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urlopen(request, timeout=20) as response:
                info = _json.loads(response.read().decode("utf-8"))
            capabilities = info.get("capabilities") or []
            if "vision" not in capabilities:
                raise RuntimeError(
                    f"Modelo Ollama '{self.tag}' não declara capacidade de visão "
                    f"(capabilities={capabilities}); o painel exige um modelo image-text."
                )
            self._ready = True
            self.load_error = None
            log.info(
                "Ollama runtime pronto: tag=%s em %s (capabilities=%s).",
                self.tag, self.base_url, capabilities,
            )
        except (HTTPError, URLError, TimeoutError, OSError, ValueError) as exc:
            self._ready = False
            self.load_error = f"{type(exc).__name__}: {exc}"
            log.exception("Falha ao preparar o runtime Ollama")

    def generate(
        self,
        image,
        prompt: str,
        max_new_tokens: int,
        response_prefix: str | None = None,
    ) -> str:
        if response_prefix is not None:
            raise RuntimeError("response_prefix não é suportado pelo runtime Ollama.")
        import base64 as _b64
        import io as _io
        import json as _json
        from urllib.request import Request, urlopen

        if not self._ready:
            raise RuntimeError(self.load_error or "Ollama runtime não pronto.")
        # Mesmas salvaguardas no texto do caminho Transformers (template Gemma sem
        # função `system`).
        safe_prompt = (
            "Você é um assistente de pesquisa em imagem médica. "
            "Não emita diagnóstico definitivo nem recomendação clínica.\n\n" + prompt
        )
        buffer = _io.BytesIO()
        image.save(buffer, format="PNG")
        image_b64 = _b64.b64encode(buffer.getvalue()).decode("ascii")
        payload = {
            "model": self.tag,
            "messages": [
                {"role": "user", "content": safe_prompt, "images": [image_b64]}
            ],
            "stream": False,
            "options": {"temperature": 0, "num_predict": int(max_new_tokens)},
        }
        request = Request(
            f"{self.base_url}/api/chat",
            data=_json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        timeout = int(self.med.get("timeout_seconds", 600))
        with self.lock, urlopen(request, timeout=timeout) as response:
            data = _json.loads(response.read().decode("utf-8"))
        return str((data.get("message") or {}).get("content", "")).strip()

    def choose(self, image, prompt: str, choices: list[str]) -> dict[str, object]:
        raise RuntimeError("Escolha restrita não é suportada pelo runtime Ollama.")

    def choose_balanced(self, image, prompt: str) -> dict[str, object]:
        raise RuntimeError("Escolha contrabalançada não é suportada pelo runtime Ollama.")


def _build_runtime(config: dict):
    """Escolhe o runtime pelo campo medgemma.runtime (transformers|ollama)."""
    kind = str(config["medgemma"].get("runtime", "transformers")).lower()
    if kind == "ollama":
        return OllamaRuntime(config)
    if kind == "transformers":
        return MedGemmaRuntime(config)
    raise PipelineError(f"medgemma.runtime desconhecido: {kind!r} (use transformers ou ollama).")


def create_app(config_path: Path):
    try:
        from fastapi import FastAPI, HTTPException
    except ImportError as exc:
        raise PipelineError("Backend ausente. Instale com: pip install -e .[medgemma]") from exc
    from PIL import Image

    config = load_screening_config(config_path)
    runtime = _build_runtime(config)

    @asynccontextmanager
    async def lifespan(_app):
        runtime.load()
        yield
        if hasattr(runtime, "unload"):
            runtime.unload()
        else:
            runtime.model = None
            runtime.processor = None

    app = FastAPI(title="Digital Twin MedGemma Gateway", version="1", lifespan=lifespan)

    @app.get("/health")
    def health():
        # O runtime Ollama nao depende de PyTorch neste processo. O health deve
        # continuar acessivel em uma instalacao minima e expor o erro real do
        # runtime Transformers quando torch ainda nao estiver instalado.
        try:
            import torch
        except ImportError:
            torch = None

        return {
            "status": "ready" if runtime.loaded else "failed",
            "contract": "dtwin-medgemma-v1",
            "volume_contract": "dtwin-medgemma-volume-v1",
            "volume_supported": isinstance(runtime, MedGemmaRuntime),
            "model_loaded": runtime.loaded,
            "model_id": runtime.med["model_id"],
            "model_version": runtime.med["model_version"],
            "quantization": runtime.med.get("quantization"),
            "device": runtime.med.get("device"),
            "cuda_available": bool(torch and torch.cuda.is_available()),
            "mps_available": bool(
                torch
                and hasattr(torch.backends, "mps")
                and torch.backends.mps.is_available()
            ),
            "gpu": (
                torch.cuda.get_device_name(0)
                if torch and torch.cuda.is_available()
                else None
            ),
            "load_error": runtime.load_error,
            "research_only": True,
        }

    @app.post("/generate")
    def generate(payload: GeneratePayload):
        if not runtime.loaded:
            raise HTTPException(status_code=503, detail=runtime.load_error or "Modelo não carregado")
        if payload.model_id != runtime.med["model_id"]:
            raise HTTPException(status_code=409, detail="model_id não corresponde ao modelo carregado")
        if payload.model_version != runtime.med["model_version"]:
            raise HTTPException(status_code=409, detail="model_version não corresponde ao modelo carregado")
        if len(payload.prompt) > int(runtime.med.get("max_prompt_chars", 12000)):
            raise HTTPException(status_code=413, detail="Prompt excede max_prompt_chars")
        allowed_choices = ["A", "B", "C"]
        semantic_choices = ["POSITIVA", "NEGATIVA", "INCONCLUSIVA"]
        if payload.generation.choices is not None:
            expected = semantic_choices if payload.generation.balanced_choices else allowed_choices
            if payload.generation.choices != expected:
                raise HTTPException(status_code=400, detail="choices não autorizadas")
            if payload.generation.response_prefix is not None:
                raise HTTPException(
                    status_code=400,
                    detail="choices e response_prefix são mutuamente exclusivos",
                )
        try:
            raw = base64.b64decode(payload.image.base64, validate=True)
            if len(raw) > int(runtime.med["max_input_bytes"]):
                raise ValueError("Imagem excede max_input_bytes")
            source = Image.open(io.BytesIO(raw))
            if source.format != "PNG":
                raise ValueError("A imagem deve ser um PNG válido")
            width, height = source.size
            if width * height > int(runtime.med.get("max_image_pixels", 4_000_000)):
                raise ValueError("Imagem excede max_image_pixels")
            source.load()
            image = source.convert("RGB")
            max_tokens = min(
                int(payload.generation.max_output_tokens),
                int(runtime.med["max_output_tokens"]),
            )
            if payload.generation.balanced_choices:
                selection = runtime.choose_balanced(image, payload.prompt)
                output = None
            elif payload.generation.choices is not None:
                selection = runtime.choose(image, payload.prompt, payload.generation.choices)
                output = None
            else:
                selection = None
                output = runtime.generate(
                    image,
                    payload.prompt,
                    max_tokens,
                    payload.generation.response_prefix,
                )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            log.exception("Falha de inferência MedGemma")
            raise HTTPException(status_code=500, detail=f"Inferência falhou: {type(exc).__name__}") from exc
        response = {
            "model_id": runtime.med["model_id"],
            "model_version": runtime.med["model_version"],
            "output": output,
        }
        if selection is not None:
            response.update(selection)
        timings = getattr(runtime, "last_generation_timings", None)
        if isinstance(timings, dict) and timings:
            response["timings_seconds"] = timings
        return response

    @app.post("/generate-volume")
    def generate_volume(payload: VolumeGeneratePayload):
        if not isinstance(runtime, MedGemmaRuntime):
            raise HTTPException(
                status_code=501,
                detail="Entrada volumétrica exige o runtime Transformers.",
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

        images = []
        total_bytes = 0
        total_pixels = 0
        per_image_bytes = int(runtime.med["max_input_bytes"])
        per_image_pixels = min(
            int(runtime.med.get("max_image_pixels", 4_000_000)),
            512 * 512,
        )
        max_total_bytes = int(runtime.med.get("max_volume_input_bytes", 96 * 1024 * 1024))
        max_total_pixels = int(runtime.med.get("max_volume_pixels", 85 * 512 * 512))
        try:
            for position, encoded in enumerate(payload.images, start=1):
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
                    if width > 512 or height > 512:
                        raise ValueError(f"Corte {position} excede 512x512 pixels")
                    pixels = width * height
                    if pixels > per_image_pixels:
                        raise ValueError(f"Corte {position} excede max_image_pixels")
                    total_pixels += pixels
                    if total_pixels > max_total_pixels:
                        raise ValueError("Volume excede max_volume_pixels")
                    source.load()
                    images.append(source.convert("RGB").copy())

            max_tokens = min(
                int(payload.generation.max_output_tokens),
                int(runtime.med["max_output_tokens"]),
            )
            output = runtime.generate_volume(
                images,
                payload.instruction,
                payload.query,
                max_tokens,
                payload.generation.response_prefix,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            log.exception("Falha de inferência volumétrica MedGemma")
            raise HTTPException(
                status_code=500,
                detail=f"Inferência volumétrica falhou: {type(exc).__name__}",
            ) from exc

        response = {
            "contract": "dtwin-medgemma-volume-v1",
            "model_id": runtime.med["model_id"],
            "model_version": runtime.med["model_version"],
            "slice_count": len(images),
            "output": output,
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
    if args.host not in {"127.0.0.1", "localhost", "::1"}:
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
