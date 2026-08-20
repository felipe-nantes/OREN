"""Inferência MedGemma 4B sobre candidatos OpenSwissHCC previamente revisados."""
from __future__ import annotations

import json
import shutil
import time
import uuid
from pathlib import Path, PurePosixPath
from typing import Any

from dtwin.benchmark.openswisshcc_alignment import (
    _load_json,
    _publish_directory,
    _sha256,
)
from dtwin.benchmark.openswisshcc_candidate import CANDIDATE_VERSION
from dtwin.benchmark.openswisshcc_fallback import (
    FALLBACK_VERSION,
    REVIEW_FALLBACK_REASON,
    REVIEW_FALLBACK_VERSION,
)
from dtwin.benchmark.openswisshcc_review import (
    REQUIRED_CONFIRMATIONS,
    REVIEW_SCHEMA,
    SIGNED_REVIEW_FIELDS,
    _candidate,
    _review_signature,
)
from dtwin.core import PipelineError
from dtwin.medgemma_client import (
    build_medgemma_prompt,
    create_medgemma_client,
    effective_config_sha256,
    load_screening_config,
)
from dtwin.medgemma_screening import build_report_envelope, sha256_of_text

INFERENCE_VERSION = "openswisshcc-medgemma-4b-reviewed-v2"


def _reviewed_entry(
    *, review_path: Path, panel_root: Path, case_id: str
) -> tuple[dict[str, Any], dict[str, Any]]:
    review = _load_json(Path(review_path).resolve())
    if review.get("schema") != REVIEW_SCHEMA:
        raise PipelineError("Schema do manifesto de revisão é incompatível.")
    if set(review) != set(SIGNED_REVIEW_FIELDS) | {"review_signature"}:
        raise PipelineError("Campos do manifesto de revisão são incompatíveis.")
    if review.get("review_status") != "approved_for_research_inference":
        raise PipelineError("Painéis não estão aprovados para inferência de pesquisa.")
    if review.get("research_only") is not True or review.get("clinical_use_allowed") is not False:
        raise PipelineError("Manifesto de revisão perdeu as salvaguardas de pesquisa.")
    if review.get("ground_truth_read") is not False or review.get("inference_executed") is not False:
        raise PipelineError("Manifesto de revisão viola o isolamento metodológico.")
    if any(review.get("confirmations", {}).get(key) is not True for key in REQUIRED_CONFIRMATIONS):
        raise PipelineError("Manifesto não contém todas as confirmações visuais.")
    if review.get("review_signature") != _review_signature(review):
        raise PipelineError("Assinatura do manifesto de revisão é incompatível.")
    panels = review.get("panels")
    if not isinstance(panels, list) or review.get("panel_count") != len(panels):
        raise PipelineError("Lista de painéis revisados é incompatível.")
    matches = [item for item in panels if item.get("case_id") == case_id]
    if len(matches) != 1:
        raise PipelineError("Caso não possui exatamente uma aprovação visual assinada.")
    current = _candidate(Path(panel_root), case_id)
    if current != matches[0]:
        raise PipelineError("Painel ou manifesto candidato mudou após a revisão humana.")
    return review, current


def _candidate_files(panel_root: Path, case_id: str) -> tuple[Path, dict[str, Any], Path, dict[str, Any]]:
    root = Path(panel_root).resolve()
    case_dir = (root / case_id).resolve()
    if not case_dir.is_relative_to(root) or not case_dir.is_dir():
        raise PipelineError("Diretório do candidato é inseguro ou ausente.")
    candidate = _load_json(case_dir / "candidate_manifest.json")
    panel_relative = PurePosixPath(str(candidate.get("panel_filename", "")))
    manifest_relative = PurePosixPath(str(candidate.get("panel_manifest_filename", "")))
    for relative in (panel_relative, manifest_relative):
        if relative.is_absolute() or ".." in relative.parts or len(relative.parts) != 1:
            raise PipelineError("Candidato contém caminho inseguro.")
    panel = (case_dir / panel_relative.name).resolve()
    panel_manifest_path = (case_dir / manifest_relative.name).resolve()
    if not panel.is_file() or not panel_manifest_path.is_file():
        raise PipelineError("Painel ou manifesto do painel está ausente.")
    if _sha256(panel) != candidate.get("panel_sha256"):
        raise PipelineError("Hash do painel candidato é incompatível.")
    panel_manifest = _load_json(panel_manifest_path)
    if panel_manifest.get("case_id") != case_id:
        raise PipelineError("Manifesto do painel pertence a outro caso.")
    if panel_manifest.get("panel_sha256") != candidate.get("panel_sha256"):
        raise PipelineError("Manifestos discordam sobre o hash do painel.")
    if panel_manifest.get("lesion_pre_marked") is not False:
        raise PipelineError("Candidato viola a proibição de lesão pré-marcada.")
    return panel, candidate, panel_manifest_path, panel_manifest


