#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Pontuação MedSigLIP zero-shot para pesquisa, sem emitir diagnóstico."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import yaml
from PIL import Image

from .core import PipelineError, sha256_of


@dataclass(frozen=True)
class MedSigLIPConfig:
    model_id: str
    positive_prompts: tuple[str, ...]
    negative_prompts: tuple[str, ...]
    exploratory_threshold: float
    minimum_adjacent_axial_tiles: int
    decision_enabled: bool


@dataclass(frozen=True)
class PanelViews:
    axial: tuple[Image.Image, ...]
    coronal: Image.Image
    sagittal: Image.Image

    @property
    def all_views(self) -> tuple[Image.Image, ...]:
        return self.axial + (self.coronal, self.sagittal)


def load_medsiglip_config(path: Path | str) -> MedSigLIPConfig:
    source = Path(path)
    try:
        raw = yaml.safe_load(source.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise PipelineError(f"Config MedSigLIP inválida: {exc}") from exc
    if not isinstance(raw, dict) or raw.get("schema") != "argos-medsiglip-zero-shot-v1":
        raise PipelineError("Schema MedSigLIP ausente ou incompatível.")
    if raw.get("research_only") is not True or raw.get("clinical_use_allowed") is not False:
        raise PipelineError("MedSigLIP deve permanecer research_only e sem uso clínico.")
    prompts = raw.get("prompt_ensemble")
    if not isinstance(prompts, dict):
        raise PipelineError("prompt_ensemble MedSigLIP é obrigatório.")
    positive = prompts.get("positive")
    negative = prompts.get("negative")
    if not isinstance(positive, list) or not isinstance(negative, list):
        raise PipelineError("Prompts positivos e negativos devem ser listas.")
    if not positive or len(positive) != len(negative):
        raise PipelineError("Ensembles positivo e negativo devem ser não vazios e balanceados.")
    all_prompts = positive + negative
    if any(not isinstance(item, str) or not item.strip() for item in all_prompts):
        raise PipelineError("Prompts MedSigLIP não podem ser vazios.")
    if any(len(item.split()) > 64 for item in all_prompts):
        raise PipelineError("Prompt MedSigLIP excede 64 tokens aproximados.")
    scoring = raw.get("scoring")
    if not isinstance(scoring, dict):
        raise PipelineError("Bloco scoring MedSigLIP é obrigatório.")
    threshold = scoring.get("exploratory_threshold")
    adjacent = scoring.get("minimum_adjacent_axial_tiles")
    if isinstance(threshold, bool) or not isinstance(threshold, (int, float)):
        raise PipelineError("exploratory_threshold deve ser numérico.")
    if not 0.0 < float(threshold) < 1.0:
        raise PipelineError("exploratory_threshold deve estar entre 0 e 1.")
    if isinstance(adjacent, bool) or not isinstance(adjacent, int) or adjacent < 1:
        raise PipelineError("minimum_adjacent_axial_tiles deve ser inteiro positivo.")
    if scoring.get("decision_enabled") is not False:
        raise PipelineError("Decisão MedSigLIP deve permanecer desabilitada até calibração.")
    return MedSigLIPConfig(
        model_id=str(raw.get("model_id", "")),
        positive_prompts=tuple(item.strip() for item in positive),
        negative_prompts=tuple(item.strip() for item in negative),
        exploratory_threshold=float(threshold),
        minimum_adjacent_axial_tiles=int(adjacent),
        decision_enabled=False,
    )


def extract_panel_views(panel_path: Path | str) -> PanelViews:
    path = Path(panel_path)
    if not path.is_file():
        raise PipelineError(f"Painel MedSigLIP não encontrado: {path}")
    with Image.open(path) as source:
        if source.info:
            raise PipelineError("Painel MedSigLIP contém metadados inesperados.")
        image = source.convert("RGB")
    width, height = image.size
    if width % 4 or height % 3 or width // 4 != height // 3:
        raise PipelineError("Painel deve ter grade 4×3 com tiles quadrados.")
    tile = width // 4
    axial = tuple(
        image.crop(
            (
                (index % 3) * tile,
                (index // 3) * tile,
                (index % 3 + 1) * tile,
                (index // 3 + 1) * tile,
            )
        )
        for index in range(9)
    )
    coronal = image.crop((3 * tile, 0, 4 * tile, tile))
    sagittal = image.crop((3 * tile, tile, 4 * tile, 2 * tile))
    return PanelViews(axial=axial, coronal=coronal, sagittal=sagittal)


def normalize_prompt_ensemble_scores(
    raw_logits: np.ndarray,
    *,
    positive_prompt_count: int,
) -> list[dict[str, float]]:
    """Apply the official candidate-text softmax and aggregate prompt classes.

    The MedSigLIP model card applies softmax directly across ``logits_per_image``.
    Positive and negative ensembles are required to have equal cardinality, so
    their probability mass can be summed into an auditable two-class score.
    """
    logits = np.asarray(raw_logits, dtype=np.float64)
    if logits.ndim != 2 or positive_prompt_count < 1:
        raise PipelineError("Matriz de logits MedSigLIP inválida.")
    if logits.shape[1] != positive_prompt_count * 2:
        raise PipelineError("Logits não correspondem ao ensemble balanceado.")
    if np.any(~np.isfinite(logits)):
        raise PipelineError("Logits MedSigLIP contêm valores não finitos.")

    shifted = logits - logits.max(axis=1, keepdims=True)
    exponentials = np.exp(shifted)
    denominator = exponentials.sum(axis=1, keepdims=True)
    if np.any(~np.isfinite(denominator)) or np.any(denominator <= 0):
        raise PipelineError("Logits MedSigLIP inválidos para softmax.")
    probabilities = exponentials / denominator
    positive = probabilities[:, :positive_prompt_count]
    negative = probabilities[:, positive_prompt_count:]

    results: list[dict[str, float]] = []
    for positive_values, negative_values in zip(positive, negative):
        positive_probability = float(positive_values.sum())
        results.append(
            {
                "positive_mean_softmax": round(float(positive_values.mean()), 8),
                "negative_mean_softmax": round(float(negative_values.mean()), 8),
                "positive_probability": round(positive_probability, 8),
                # Compatibilidade interna com o detector de adjacência v1.
                "positive_pair_normalized": round(positive_probability, 8),
            }
        )
    return results


def adjacent_axial_evidence(
    normalized_scores: list[dict[str, float]],
    *,
    threshold: float,
    minimum_adjacent: int,
) -> dict[str, Any]:
    if len(normalized_scores) < 9:
        raise PipelineError("São necessários nove scores axiais.")
    flags = [
        float(item["positive_pair_normalized"]) >= float(threshold)
        for item in normalized_scores[:9]
    ]
    longest = current = 0
    for flag in flags:
        current = current + 1 if flag else 0
        longest = max(longest, current)
    return {
        "threshold": float(threshold),
        "minimum_adjacent": int(minimum_adjacent),
        "axial_flags": flags,
        "longest_adjacent_run": longest,
        "exploratory_evidence_present": longest >= int(minimum_adjacent),
        "is_final_decision": False,
    }


class MedSigLIPScorer:
    """Carrega o encoder somente quando solicitado e retorna scores auditáveis."""

    def __init__(
        self,
        config: MedSigLIPConfig,
        *,
        local_files_only: bool = True,
        device: str = "cpu",
    ) -> None:
        self.config = config
        self.local_files_only = bool(local_files_only)
        self.device = str(device)
        self._processor = None
        self._model = None

    def load(self) -> None:
        try:
            import torch
            from transformers import (
                AutoModelForZeroShotImageClassification,
                AutoProcessor,
            )

            self._processor = AutoProcessor.from_pretrained(
                self.config.model_id,
                local_files_only=self.local_files_only,
            )
            dtype = torch.float16 if self.device.startswith("cuda") else torch.float32
            self._model = AutoModelForZeroShotImageClassification.from_pretrained(
                self.config.model_id,
                local_files_only=self.local_files_only,
                dtype=dtype,
            ).to(self.device)
            self._model.eval()
        except Exception as exc:  # erro externo é convertido ao contrato do pipeline
            raise PipelineError(f"Não foi possível carregar MedSigLIP: {exc}") from exc

    def score_panel(self, panel_path: Path | str) -> dict[str, Any]:
        if self._processor is None or self._model is None:
            self.load()
        import torch

        views = extract_panel_views(panel_path)
        prompts = self.config.positive_prompts + self.config.negative_prompts
        inputs = self._processor(
            text=list(prompts),
            images=list(views.all_views),
            padding="max_length",
            return_tensors="pt",
        )
        inputs = {key: value.to(self.device) for key, value in inputs.items()}
        with torch.inference_mode():
            outputs = self._model(**inputs)
            raw_logits = outputs.logits_per_image.float().cpu().numpy()
        normalized = normalize_prompt_ensemble_scores(
            raw_logits,
            positive_prompt_count=len(self.config.positive_prompts),
        )
        return {
            "schema": "argos-medsiglip-scores-v2",
            "scoring_method": "softmax_logits_prompt_ensemble",
            "research_only": True,
            "clinical_use_allowed": False,
            "model_id": self.config.model_id,
            "panel_sha256": sha256_of(Path(panel_path)),
            "view_order": [f"axial_{index:02d}" for index in range(1, 10)]
            + ["coronal", "sagittal"],
            "scores": normalized,
            "adjacent_axial_exploratory": adjacent_axial_evidence(
                normalized,
                threshold=self.config.exploratory_threshold,
                minimum_adjacent=self.config.minimum_adjacent_axial_tiles,
            ),
            "final_decision": None,
            "requires_human_review": True,
        }
