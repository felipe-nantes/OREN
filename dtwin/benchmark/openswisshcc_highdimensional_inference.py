"""Congelamento e inferência cega do piloto high-dimensional MedGemma 1.5."""
from __future__ import annotations

import base64
import hashlib
import json
import re
import time
import uuid
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse, urlunparse
from urllib.request import Request, urlopen

from PIL import Image

from dtwin.benchmark.openswisshcc_highdimensional import CONTRACT, SCHEMA
from dtwin.core import PipelineError, sha256_of
from dtwin.medgemma_client import load_screening_config


PROTOCOL_SCHEMA = "argos-openswisshcc-highdimensional-protocol-v1"
RESULT_SCHEMA = "argos-openswisshcc-highdimensional-pilot-result-v1"
INSTRUCTION = (
    "Analise a sequência axial T1 pós-contraste venosa de uma RM hepática. "
    "Os cortes estão ordenados pelo índice axial LPS. O alvo exclusivo é suspeita "
    "de lesão focal hepática. Estrutura vascular tubular contínua, variante anatômica "
    "isolada e artefato provável não devem ser classificados como patologia alvo."
)
QUERY = (
    "Classifique como POSITIVA somente se houver lesão focal hepática suspeita; "
    "NEGATIVA quando não houver lesão focal suspeita; INCONCLUSIVA quando a qualidade "
    "não permitir a separação. Complete somente o valor e feche o JSON iniciado."
)
RESPONSE_PREFIX = '{"resultado_hipotese":"'
MAX_OUTPUT_TOKENS = 16
TIME_GATE_SECONDS = 180.0
_SAFE_FILENAME = re.compile(r"^slice_[0-9]{3}\.png$")


def _canonical_hash(value: dict) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _atomic_json(path: Path, value: dict) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp-{uuid.uuid4().hex}")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _volume_url(endpoint_url: str) -> str:
    parsed = urlparse(str(endpoint_url))
    if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise PipelineError("Piloto volumétrico exige endpoint HTTP exclusivamente local.")
    return urlunparse(parsed._replace(path="/generate-volume", params="", query="", fragment=""))


def validate_highdimensional_stack(stack_dir: Path) -> tuple[dict, list[bytes]]:
    stack_dir = Path(stack_dir).resolve()
    manifest_path = stack_dir / "manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PipelineError("Manifesto high-dimensional ausente ou inválido.") from exc
    if (
        manifest.get("schema") != SCHEMA
        or manifest.get("contract") != CONTRACT
        or manifest.get("research_only") is not True
        or manifest.get("clinical_use_allowed") is not False
        or manifest.get("requires_human_review") is not True
        or manifest.get("gate", {}).get("passed") is not True
        or manifest.get("gate", {}).get("ground_truth_used") is not False
        or manifest.get("gate", {}).get("lesion_mask_used") is not False
        or manifest.get("gate", {}).get("phi_metadata_included") is not False
    ):
        raise PipelineError("Gate ou salvaguardas da pilha high-dimensional falharam.")
    records = manifest.get("images")
    if not isinstance(records, list) or not 5 <= len(records) <= 85:
        raise PipelineError("Pilha deve conter entre 5 e 85 imagens.")
    if manifest.get("slice_count") != len(records):
        raise PipelineError("slice_count diverge da lista de imagens.")

    payloads: list[bytes] = []
    seen = set()
    for expected_order, item in enumerate(records, start=1):
        filename = str(item.get("filename", ""))
        if (
            item.get("order") != expected_order
            or not _SAFE_FILENAME.fullmatch(filename)
            or filename in seen
        ):
            raise PipelineError("Ordem ou nome inseguro na pilha high-dimensional.")
        seen.add(filename)
        path = (stack_dir / filename).resolve()
        try:
            path.relative_to(stack_dir)
        except ValueError as exc:
            raise PipelineError("Imagem escapou do diretório da pilha.") from exc
        raw = path.read_bytes()
        if sha256_of(path) != item.get("sha256"):
            raise PipelineError("Hash de imagem diverge antes da inferência.")
        with Image.open(path) as image:
            if image.format != "PNG" or image.mode != "RGB" or max(image.size) > 512:
                raise PipelineError("Imagem volumétrica viola formato, modo ou dimensão.")
            image.load()
        payloads.append(raw)
    return manifest, payloads


def freeze_highdimensional_protocol(
    *,
    stack_dir: Path,
    config_path: Path,
    out_path: Path,
) -> dict:
    manifest, _ = validate_highdimensional_stack(stack_dir)
    config = load_screening_config(config_path)
    med = config["medgemma"]
    volume_url = _volume_url(str(med["endpoint_url"]))
    base = {
        "schema": PROTOCOL_SCHEMA,
        "status": "frozen_before_inference",
        "case_id": manifest["case_id"],
        "case_selection": "first_case_id_lexicographically_in_blind_v11_bundle",
        "stack_manifest_sha256": sha256_of(Path(stack_dir) / "manifest.json"),
        "slice_count": manifest["slice_count"],
        "sampling": manifest["sampling"],
        "model_id": med["model_id"],
        "model_version": med["model_version"],
        "contract": CONTRACT,
        "endpoint_url": volume_url,
        "instruction": INSTRUCTION,
        "query": QUERY,
        "generation": {
            "max_output_tokens": MAX_OUTPUT_TOKENS,
            "response_prefix": RESPONSE_PREFIX,
            "do_sample": False,
            "requests_per_case": 1,
        },
        "time_gate_seconds": TIME_GATE_SECONDS,
        "ground_truth_read": False,
        "metrics_calculated": False,
        "holdout_opened": False,
        "research_only": True,
        "clinical_use_allowed": False,
        "requires_human_review": True,
    }
    protocol = dict(base)
    protocol["protocol_signature"] = _canonical_hash(base)
    out_path = Path(out_path)
    if out_path.exists():
        existing = json.loads(out_path.read_text(encoding="utf-8"))
        if existing != protocol:
            raise PipelineError("Protocolo existente diverge; sobrescrita recusada.")
        return existing
    _atomic_json(out_path, protocol)
    return protocol


