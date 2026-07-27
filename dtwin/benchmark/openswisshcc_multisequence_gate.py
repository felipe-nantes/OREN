"""Signed human-review gate for the OpenSwissHCC multisequence v9 cohort."""
from __future__ import annotations

import hashlib
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from dtwin.benchmark.openswisshcc_alignment import _sha256
from dtwin.benchmark.openswisshcc_multisequence_batch import COHORT_SCHEMA
from dtwin.benchmark.openswisshcc_multisequence_panel import SCHEMA
from dtwin.core import PipelineError

REVIEW_SCHEMA = "argos-openswisshcc-multisequence-review-v1"
CONFIRMATIONS = (
    "no_visible_phi",
    "all_panels_open_and_uncorrupted",
    "cross_sequence_anatomy_acceptable",
    "liver_framing_and_contrast_acceptable",
    "out_of_fov_tiles_reviewed",
)
SIGNED = (
    "schema", "review_status", "reviewer", "reviewed_at_utc", "confirmations",
    "source_cohort_signature", "case_count", "panel_count", "cases",
    "research_only", "clinical_use_allowed", "ground_truth_read",
    "lesion_mask_used", "inference_executed",
)


def _load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PipelineError(f"JSON de revisao v9 invalido: {path}") from exc
    if not isinstance(value, dict):
        raise PipelineError("JSON de revisao v9 deve ser objeto.")
    return value


def _canonical(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _signature(payload: Mapping[str, Any]) -> str:
    return _canonical({key: payload.get(key) for key in SIGNED})


def validate_multisequence_cohort(panel_root: Path, expected_case_count: int = 88) -> dict[str, Any]:
    root = Path(panel_root).resolve()
    cohort = _load(root / "cohort_manifest.json")
    if cohort.get("schema") != COHORT_SCHEMA or cohort.get("case_count") != expected_case_count:
        raise PipelineError("Coorte v9 ausente ou incompatível.")
    if (cohort.get("research_only") is not True or cohort.get("clinical_use_allowed") is not False
            or cohort.get("ground_truth_read") is not False or cohort.get("lesion_mask_used") is not False
            or cohort.get("inference_executed") is not False):
        raise PipelineError("Coorte v9 perdeu salvaguardas metodologicas.")
    raw_cases = cohort.get("cases")
    if not isinstance(raw_cases, list) or len(raw_cases) != expected_case_count:
        raise PipelineError("Lista de casos v9 incompatível.")
    records = []
    for item in raw_cases:
        case_id = str(item.get("case_id", ""))
        case_dir = (root / case_id).resolve()
        if not case_id.startswith("anon-") or not case_dir.is_relative_to(root) or not case_dir.is_dir():
            raise PipelineError("Caso v9 inseguro ou ausente.")
        mpath = case_dir / "multisequence_manifest.json"
        manifest = _load(mpath)
        if (_sha256(mpath) != item.get("manifest_sha256") or manifest.get("schema") != SCHEMA
                or manifest.get("case_id") != case_id or manifest.get("ground_truth_read") is not False
                or manifest.get("lesion_mask_used") is not False):
            raise PipelineError(f"Manifesto v9 divergente: {case_id}.")
        coverage = manifest.get("coverage", {})
        if (coverage.get("gate_passed") is not True or coverage.get("missing_trace_planes") != []
                or coverage.get("duplicate_trace_planes") != []):
            raise PipelineError(f"Cobertura TRACE v9 invalida: {case_id}.")
        panels = manifest.get("panels")
        if not isinstance(panels, list) or len(panels) != item.get("panel_count"):
            raise PipelineError(f"Contagem de paineis v9 divergente: {case_id}.")
        compact = []
        for expected, panel in enumerate(panels, 1):
            path = (case_dir / str(panel.get("image", ""))).resolve()
            if (not path.is_relative_to(case_dir) or not path.is_file()
                    or panel.get("panel_number") != expected or _sha256(path) != panel.get("sha256")
                    or path.stat().st_size != panel.get("bytes")):
                raise PipelineError(f"Painel v9 divergente: {case_id}/{expected}.")
            compact.append({key: panel[key] for key in ("panel_number", "sha256", "bytes", "trace_plane_index")})
        records.append({
            "case_id": case_id, "manifest_sha256": item["manifest_sha256"],
            "panel_count": len(compact), "panel_set_sha256": _canonical(compact),
            "unavailable_tiles": coverage.get("unavailable_tiles", []),
        })
    if cohort.get("panel_count") != sum(r["panel_count"] for r in records):
        raise PipelineError("Total de paineis v9 divergente.")
    return {"cohort": cohort, "records": records}


def create_multisequence_review(*, panel_root: Path, output_path: Path, reviewer: str,
                                confirmations: Mapping[str, bool], expected_case_count: int = 88) -> dict[str, Any]:
    reviewer = str(reviewer).strip()
    if not reviewer or len(reviewer) > 120:
        raise PipelineError("Revisor v9 obrigatorio e limitado a 120 caracteres.")
    if any(confirmations.get(key) is not True for key in CONFIRMATIONS):
        raise PipelineError("Todas as confirmacoes humanas v9 devem ser explicitas.")
    output_path = Path(output_path).resolve()
    if output_path.exists():
        raise PipelineError("Revisao v9 ja existe e nao sera sobrescrita.")
    validated = validate_multisequence_cohort(panel_root, expected_case_count)
    records = validated["records"]
    payload = {
        "schema": REVIEW_SCHEMA, "review_status": "approved_for_research_inference",
        "reviewer": reviewer, "reviewed_at_utc": datetime.now(timezone.utc).isoformat(),
        "confirmations": {key: True for key in CONFIRMATIONS},
        "source_cohort_signature": validated["cohort"]["cohort_signature"],
        "case_count": len(records), "panel_count": sum(r["panel_count"] for r in records),
        "cases": records, "research_only": True, "clinical_use_allowed": False,
        "ground_truth_read": False, "lesion_mask_used": False, "inference_executed": False,
    }
    payload["review_signature"] = _signature(payload)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = output_path.with_name(f".{output_path.name}.{uuid.uuid4().hex}.tmp")
    try:
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(tmp, output_path)
    finally:
        tmp.unlink(missing_ok=True)
    return payload


def verify_multisequence_review(*, panel_root: Path, review_path: Path,
                                expected_case_count: int = 88) -> dict[str, Any]:
    review = _load(Path(review_path).resolve())
    if set(review) != set(SIGNED) | {"review_signature"} or review.get("schema") != REVIEW_SCHEMA:
        raise PipelineError("Campos ou schema da revisao v9 invalidos.")
    if review.get("review_status") != "approved_for_research_inference" or review.get("review_signature") != _signature(review):
        raise PipelineError("Revisao v9 nao esta aprovada ou possui assinatura invalida.")
    if any(review.get("confirmations", {}).get(key) is not True for key in CONFIRMATIONS):
        raise PipelineError("Confirmacoes da revisao v9 incompletas.")
    validated = validate_multisequence_cohort(panel_root, expected_case_count)
    if (review.get("source_cohort_signature") != validated["cohort"]["cohort_signature"]
            or review.get("cases") != validated["records"]
            or review.get("case_count") != len(validated["records"])
            or review.get("panel_count") != sum(r["panel_count"] for r in validated["records"])):
        raise PipelineError("Coorte ou paineis v9 mudaram apos a revisao.")
    return review
