"""Signed technical-review gate for LLD-MMRI v23 uniform-9 panels."""
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from dtwin.benchmark.lld_mmri_v23_panels import (
    COHORT_SCHEMA,
    GALLERY_SCHEMA,
    _load,
    _safe,
)
from dtwin.benchmark.openswisshcc_alignment import _sha256
from dtwin.benchmark.openswisshcc_v20_fusion import _canonical_sha
from dtwin.core import PipelineError
from dtwin.medgemma_screening import _write_json_atomic


REVIEW_SCHEMA = "argos-lld-mmri-v23-uniform9-human-review-v1"


def _validate_sources(
    *, panel_root: Path, gallery_root: Path
) -> tuple[dict[str, Any], dict[str, Any]]:
    panel_root = Path(panel_root).resolve()
    gallery_root = Path(gallery_root).resolve()
    cohort_path = panel_root / "cohort_manifest.json"
    gallery_path = gallery_root / "gallery_manifest.json"
    cohort = _load(cohort_path)
    gallery = _load(gallery_path)
    cohort_unsigned = dict(cohort)
    cohort_signature = cohort_unsigned.pop("cohort_signature", None)
    gallery_unsigned = dict(gallery)
    gallery_signature = gallery_unsigned.pop("gallery_signature", None)
    if (
        cohort.get("schema") != COHORT_SCHEMA
        or cohort.get("status") != "complete_pending_human_review"
        or cohort_signature != _canonical_sha(cohort_unsigned)
        or cohort.get("all_panels_uniform9") is not True
        or cohort.get("all_panels_pending_human_review") is not True
        or cohort.get("lesion_masks_used") is not False
        or cohort.get("pathology_labels_used") is not False
        or cohort.get("ground_truth_read") is not False
        or cohort.get("protocol_case_count")
        != cohort.get("case_count", 0) + cohort.get("technical_failure_case_count", 0)
        or cohort.get("technical_failure_case_count")
        != len(cohort.get("technical_failure_case_ids", []))
        or cohort.get("technical_failures_excluded_from_inference") is not True
        or cohort.get("technical_failures_count_as_primary_metric_errors") is not True
    ):
        raise PipelineError("Coorte LLD-MMRI invalida antes da revisao.")
    if (
        gallery.get("schema") != GALLERY_SCHEMA
        or gallery.get("status") != "pending_human_review"
        or gallery.get("approved") is not False
        or gallery_signature != _canonical_sha(gallery_unsigned)
        or gallery.get("source_cohort_sha256") != _sha256(cohort_path)
        or gallery.get("source_cohort_signature") != cohort_signature
        or gallery.get("index_sha256") != _sha256(gallery_root / "index.html")
        or gallery.get("ground_truth_read") is not False
        or gallery.get("protocol_case_count") != cohort.get("protocol_case_count")
        or gallery.get("technical_failure_case_count")
        != cohort.get("technical_failure_case_count")
        or gallery.get("technical_failure_case_ids")
        != cohort.get("technical_failure_case_ids")
        or gallery.get("technical_failures_excluded_from_inference") is not True
        or gallery.get("technical_failures_count_as_primary_metric_errors") is not True
    ):
        raise PipelineError("Galeria LLD-MMRI invalida antes da revisao.")
    cohort_cases = cohort.get("cases")
    gallery_cases = gallery.get("cases")
    if (
        not isinstance(cohort_cases, list)
        or not isinstance(gallery_cases, list)
        or [item.get("case_id") for item in cohort_cases]
        != [item.get("case_id") for item in gallery_cases]
        or len(cohort_cases) != cohort.get("case_count")
    ):
        raise PipelineError("Cobertura da galeria LLD-MMRI divergiu da coorte.")
    for source, copy in zip(cohort_cases, gallery_cases, strict=True):
        panel = _safe(panel_root, str(source.get("panel", "")))
        image = _safe(gallery_root, str(copy.get("image", "")))
        expected = str(source.get("panel_sha256", ""))
        if (
            not panel.is_file()
            or not image.is_file()
            or _sha256(panel) != expected
            or _sha256(image) != expected
            or copy.get("sha256") != expected
        ):
            raise PipelineError("Painel LLD-MMRI mudou antes da revisao.")
    return cohort, gallery


