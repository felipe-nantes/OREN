"""Signed human technical-review gate for the CHAOS v21 panels."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any

from dtwin.benchmark.chaos_v21_panels import COHORT_SCHEMA, GALLERY_SCHEMA
from dtwin.benchmark.openswisshcc_alignment import _sha256
from dtwin.core import PipelineError
from dtwin.medgemma_screening import _write_json_atomic

REVIEW_SCHEMA = "argos-chaos-v21-uniform9-human-review-v1"


def _load(path: Path) -> dict[str, Any]:
    if not Path(path).is_file():
        raise PipelineError(f"Revisao humana CHAOS v21 ausente: {path}")
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PipelineError(f"JSON de revisao CHAOS v21 invalido: {path}") from exc
    if not isinstance(value, dict):
        raise PipelineError("Artefato de revisao CHAOS v21 deve ser objeto.")
    return value


def _canonical_sha(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _safe(root: Path, relative: str) -> Path:
    part = PurePosixPath(relative)
    if part.is_absolute() or ".." in part.parts:
        raise PipelineError("Caminho de painel CHAOS v21 inseguro.")
    path = (root / Path(*part.parts)).resolve()
    if not path.is_relative_to(root):
        raise PipelineError("Caminho de painel CHAOS v21 saiu da raiz.")
    return path


def _validate_sources(panel_root: Path, gallery_root: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    panel_root = Path(panel_root).resolve()
    gallery_root = Path(gallery_root).resolve()
    cohort_path = panel_root / "cohort_manifest.json"
    gallery_path = gallery_root / "gallery_manifest.json"
    cohort = _load(cohort_path)
    gallery = _load(gallery_path)
    cohort_unsigned = dict(cohort)
    cohort_signature = str(cohort_unsigned.pop("cohort_signature", ""))
    gallery_unsigned = dict(gallery)
    gallery_signature = str(gallery_unsigned.pop("gallery_signature", ""))
    if (
        cohort.get("schema") != COHORT_SCHEMA
        or cohort.get("status") != "complete_pending_human_review"
        or cohort_signature != _canonical_sha(cohort_unsigned)
        or cohort.get("all_panels_pending_human_review") is not True
        or cohort.get("lesion_masks_used") is not False
        or cohort.get("pathology_labels_used") is not False
        or cohort.get("ground_truth_read") is not False
        or cohort.get("holdout_opened") is not False
        or cohort.get("combined_primary_metric_allowed") is not False
    ):
        raise PipelineError("Coorte de paineis CHAOS v21 invalida ou adulterada.")
    if (
        gallery.get("schema") != GALLERY_SCHEMA
        or gallery.get("status") != "pending_human_review"
        or gallery.get("approved") is not False
        or gallery_signature != _canonical_sha(gallery_unsigned)
        or gallery.get("source_cohort_sha256") != _sha256(cohort_path)
        or gallery.get("index_sha256") != _sha256(gallery_root / "index.html")
        or gallery.get("ground_truth_read") is not False
        or gallery.get("holdout_opened") is not False
        or gallery.get("combined_primary_metric_allowed") is not False
    ):
        raise PipelineError("Galeria CHAOS v21 invalida ou adulterada.")
    cohort_cases = cohort.get("cases")
    gallery_cases = gallery.get("cases")
    if not isinstance(cohort_cases, list) or not isinstance(gallery_cases, list):
        raise PipelineError("Casos da coorte/galeria CHAOS v21 ausentes.")
    if [row.get("case_id") for row in cohort_cases] != [row.get("case_id") for row in gallery_cases]:
        raise PipelineError("Ordem de casos da galeria CHAOS diverge da coorte.")
    for cohort_case, gallery_case in zip(cohort_cases, gallery_cases, strict=True):
        panel = _safe(panel_root, str(cohort_case.get("panel", "")))
        gallery_image = _safe(gallery_root, str(gallery_case.get("image", "")))
        expected = str(cohort_case.get("panel_sha256", ""))
        if (
            not panel.is_file() or not gallery_image.is_file()
            or _sha256(panel) != expected or _sha256(gallery_image) != expected
            or gallery_case.get("sha256") != expected
        ):
            raise PipelineError("Hash de painel/galeria CHAOS divergiu antes da aprovacao.")
    return cohort, gallery


def create_chaos_v21_review(
    *, panel_root: Path, gallery_root: Path, output_path: Path,
    reviewer: str, approved: bool, note: str = "",
) -> dict[str, Any]:
    """Persist an explicit all-case technical approval; partial approval is rejected."""

    reviewer = str(reviewer).strip()
    if approved is not True:
        raise PipelineError("A inferencia CHAOS v21 exige aprovacao humana explicita.")
    if not reviewer or len(reviewer) > 80:
        raise PipelineError("Identificacao do revisor CHAOS v21 ausente ou invalida.")
    if len(str(note)) > 1000:
        raise PipelineError("Nota de revisao CHAOS v21 excede 1000 caracteres.")
    panel_root = Path(panel_root).resolve()
    gallery_root = Path(gallery_root).resolve()
    cohort, gallery = _validate_sources(panel_root, gallery_root)
    payload: dict[str, Any] = {
        "schema": REVIEW_SCHEMA,
        "status": "approved_for_blind_inference",
        "review_scope": "technical_representation_only_not_diagnosis",
        "evaluation_scope": "secondary_negative_domain_shift_stress_only",
        "reviewer": reviewer,
        "reviewed_at_utc": datetime.now(timezone.utc).isoformat(),
        "approved": True, "all_cases_approved": True,
        "approved_case_ids": list(cohort["case_ids"]),
        "case_count": int(cohort["case_count"]), "note": str(note).strip(),
        "checks_confirmed": {
            "liver_visible": True, "orientation_plausible": True,
            "crop_non_destructive": True, "rgb_fusion_interpretable": True,
            "rgb_semantics_t1in_t1out_t2spir_confirmed": True,
            "liver_contour_acceptable": True, "visible_phi_absent": True,
            "lesion_annotation_absent": True,
        },
        "source": {
            "panel_cohort_sha256": _sha256(panel_root / "cohort_manifest.json"),
            "panel_cohort_signature": cohort["cohort_signature"],
            "gallery_manifest_sha256": _sha256(gallery_root / "gallery_manifest.json"),
            "gallery_signature": gallery["gallery_signature"],
            "gallery_index_sha256": gallery["index_sha256"],
        },
        "diagnostic_review_performed": False,
        "ground_truth_read": False, "holdout_opened": False,
        "combined_primary_metric_allowed": False,
        "research_only": True, "clinical_use_allowed": False,
        "requires_human_review": True,
    }
    payload["review_signature"] = _canonical_sha(payload)
    output = Path(output_path).resolve()
    if output.exists():
        raise PipelineError("Revisao humana CHAOS v21 ja existe; recuso sobrescrever.")
    output.parent.mkdir(parents=True, exist_ok=True)
    _write_json_atomic(output, payload)
    return payload


def verify_chaos_v21_review(
    *, panel_root: Path, gallery_root: Path, review_path: Path,
    expected_reviewer: str | None = None,
) -> dict[str, Any]:
    """Fail closed before model loading or any inference call."""

    panel_root = Path(panel_root).resolve()
    gallery_root = Path(gallery_root).resolve()
    cohort, gallery = _validate_sources(panel_root, gallery_root)
    review = _load(Path(review_path).resolve())
    unsigned = dict(review)
    signature = str(unsigned.pop("review_signature", ""))
    source = review.get("source")
    if (
        review.get("schema") != REVIEW_SCHEMA
        or review.get("status") != "approved_for_blind_inference"
        or review.get("approved") is not True
        or review.get("all_cases_approved") is not True
        or review.get("approved_case_ids") != cohort["case_ids"]
        or review.get("case_count") != cohort["case_count"]
        or signature != _canonical_sha(unsigned)
        or not isinstance(source, dict)
        or source.get("panel_cohort_sha256") != _sha256(panel_root / "cohort_manifest.json")
        or source.get("panel_cohort_signature") != cohort["cohort_signature"]
        or source.get("gallery_manifest_sha256") != _sha256(gallery_root / "gallery_manifest.json")
        or source.get("gallery_signature") != gallery["gallery_signature"]
        or source.get("gallery_index_sha256") != gallery["index_sha256"]
        or review.get("diagnostic_review_performed") is not False
        or review.get("ground_truth_read") is not False
        or review.get("holdout_opened") is not False
        or review.get("combined_primary_metric_allowed") is not False
        or review.get("research_only") is not True
        or review.get("clinical_use_allowed") is not False
    ):
        raise PipelineError("Revisao humana CHAOS v21 invalida, incompleta ou adulterada.")
    if expected_reviewer is not None and review.get("reviewer") != expected_reviewer:
        raise PipelineError("Revisor CHAOS v21 diverge do esperado.")
    return review
