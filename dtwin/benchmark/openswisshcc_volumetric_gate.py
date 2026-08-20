"""Immutable review and experiment freeze for OpenSwissHCC volumetric panels.

The legacy OpenSwissHCC review signs one preview panel per case.  A volumetric
candidate is a collection, so this module deliberately uses a separate schema
and binds every image, the authoritative panel manifest, exact liver coverage,
the effective model configuration, and the deterministic aggregation rule.
It never opens labels or lesion annotations.
"""
from __future__ import annotations

import hashlib
import json
import os
import uuid
from collections.abc import Iterable, Mapping
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any

from dtwin.benchmark.openswisshcc_alignment import _load_json, _sha256
from dtwin.core import PipelineError
from dtwin.medgemma_client import effective_config_sha256, load_screening_config

REVIEW_SCHEMA = "argos-openswisshcc-volumetric-review-v1"
FREEZE_SCHEMA = "argos-openswisshcc-volumetric-freeze-v1"
COHORT_SCHEMA = "argos-openswisshcc-volumetric-candidate-cohort-v1"
CANDIDATE_SCHEMA = "argos-public-liver-mri-volumetric-candidate-v1"
AGGREGATION_RULE = (
    "any_positive_else_any_inconclusive_else_all_negative; "
    "minimum_confidence_among_determining_reports"
)
REQUIRED_CONFIRMATIONS = (
    "no_visible_phi",
    "all_panels_open_and_uncorrupted",
    "liver_framing_acceptable",
    "multiphase_alignment_acceptable",
    "volumetric_sequence_acceptable",
)
_REVIEW_SIGNED_FIELDS = (
    "schema", "review_status", "reviewer", "reviewed_at_utc", "confirmations",
    "source_cohort_signature", "case_count", "panel_image_count", "cases",
    "research_only", "clinical_use_allowed", "ground_truth_read", "inference_executed",
)
_FREEZE_SIGNED_FIELDS = (
    "schema", "experiment_version", "review_signature", "source_cohort_signature",
    "case_count", "panel_image_count", "configs", "candidates", "aggregation_rule",
    "max_case_seconds", "research_only", "clinical_use_allowed", "ground_truth_read",
    "inference_executed",
)