def create_lld_mmri_v23_review(
    *,
    panel_root: Path,
    gallery_root: Path,
    output_path: Path,
    reviewer: str,
    approved: bool,
    note: str = "",
) -> dict[str, Any]:
    """Record explicit approval of every panel; partial approval is forbidden."""

    reviewer = str(reviewer).strip()
    note = str(note).strip()
    if approved is not True:
        raise PipelineError("Inferencia LLD-MMRI exige aprovacao humana explicita.")
    if not reviewer or len(reviewer) > 80 or len(note) > 1000:
        raise PipelineError("Identificacao ou nota de revisao LLD-MMRI invalida.")
    panel_root = Path(panel_root).resolve()
    gallery_root = Path(gallery_root).resolve()
    cohort, gallery = _validate_sources(
        panel_root=panel_root,
        gallery_root=gallery_root,
    )
    base = {
        "schema": REVIEW_SCHEMA,
        "status": "approved_for_blind_inference",
        "review_scope": "technical_representation_only_not_diagnosis",
        "reviewer": reviewer,
        "reviewed_at_utc": datetime.now(timezone.utc).isoformat(),
        "approved": True,
        "all_cases_approved": True,
        "all_inference_eligible_cases_approved": True,
        "approved_case_ids": list(cohort["case_ids"]),
        "protocol_case_count": cohort["protocol_case_count"],
        "case_count": cohort["case_count"],
        "technical_failure_case_count": cohort["technical_failure_case_count"],
        "technical_failure_case_ids": list(cohort["technical_failure_case_ids"]),
        "technical_failures_excluded_from_inference": True,
        "technical_failures_count_as_primary_metric_errors": True,
        "note": note,
        "checks_confirmed": {
            "liver_visible": True,
            "orientation_plausible": True,
            "crop_non_destructive": True,
            "rgb_fusion_interpretable": True,
            "liver_contour_acceptable": True,
            "visible_phi_absent": True,
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
        "ground_truth_read": False,
        "research_only": True,
        "clinical_use_allowed": False,
        "requires_human_review": True,
    }
    review = dict(base)
    review["review_signature"] = _canonical_sha(base)
    output_path = Path(output_path).resolve()
    if output_path.exists():
        raise PipelineError("Revisao LLD-MMRI existente; sobrescrita recusada.")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    _write_json_atomic(output_path, review)
    return review


def verify_lld_mmri_v23_review(
    *,
    panel_root: Path,
    gallery_root: Path,
    review_path: Path,
    expected_reviewer: str | None = None,
) -> dict[str, Any]:
    """Fail closed before any MedGemma, MedSigLIP or localizer load."""

    panel_root = Path(panel_root).resolve()
    gallery_root = Path(gallery_root).resolve()
    cohort, gallery = _validate_sources(
        panel_root=panel_root,
        gallery_root=gallery_root,
    )
    review = _load(Path(review_path).resolve())
    unsigned = dict(review)
    signature = unsigned.pop("review_signature", None)
    source = review.get("source")
    if (
        review.get("schema") != REVIEW_SCHEMA
        or review.get("status") != "approved_for_blind_inference"
        or review.get("approved") is not True
        or review.get("all_cases_approved") is not True
        or review.get("all_inference_eligible_cases_approved") is not True
        or review.get("approved_case_ids") != cohort["case_ids"]
        or review.get("protocol_case_count") != cohort["protocol_case_count"]
        or review.get("case_count") != cohort["case_count"]
        or review.get("technical_failure_case_count")
        != cohort["technical_failure_case_count"]
        or review.get("technical_failure_case_ids")
        != cohort["technical_failure_case_ids"]
        or review.get("technical_failures_excluded_from_inference") is not True
        or review.get("technical_failures_count_as_primary_metric_errors") is not True
        or signature != _canonical_sha(unsigned)
        or not isinstance(source, dict)
        or source.get("panel_cohort_sha256") != _sha256(panel_root / "cohort_manifest.json")
        or source.get("panel_cohort_signature") != cohort["cohort_signature"]
        or source.get("gallery_manifest_sha256") != _sha256(gallery_root / "gallery_manifest.json")
        or source.get("gallery_signature") != gallery["gallery_signature"]
        or source.get("gallery_index_sha256") != gallery["index_sha256"]
        or review.get("diagnostic_review_performed") is not False
        or review.get("ground_truth_read") is not False
        or review.get("research_only") is not True
        or review.get("clinical_use_allowed") is not False
    ):
        raise PipelineError("Revisao LLD-MMRI invalida, incompleta ou adulterada.")
    if expected_reviewer is not None and review.get("reviewer") != expected_reviewer:
        raise PipelineError("Revisor LLD-MMRI divergiu do esperado.")
    return review


__all__ = [
    "REVIEW_SCHEMA",
    "create_lld_mmri_v23_review",
    "verify_lld_mmri_v23_review",
]