def _load_protocol(path: Path) -> dict:
    try:
        protocol = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PipelineError("Protocolo high-dimensional ausente ou inválido.") from exc
    signature = protocol.pop("protocol_signature", None)
    if signature != _canonical_hash(protocol):
        raise PipelineError("Assinatura do protocolo high-dimensional diverge.")
    protocol["protocol_signature"] = signature
    return protocol


def _request_json(request: Request, timeout: float) -> dict:
    try:
        with urlopen(request, timeout=timeout) as response:
            decoded = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        detail = exc.read(1000).decode("utf-8", errors="replace")
        raise PipelineError(f"Gateway retornou HTTP {exc.code}: {detail}") from exc
    except (URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        raise PipelineError(f"Falha HTTP no piloto high-dimensional: {exc}") from exc
    if not isinstance(decoded, dict):
        raise PipelineError("Gateway retornou resposta que não é objeto JSON.")
    return decoded


def run_highdimensional_pilot(
    *,
    stack_dir: Path,
    protocol_path: Path,
    config_path: Path,
    out_path: Path,
) -> dict:
    if Path(out_path).exists():
        raise PipelineError("Resultado do piloto já existe; sobrescrita recusada.")
    protocol = _load_protocol(protocol_path)
    manifest, images = validate_highdimensional_stack(stack_dir)
    if sha256_of(Path(stack_dir) / "manifest.json") != protocol.get("stack_manifest_sha256"):
        raise PipelineError("Manifesto da pilha mudou após o congelamento.")
    config = load_screening_config(config_path)
    med = config["medgemma"]
    if (
        protocol.get("model_id") != med.get("model_id")
        or protocol.get("model_version") != med.get("model_version")
        or protocol.get("case_id") != manifest.get("case_id")
    ):
        raise PipelineError("Modelo, versão ou caso diverge do protocolo congelado.")

    health_url = str(med["healthcheck_url"])
    health = _request_json(
        Request(health_url, headers={"Accept": "application/json"}, method="GET"),
        timeout=15,
    )
    if (
        health.get("status") != "ready"
        or health.get("model_id") != protocol["model_id"]
        or health.get("model_version") != protocol["model_version"]
        or health.get("volume_contract") != CONTRACT
        or health.get("volume_supported") is not True
    ):
        raise PipelineError("Health check não confirmou o contrato volumétrico congelado.")

    payload = {
        "contract": CONTRACT,
        "model_id": protocol["model_id"],
        "model_version": protocol["model_version"],
        "instruction": protocol["instruction"],
        "images": [
            {"mime_type": "image/png", "base64": base64.b64encode(raw).decode("ascii")}
            for raw in images
        ],
        "query": protocol["query"],
        "generation": {
            "max_output_tokens": protocol["generation"]["max_output_tokens"],
            "response_prefix": protocol["generation"]["response_prefix"],
        },
    }
    request = Request(
        protocol["endpoint_url"],
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    started = time.monotonic()
    response = _request_json(request, timeout=TIME_GATE_SECONDS)
    elapsed = time.monotonic() - started
    if (
        response.get("contract") != CONTRACT
        or response.get("model_id") != protocol["model_id"]
        or response.get("model_version") != protocol["model_version"]
        or response.get("slice_count") != len(images)
        or response.get("research_only") is not True
        or response.get("clinical_use_allowed") is not False
        or response.get("requires_human_review") is not True
    ):
        raise PipelineError("Resposta volumétrica violou contrato ou salvaguardas.")

    raw_output = response.get("output")
    report = None
    classification = None
    try:
        report = json.loads(raw_output) if isinstance(raw_output, str) else None
        candidate = report.get("resultado_hipotese") if isinstance(report, dict) else None
        if candidate in {"POSITIVA", "NEGATIVA", "INCONCLUSIVA"}:
            classification = candidate
    except json.JSONDecodeError:
        pass
    output_valid = classification is not None
    result = {
        "schema": RESULT_SCHEMA,
        "status": "technical_passed" if output_valid and elapsed <= TIME_GATE_SECONDS else "technical_failed",
        "case_id": manifest["case_id"],
        "protocol_signature": protocol["protocol_signature"],
        "stack_manifest_sha256": protocol["stack_manifest_sha256"],
        "slice_count": len(images),
        "classification": classification,
        "report": report,
        "raw_output": raw_output,
        "gateway_timings_seconds": response.get("timings_seconds"),
        "request_elapsed_seconds": round(elapsed, 4),
        "time_gate_seconds": TIME_GATE_SECONDS,
        "time_gate_passed": elapsed <= TIME_GATE_SECONDS,
        "output_schema_valid": output_valid,
        "ground_truth_read": False,
        "metrics_calculated": False,
        "holdout_opened": False,
        "research_only": True,
        "clinical_use_allowed": False,
        "requires_human_review": True,
    }
    _atomic_json(out_path, result)
    return result