def _canonical_sha256(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _signature(payload: Mapping[str, Any], fields: Iterable[str]) -> str:
    return _canonical_sha256({key: payload.get(key) for key in fields})


def _atomic_json(path: Path, payload: Mapping[str, Any]) -> None:
    path = Path(path).resolve()
    if path.exists():
        raise PipelineError(f"Artefato ja existe e nao sera sobrescrito: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _safe_file(parent: Path, value: Any, *, label: str) -> Path:
    relative = PurePosixPath(str(value or ""))
    if relative.is_absolute() or ".." in relative.parts or len(relative.parts) != 1:
        raise PipelineError(f"{label} possui caminho inseguro.")
    path = (parent / relative.name).resolve()
    if not path.is_relative_to(parent.resolve()) or not path.is_file():
        raise PipelineError(f"{label} esta ausente: {relative.name!r}.")
    return path


def ready_case_ids(panel_root: Path) -> list[str]:
    root = Path(panel_root).resolve()
    if not root.is_dir():
        raise PipelineError("Diretorio volumetrico nao existe.")
    ids = sorted(
        item.name for item in root.iterdir()
        if item.is_dir() and item.name.startswith("anon-")
        and (item / "candidate_manifest.json").is_file()
    )
    if not ids:
        raise PipelineError("Nenhum candidato volumetrico foi encontrado.")
    return ids


def validate_volumetric_candidate(panel_root: Path, case_id: str) -> dict[str, Any]:
    """Recompute the complete authoritative shape of one candidate."""
    if not case_id.startswith("anon-") or any(char in case_id for char in "/\\"):
        raise PipelineError(f"case_id invalido: {case_id!r}.")
    root = Path(panel_root).resolve()
    case_dir = (root / case_id).resolve()
    if not case_dir.is_relative_to(root) or not case_dir.is_dir():
        raise PipelineError(f"Caso volumetrico ausente: {case_id}.")
    candidate_path = case_dir / "candidate_manifest.json"
    candidate = _load_json(candidate_path)
    if candidate.get("schema") != CANDIDATE_SCHEMA or candidate.get("case_id") != case_id:
        raise PipelineError("Schema ou identidade do candidato volumetrico e invalida.")
    if candidate.get("panel_strategy") != "volumetric_blocks":
        raise PipelineError("Candidato nao usa cobertura volumetrica.")
    if candidate.get("research_only") is not True or candidate.get("clinical_use_allowed") is not False:
        raise PipelineError("Candidato perdeu as salvaguardas de pesquisa.")
    if candidate.get("ground_truth_read") is not False or candidate.get("visible_phi_confirmed") is not False:
        raise PipelineError("Candidato viola isolamento de labels ou gate visual previo.")

    coverage = candidate.get("coverage")
    if not isinstance(coverage, dict) or coverage.get("gate_passed") is not True:
        raise PipelineError("Gate de cobertura volumetrica ausente ou reprovado.")
    total = coverage.get("total_liver_voxels")
    covered = coverage.get("covered_liver_voxels")
    if not isinstance(total, int) or total <= 0 or covered != total:
        raise PipelineError("Cobertura nao prova igualdade exata de voxels hepaticos.")
    if coverage.get("missing_axial_indices") or coverage.get("duplicate_axial_indices"):
        raise PipelineError("Cobertura possui indices axiais ausentes ou duplicados.")

    raw_panels = candidate.get("panels")
    if not isinstance(raw_panels, list) or not raw_panels:
        raise PipelineError("Colecao de paineis volumetricos esta vazia.")
    if candidate.get("panel_image_count") != len(raw_panels):
        raise PipelineError("Contagem de paineis do candidato e inconsistente.")
    panels: list[dict[str, Any]] = []
    names: set[str] = set()
    for number, item in enumerate(raw_panels, start=1):
        if not isinstance(item, dict):
            raise PipelineError("Registro de painel volumetrico e invalido.")
        path = _safe_file(case_dir, item.get("image"), label="Painel volumetrico")
        if path.name in names:
            raise PipelineError("Colecao volumetrica contem arquivo duplicado.")
        names.add(path.name)
        if item.get("panel_number") != number or item.get("panel_total") != len(raw_panels):
            raise PipelineError("Ordem ou total da colecao volumetrica e invalido.")
        digest = _sha256(path)
        if digest != item.get("sha256") or path.stat().st_size != item.get("bytes"):
            raise PipelineError("Hash ou tamanho de painel volumetrico divergiu.")
        panels.append({
            "panel_number": number,
            "panel_total": len(raw_panels),
            "image": path.name,
            "sha256": digest,
            "bytes": path.stat().st_size,
            "axial_interval": item.get("axial_interval"),
        })
    if _canonical_sha256(panels) != candidate.get("panel_set_sha256"):
        raise PipelineError("Hash autoritativo da colecao volumetrica divergiu.")
    if (
        candidate.get("panel_filename") != panels[0]["image"]
        or candidate.get("panel_sha256") != panels[0]["sha256"]
        or candidate.get("panel_bytes") != panels[0]["bytes"]
    ):
        raise PipelineError("Preview legado nao corresponde ao primeiro painel da colecao.")

    panel_manifest_path = _safe_file(
        case_dir, candidate.get("panel_manifest_filename"), label="Manifesto volumetrico"
    )
    panel_manifest = _load_json(panel_manifest_path)
    if panel_manifest.get("case_id") != case_id or panel_manifest.get("panel_strategy") != "volumetric_blocks":
        raise PipelineError("Manifesto volumetrico pertence a outro caso ou estrategia.")
    if panel_manifest.get("lesion_pre_marked") is not False:
        raise PipelineError("Manifesto indica lesao pre-marcada.")
    if panel_manifest.get("coverage") != coverage:
        raise PipelineError("Candidato e manifesto discordam sobre cobertura.")
    manifest_panels = panel_manifest.get("panels")
    if not isinstance(manifest_panels, list) or len(manifest_panels) != len(panels):
        raise PipelineError("Manifesto e candidato discordam sobre a colecao.")
    for expected, actual in zip(panels, manifest_panels, strict=True):
        for key in ("panel_number", "panel_total", "image", "sha256", "axial_interval"):
            if actual.get(key) != expected.get(key):
                raise PipelineError(f"Manifesto diverge no campo {key!r} de um painel.")

    return {
        "case_id": case_id,
        "candidate_kind": candidate.get("candidate_kind"),
        "candidate_version": candidate.get("candidate_version"),
        "candidate_signature": candidate.get("candidate_signature"),
        "candidate_manifest_sha256": _sha256(candidate_path),
        "panel_manifest_filename": panel_manifest_path.name,
        "panel_manifest_sha256": _sha256(panel_manifest_path),
        "config_sha256": candidate.get("config_sha256"),
        "panel_image_count": len(panels),
        "panel_set_sha256": candidate.get("panel_set_sha256"),
        "coverage_sha256": _canonical_sha256(coverage),
        "total_liver_voxels": total,
        "covered_liver_voxels": covered,
        "panels": panels,
    }


def _validated_cohort(panel_root: Path, case_ids: list[str]) -> dict[str, Any]:
    root = Path(panel_root).resolve()
    cohort = _load_json(root / "cohort_manifest.json")
    if cohort.get("schema") != COHORT_SCHEMA:
        raise PipelineError("Schema do manifesto de coorte e invalido.")
    if cohort.get("research_only") is not True or cohort.get("clinical_use_allowed") is not False:
        raise PipelineError("Coorte perdeu as salvaguardas de pesquisa.")
    if cohort.get("ground_truth_read") is not False or cohort.get("inference_executed") is not False:
        raise PipelineError("Coorte viola isolamento metodologico.")
    records = [validate_volumetric_candidate(root, case_id) for case_id in case_ids]
    summaries = [
        {key: item[key] for key in (
            "case_id", "candidate_kind", "candidate_signature", "panel_image_count",
            "panel_set_sha256", "total_liver_voxels", "covered_liver_voxels",
        )}
        for item in records
    ]
    if cohort.get("cases") != summaries or cohort.get("cohort_signature") != _canonical_sha256(summaries):
        raise PipelineError("Manifesto da coorte nao corresponde aos candidatos atuais.")
    if cohort.get("case_count") != len(records) or cohort.get("panel_image_count") != sum(
        item["panel_image_count"] for item in records
    ):
        raise PipelineError("Contagens do manifesto da coorte sao inconsistentes.")
    return {"manifest": cohort, "records": records}


def create_volumetric_review(
    *, panel_root: Path, output_path: Path, reviewer: str,
    confirmations: Mapping[str, bool], expected_case_count: int = 88,
) -> dict[str, Any]:
    """Sign the human approval against every panel and coverage manifest."""
    reviewer = str(reviewer).strip()
    if not reviewer or len(reviewer) > 120:
        raise PipelineError("Identificador do revisor e obrigatorio e deve ter ate 120 caracteres.")
    if any(confirmations.get(key) is not True for key in REQUIRED_CONFIRMATIONS):
        raise PipelineError("Todas as confirmacoes visuais volumetricas devem ser explicitas.")
    case_ids = ready_case_ids(panel_root)
    if len(case_ids) != int(expected_case_count):
        raise PipelineError(f"Coorte possui {len(case_ids)} casos; esperado {expected_case_count}.")
    validated = _validated_cohort(panel_root, case_ids)
    records = validated["records"]
    payload: dict[str, Any] = {
        "schema": REVIEW_SCHEMA,
        "review_status": "approved_for_research_inference",
        "reviewer": reviewer,
        "reviewed_at_utc": datetime.now(timezone.utc).isoformat(),
        "confirmations": {key: True for key in REQUIRED_CONFIRMATIONS},
        "source_cohort_signature": validated["manifest"]["cohort_signature"],
        "case_count": len(records),
        "panel_image_count": sum(item["panel_image_count"] for item in records),
        "cases": records,
        "research_only": True,
        "clinical_use_allowed": False,
        "ground_truth_read": False,
        "inference_executed": False,
    }
    payload["review_signature"] = _signature(payload, _REVIEW_SIGNED_FIELDS)
    _atomic_json(output_path, payload)
    return payload


def verify_volumetric_review(
    *, review_path: Path, panel_root: Path, expected_case_count: int = 88,
) -> dict[str, Any]:
    review = _load_json(Path(review_path).resolve())
    if set(review) != set(_REVIEW_SIGNED_FIELDS) | {"review_signature"}:
        raise PipelineError("Campos do manifesto de revisao volumetrica sao invalidos.")
    if review.get("schema") != REVIEW_SCHEMA or review.get("review_status") != "approved_for_research_inference":
        raise PipelineError("Revisao volumetrica nao esta aprovada.")
    if review.get("review_signature") != _signature(review, _REVIEW_SIGNED_FIELDS):
        raise PipelineError("Assinatura da revisao volumetrica e invalida.")
    if any(review.get("confirmations", {}).get(key) is not True for key in REQUIRED_CONFIRMATIONS):
        raise PipelineError("Revisao volumetrica perdeu confirmacoes obrigatorias.")
    if review.get("research_only") is not True or review.get("clinical_use_allowed") is not False:
        raise PipelineError("Revisao volumetrica perdeu salvaguardas de pesquisa.")
    if review.get("ground_truth_read") is not False or review.get("inference_executed") is not False:
        raise PipelineError("Revisao volumetrica viola isolamento metodologico.")
    case_ids = ready_case_ids(panel_root)
    if len(case_ids) != int(expected_case_count):
        raise PipelineError("Coorte atual nao possui a contagem revisada.")
    validated = _validated_cohort(panel_root, case_ids)
    records = validated["records"]
    if (
        review.get("source_cohort_signature") != validated["manifest"]["cohort_signature"]
        or review.get("case_count") != len(records)
        or review.get("panel_image_count") != sum(item["panel_image_count"] for item in records)
        or review.get("cases") != records
    ):
        raise PipelineError("Painel, manifesto ou cobertura mudou apos a revisao humana.")
    return review


def _config_records(config_paths: Mapping[str, Path]) -> dict[str, dict[str, Any]]:
    if not config_paths:
        raise PipelineError("Nenhuma configuracao foi fornecida ao congelamento.")
    records: dict[str, dict[str, Any]] = {}
    identities: set[tuple[str, str, str]] = set()
    raw_hashes: set[str] = set()
    for key, raw_path in sorted(config_paths.items()):
        path = Path(raw_path).resolve()
        config = load_screening_config(path)
        med = config["medgemma"]
        panel = config.get("panel", {})
        record = {
            "filename": path.name,
            "raw_sha256": _sha256(path),
            "effective_sha256": effective_config_sha256(config),
            "model_id": med.get("model_id"),
            "model_version": med.get("model_version"),
            "endpoint_url": med.get("endpoint_url"),
            "response_mode": med.get("response_mode"),
            "timeout_seconds": med.get("timeout_seconds"),
            "max_retries": med.get("max_retries"),
            "response_validation_max_retries": med.get("response_validation_max_retries"),
            "panel_mode": panel.get("mode", "single_grayscale"),
            "panel_strategy": panel.get("strategy", "uniform_9"),
            "rag_enabled": config.get("rag", {}).get("enabled", False),
        }
        if record["raw_sha256"] in raw_hashes:
            raise PipelineError("Configuracoes congeladas possuem bytes duplicados.")
        raw_hashes.add(record["raw_sha256"])
        if record["model_id"] != "google/medgemma-1.5-4b-it" or med.get("model_parameter_scale") != "4B":
            raise PipelineError("Congelamento volumetrico exige exatamente MedGemma 1.5 4B.")
        if record["response_mode"] != "choice_classification":
            raise PipelineError("Congelamento volumetrico exige choice_classification.")
        if record["panel_strategy"] != "volumetric_blocks":
            raise PipelineError("Configuracao congelada nao usa volumetric_blocks.")
        if int(record["timeout_seconds"] or 0) > 120:
            raise PipelineError("Timeout interno excede 120 segundos.")
        if int(record["max_retries"] or 0) != 0 or int(record["response_validation_max_retries"] or 0) != 0:
            raise PipelineError("Configuracao congelada nao pode usar retry.")
        if record["rag_enabled"] is not False:
            raise PipelineError("Experimento volumetrico de calibracao nao permite RAG.")
        identities.add((str(record["model_id"]), str(record["model_version"]), str(record["endpoint_url"])))
        records[str(key)] = record
    if len(identities) != 1:
        raise PipelineError("Configuracoes nao compartilham a mesma identidade de backend.")
    return records


def create_volumetric_freeze(
    *, panel_root: Path, review_path: Path, config_paths: Mapping[str, Path],
    output_path: Path, experiment_version: str,
    expected_case_count: int = 88, max_case_seconds: float = 180.0,
) -> dict[str, Any]:
    version = str(experiment_version).strip()
    if not version or len(version) > 120:
        raise PipelineError("experiment_version e invalida.")
    if not 0 < float(max_case_seconds) <= 180:
        raise PipelineError("max_case_seconds deve estar em (0, 180].")
    review = verify_volumetric_review(
        review_path=review_path, panel_root=panel_root, expected_case_count=expected_case_count
    )
    configs = _config_records(config_paths)
    by_hash = {item["raw_sha256"]: key for key, item in configs.items()}
    candidates: list[dict[str, Any]] = []
    for item in review["cases"]:
        config_key = by_hash.get(item["config_sha256"])
        if config_key is None:
            raise PipelineError(f"Candidato {item['case_id']} nao possui configuracao autorizada.")
        candidates.append({**item, "config_key": config_key, "config_effective_sha256": configs[config_key]["effective_sha256"]})
    payload: dict[str, Any] = {
        "schema": FREEZE_SCHEMA,
        "experiment_version": version,
        "review_signature": review["review_signature"],
        "source_cohort_signature": review["source_cohort_signature"],
        "case_count": len(candidates),
        "panel_image_count": sum(item["panel_image_count"] for item in candidates),
        "configs": configs,
        "candidates": candidates,
        "aggregation_rule": AGGREGATION_RULE,
        "max_case_seconds": float(max_case_seconds),
        "research_only": True,
        "clinical_use_allowed": False,
        "ground_truth_read": False,
        "inference_executed": False,
    }
    payload["experiment_signature"] = _signature(payload, _FREEZE_SIGNED_FIELDS)
    payload["created_at_utc"] = datetime.now(timezone.utc).isoformat()
    _atomic_json(output_path, payload)
    return payload


def verify_volumetric_freeze(
    *, freeze_path: Path, panel_root: Path, review_path: Path,
    config_paths: Mapping[str, Path], expected_case_count: int = 88,
) -> dict[str, Any]:
    freeze = _load_json(Path(freeze_path).resolve())
    allowed = set(_FREEZE_SIGNED_FIELDS) | {"experiment_signature", "created_at_utc"}
    if set(freeze) != allowed or freeze.get("schema") != FREEZE_SCHEMA:
        raise PipelineError("Campos ou schema do freeze volumetrico sao invalidos.")
    if freeze.get("experiment_signature") != _signature(freeze, _FREEZE_SIGNED_FIELDS):
        raise PipelineError("Assinatura do freeze volumetrico e invalida.")
    if freeze.get("aggregation_rule") != AGGREGATION_RULE:
        raise PipelineError("Regra de agregacao congelada e invalida.")
    review = verify_volumetric_review(
        review_path=review_path, panel_root=panel_root, expected_case_count=expected_case_count
    )
    configs = _config_records(config_paths)
    by_hash = {item["raw_sha256"]: key for key, item in configs.items()}
    candidates = []
    for item in review["cases"]:
        key = by_hash.get(item["config_sha256"])
        if key is None:
            raise PipelineError("Candidato atual nao possui configuracao autorizada.")
        candidates.append({**item, "config_key": key, "config_effective_sha256": configs[key]["effective_sha256"]})
    if (
        freeze.get("review_signature") != review["review_signature"]
        or freeze.get("source_cohort_signature") != review["source_cohort_signature"]
        or freeze.get("case_count") != len(candidates)
        or freeze.get("panel_image_count") != sum(item["panel_image_count"] for item in candidates)
        or freeze.get("configs") != configs
        or freeze.get("candidates") != candidates
    ):
        raise PipelineError("Freeze nao corresponde a revisao, paineis ou configuracoes atuais.")
    if freeze.get("ground_truth_read") is not False or freeze.get("inference_executed") is not False:
        raise PipelineError("Freeze viola isolamento metodologico.")
    return freeze
