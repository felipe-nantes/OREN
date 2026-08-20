"""Safe MedSigLIP top-2 -> MedGemma subtype adjudication contract.

The module is deliberately transport-agnostic: it prepares balanced A/B/C
choice prompts and deterministically validates/aggregates gateway responses.
It never changes the previously frozen HCC-vs-benign decision.
"""
from __future__ import annotations

import base64
import json
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from dtwin.core import PipelineError
from dtwin.learning.monophase_protocol import build_hierarchical_screening_result
from dtwin.medgemma_client import HTTPJSONMedGemmaClient, load_screening_config

SCHEMA = "oren-monophase-subtype-adjudication-v1"
ALLOWED_SUBTYPES = {"hcc", "fnh", "hemangioma", "hepatic_cyst"}
CONFIDENCE_ORDER = {"baixa": 0, "moderada": 1, "alta": 2}


def validated_top2(class_probabilities: Mapping[str, Any]) -> list[dict[str, Any]]:
    if set(class_probabilities) != ALLOWED_SUBTYPES:
        raise PipelineError("Probabilidades de subtipo não cobrem as quatro classes autorizadas.")
    values: dict[str, float] = {}
    for name, raw in class_probabilities.items():
        try:
            value = float(raw)
        except (TypeError, ValueError) as exc:
            raise PipelineError("Probabilidade de subtipo inválida.") from exc
        if not 0.0 <= value <= 1.0:
            raise PipelineError("Probabilidade de subtipo fora de [0,1].")
        values[name] = value
    total = sum(values.values())
    if abs(total - 1.0) > 1e-5:
        raise PipelineError("Probabilidades de subtipo não estão normalizadas.")
    ordered = sorted(values.items(), key=lambda item: (-item[1], item[0]))[:2]
    return [{"subtype": name, "probability": value} for name, value in ordered]


def build_balanced_choice_prompts(
    *,
    top2: list[dict[str, Any]],
    source_phase_key: str,
    panel_number: int,
    panel_total: int,
    rag_context: str | None = None,
) -> list[dict[str, Any]]:
    if len(top2) != 2 or any(item.get("subtype") not in ALLOWED_SUBTYPES for item in top2):
        raise PipelineError("Top-2 inválido para adjudicação.")
    if not source_phase_key or source_phase_key == "unknown":
        raise PipelineError("Adjudicação exige sequência monofásica reconhecida.")
    if panel_number < 1 or panel_total < panel_number:
        raise PipelineError("Numeração de painel de adjudicação inválida.")
    rag = ""
    if rag_context:
        rag = (
            "\nCONTEXTO RAG TEXTUAL (apoio, não evidência visual):\n"
            + str(rag_context).strip()[:3000]
            + "\nNão use o RAG para criar um achado ausente na imagem.\n"
        )

    def prompt(left: str, right: str, order: str) -> dict[str, Any]:
        text = f"""Você é um segundo leitor de pesquisa para RM hepática monofásica.
Sequência real: {source_phase_key}. Evidência {panel_number}/{panel_total}.
O classificador visual forneceu somente um diferencial fechado entre dois subtipos.

A = {left}
B = {right}
C = INCONCLUSIVA

Escolha A somente se a imagem favorecer visualmente {left} sobre {right}.
Escolha B somente se a imagem favorecer visualmente {right} sobre {left}.
Escolha C quando a imagem não separar os dois com segurança.
Não alegue washout, comparação entre fases ou fase sintética. Não emita diagnóstico
definitivo nem conduta. Analise somente esta imagem. Responda pela escolha restrita.
{rag}"""
        return {
            "order": order,
            "prompt": text.strip(),
            "choice_map": {"A": left, "B": right, "C": "INCONCLUSIVE"},
            "allowed_gateway_choices": ["A", "B", "C"],
        }

    first, second = str(top2[0]["subtype"]), str(top2[1]["subtype"])
    return [prompt(first, second, "forward"), prompt(second, first, "reverse")]


def _mapped_probabilities(read: Mapping[str, Any], prompt_spec: Mapping[str, Any]) -> dict[str, float]:
    if list(read.get("choices") or []) != ["A", "B", "C"]:
        raise PipelineError("Gateway não confirmou escolhas A/B/C.")
    probabilities = read.get("choice_probabilities")
    if not isinstance(probabilities, Mapping) or set(probabilities) != {"A", "B", "C"}:
        raise PipelineError("Resposta de escolha sem probabilidades A/B/C completas.")
    mapped = {name: 0.0 for name in ALLOWED_SUBTYPES | {"INCONCLUSIVE"}}
    for letter, target in prompt_spec["choice_map"].items():
        value = float(probabilities[letter])
        if not 0.0 <= value <= 1.0:
            raise PipelineError("Probabilidade A/B/C inválida.")
        mapped[target] += value
    if abs(sum(mapped.values()) - 1.0) > 1e-4:
        raise PipelineError("Probabilidades A/B/C não normalizadas.")
    return mapped