def _validated_config(candidate: dict[str, Any], config_path: Path) -> tuple[dict[str, Any], str]:
    config_path = Path(config_path).resolve()
    if _sha256(config_path) != candidate.get("config_sha256"):
        raise PipelineError("Configuração não corresponde ao hash usado pelo candidato.")
    config = load_screening_config(config_path)
    kind = candidate.get("candidate_kind", "multiphase_rgb")
    version = candidate.get("candidate_version")
    mode = config.get("panel", {}).get("mode", "single_grayscale")
    if kind == "venous_single_phase_fallback":
        if version not in {FALLBACK_VERSION, REVIEW_FALLBACK_VERSION} or mode != "single_grayscale":
            raise PipelineError("Fallback venoso e configuração são incompatíveis.")
    elif kind == "multiphase_rgb":
        if version != CANDIDATE_VERSION or mode != "multiphase_fusion":
            raise PipelineError("Candidato multifásico e configuração são incompatíveis.")
    else:
        raise PipelineError(f"Tipo de candidato não autorizado: {kind!r}.")
    med = config.get("medgemma", {})
    if med.get("model_id") != "google/medgemma-1.5-4b-it":
        raise PipelineError("Executor exige exatamente MedGemma 1.5 4B.")
    if med.get("model_parameter_scale") != "4B":
        raise PipelineError("Escala do modelo não corresponde a 4B.")
    if int(med.get("timeout_seconds", 0)) > 120:
        raise PipelineError("Timeout interno do modelo excede 120 segundos.")
    if int(med.get("max_retries", 1)) != 0 or int(med.get("response_validation_max_retries", 1)) != 0:
        raise PipelineError("Candidato de baixa latência não permite retries.")
    if config.get("rag", {}).get("enabled") is not False:
        raise PipelineError("Candidato qualificado não permite RAG nesta execução.")
    return config, effective_config_sha256(config)


def infer_reviewed_candidate(
    *, case_id: str, panel_root: Path, review_path: Path, output_root: Path,
    config_path: Path, max_case_seconds: float = 180.0, client: Any | None = None
) -> dict[str, Any]:
    """Execute um caso aprovado; não persista relatório se qualquer gate falhar."""
    if not 0 < float(max_case_seconds) <= 180:
        raise PipelineError("max_case_seconds deve estar em (0, 180].")
    started = time.monotonic()
    review, reviewed = _reviewed_entry(
        review_path=review_path, panel_root=panel_root, case_id=case_id
    )
    panel, candidate, panel_manifest_path, panel_manifest = _candidate_files(panel_root, case_id)
    if candidate.get("candidate_signature") != reviewed.get("candidate_signature"):
        raise PipelineError("Assinatura do candidato diverge da revisão.")
    config, effective_hash = _validated_config(candidate, config_path)
    prompt = build_medgemma_prompt(config)
    if candidate.get("candidate_kind") == "venous_single_phase_fallback":
        reason = candidate.get("fallback_reason")
        explanation = (
            "o alinhamento multifásico não atingiu o gate anatômico"
            if reason != REVIEW_FALLBACK_REASON
            else "a revisão humana considerou a representação multifásica inadequada por alinhamento ou enquadramento"
        )
        prompt += (
            "\n\nCONTEXTO TÉCNICO: este caso usa o fallback pré-declarado de fase venosa única "
            f"porque {explanation}. Não presuma informação dinâmica arterial ou tardia."
        )
    if len(prompt) > int(config["medgemma"].get("max_prompt_chars", 12000)):
        raise PipelineError("Prompt efetivo excede max_prompt_chars.")

    output_root = Path(output_root).resolve()
    case_output = output_root / case_id
    if case_output.exists():
        raise PipelineError("Saída do caso já existe; não será sobrescrita.")
    output_root.mkdir(parents=True, exist_ok=True)
    staging = output_root / f".{case_id}.staging.{uuid.uuid4().hex}"
    staging.mkdir()
    try:
        medgemma_client = client if client is not None else create_medgemma_client(config)
        report = medgemma_client.generate(panel, prompt)
        elapsed = time.monotonic() - started
        if elapsed > float(max_case_seconds):
            raise PipelineError(
                f"Caso excedeu o teto operacional: {elapsed:.3f}s > {max_case_seconds:.3f}s."
            )
        durations = {
            "screening_total": round(elapsed, 4),
            **dict(getattr(medgemma_client, "last_timings", {}) or {}),
        }
        envelope = build_report_envelope(
            case_id=case_id,
            config=config,
            panel_filename=panel.name,
            panel_manifest_filename=panel_manifest_path.name,
            panel_manifest=panel_manifest,
            screening_config_sha256=effective_hash,
            report=report,
            durations_seconds=durations,
        )
        envelope["qualification"] = {
            "schema": "argos-openswisshcc-qualification-trace-v1",
            "inference_version": INFERENCE_VERSION,
            "review_signature": review["review_signature"],
            "candidate_signature": candidate["candidate_signature"],
            "candidate_version": candidate["candidate_version"],
            "candidate_kind": candidate.get("candidate_kind", "multiphase_rgb"),
            "effective_config_sha256": effective_hash,
            "prompt_sha256": sha256_of_text(prompt),
            "max_case_seconds": float(max_case_seconds),
            "ground_truth_read": False,
        }
        report_path = staging / "medgemma_report.json"
        report_path.write_text(
            json.dumps(envelope, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        inference_manifest = {
            "schema": "argos-openswisshcc-inference-case-v1",
            "case_id": case_id,
            "status": "pending_human_review",
            "prediction": envelope["report"]["resultado_hipotese"],
            "panel_sha256": candidate["panel_sha256"],
            "report_sha256": _sha256(report_path),
            "review_signature": review["review_signature"],
            "candidate_signature": candidate["candidate_signature"],
            "effective_config_sha256": effective_hash,
            "elapsed_seconds": round(elapsed, 4),
            "max_case_seconds": float(max_case_seconds),
            "within_time_limit": True,
            "research_only": True,
            "clinical_use_allowed": False,
            "requires_human_review": True,
            "ground_truth_read": False,
        }
        (staging / "inference_manifest.json").write_text(
            json.dumps(inference_manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        _publish_directory(staging, case_output)
        return inference_manifest
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