def aggregate_balanced_choice_reads(
    *,
    prompt_specs: list[dict[str, Any]],
    reads: list[Mapping[str, Any]],
    minimum_margin: float = 0.15,
    minimum_probability: float = 0.50,
) -> dict[str, Any]:
    if len(prompt_specs) != 2 or len(reads) != 2:
        raise PipelineError("Adjudicação balanceada exige exatamente duas leituras.")
    mapped = [_mapped_probabilities(read, spec) for read, spec in zip(reads, prompt_specs)]
    names = sorted(ALLOWED_SUBTYPES | {"INCONCLUSIVE"})
    averaged = {name: sum(item[name] for item in mapped) / 2.0 for name in names}
    subtype_scores = sorted(
        ((name, averaged[name]) for name in ALLOWED_SUBTYPES),
        key=lambda item: (-item[1], item[0]),
    )
    winner, winner_probability = subtype_scores[0]
    runner_probability = subtype_scores[1][1]
    margin = winner_probability - runner_probability
    inconclusive = averaged["INCONCLUSIVE"]
    determined = (
        winner_probability >= minimum_probability
        and margin >= minimum_margin
        and winner_probability > inconclusive
    )
    confidence = (
        "alta" if determined and winner_probability >= 0.75
        else "moderada" if determined
        else "baixa"
    )
    return {
        "subtype": winner if determined else None,
        "determined": determined,
        "subtype_confidence": confidence,
        "averaged_probabilities": averaged,
        "winning_margin": margin,
        "order_balanced": True,
        "technical_failure": False,
    }


def request_balanced_subtype_reads(
    *,
    config_path: Path,
    image_path: Path,
    prompt_specs: list[dict[str, Any]],
) -> dict[str, Any]:
    """Call the existing dtwin-medgemma-v1 A/B/C choice contract twice.

    No new gateway API is introduced. The two prompts reverse subtype order;
    returned letter probabilities are later mapped back to clinical names.
    """
    if len(prompt_specs) != 2:
        raise PipelineError("Leitura balanceada exige dois prompts.")
    config = load_screening_config(config_path)
    client = HTTPJSONMedGemmaClient(config)
    health = client.check_ready()
    med = config["medgemma"]
    image_path = Path(image_path)
    if not image_path.is_file() or image_path.suffix.lower() != ".png":
        raise PipelineError("Adjudicação exige imagem PNG existente.")
    image_bytes = image_path.read_bytes()
    if len(image_bytes) > int(med["max_input_bytes"]):
        raise PipelineError("Imagem de adjudicação excede max_input_bytes.")
    reads: list[dict[str, Any]] = []
    started = time.monotonic()
    for spec in prompt_specs:
        payload = {
            "contract": "dtwin-medgemma-v1",
            "model_id": med["model_id"],
            "model_version": med["model_version"],
            "prompt": spec["prompt"],
            "image": {
                "mime_type": "image/png",
                "base64": base64.b64encode(image_bytes).decode("ascii"),
            },
            "generation": {
                "max_output_tokens": 1,
                "choices": ["A", "B", "C"],
                "balanced_choices": False,
            },
        }
        request = Request(
            str(med["endpoint_url"]),
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=int(med["timeout_seconds"])) as response:
                decoded = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            detail = exc.read(500).decode("utf-8", errors="replace")
            raise PipelineError(f"Gateway recusou adjudicação ({exc.code}): {detail}") from exc
        except (URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
            raise PipelineError(f"Falha na adjudicação MedGemma: {exc}") from exc
        if (
            not isinstance(decoded, dict)
            or decoded.get("model_id") != med["model_id"]
            or decoded.get("model_version") != med["model_version"]
        ):
            raise PipelineError("Gateway não confirmou a identidade exata do MedGemma.")
        reads.append({
            "choices": ["A", "B", "C"],
            "choice": decoded.get("choice"),
            "choice_probabilities": decoded.get("choice_probabilities"),
            "choice_aggregation": decoded.get("choice_aggregation"),
            "timings_seconds": decoded.get("timings_seconds"),
            "order": spec["order"],
        })
    return {
        "reads": reads,
        "elapsed_seconds": round(time.monotonic() - started, 4),
        "model_id": med["model_id"],
        "model_version": med["model_version"],
        "health_status": health.get("status"),
        "ground_truth_read": False,
        "lesion_masks_read": 0,
        "research_only": True,
    }


def fuse_subtype_adjudication(
    *,
    binary_prediction: str,
    class_probabilities: Mapping[str, Any],
    medgemma_adjudication: Mapping[str, Any],
    sequence_contract: Mapping[str, Any],
) -> dict[str, Any]:
    top2 = validated_top2(class_probabilities)
    adjudication = dict(medgemma_adjudication)
    subtype = adjudication.get("subtype")
    determined = adjudication.get("determined") is True
    allowed_differential = {item["subtype"] for item in top2}
    if determined and subtype not in allowed_differential:
        raise PipelineError("MedGemma escolheu subtipo fora do diferencial top-2 congelado.")
    if determined and adjudication.get("subtype_confidence") not in {"moderada", "alta"}:
        raise PipelineError("Subtipo determinado exige confiança moderada ou alta.")
    hierarchical = build_hierarchical_screening_result(
        prediction=binary_prediction,
        subtype=(
            {
                "determined": True,
                "subtype": subtype,
                "subtype_confidence": adjudication["subtype_confidence"],
            }
            if determined
            else {"determined": False}
        ),
        sequence_contract=sequence_contract,
    )
    return {
        "schema": SCHEMA,
        "binary_prediction_input": str(binary_prediction).upper(),
        "binary_prediction_changed_by_subtype_reader": False,
        "medsiglip_top2": top2,
        "medgemma_subtype_adjudication": adjudication,
        "hierarchical_result": hierarchical,
        "ground_truth_read": False,
        "lesion_masks_read": 0,
        "requires_human_review": True,
        "research_only": True,
        "clinical_use_allowed": False,
    }


__all__ = [
    "SCHEMA",
    "aggregate_balanced_choice_reads",
    "build_balanced_choice_prompts",
    "fuse_subtype_adjudication",
    "request_balanced_subtype_reads",
    "validated_top2",
]
