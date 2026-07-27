"""Signed human-review gate for the label-blind LLD-MMRI full-FOV 3x9 pilot."""
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from dtwin.benchmark.lld_mmri_v23_full_fov_pilot import COHORT_SCHEMA, GALLERY_SCHEMA
from dtwin.benchmark.openswisshcc_alignment import _sha256
from dtwin.benchmark.openswisshcc_v20_fusion import _canonical_sha
from dtwin.core import PipelineError
from dtwin.medgemma_panel_full_fov import FULL_FOV_MULTIPANEL_POLICY
from dtwin.medgemma_screening import _write_json_atomic


REVIEW_SCHEMA = "argos-lld-mmri-v23-full-fov-3x9-human-review-v1"


def _load(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PipelineError(f"{label} ausente ou invalido.") from exc
    if not isinstance(value, dict):
        raise PipelineError(f"{label} deve ser objeto JSON.")
    return value


def _inside(root: Path, relative: str) -> Path:
    candidate = (root / str(relative)).resolve()
    if not candidate.is_relative_to(root):
        raise PipelineError("Caminho full-FOV fora da raiz autorizada.")
    return candidate


def validate_full_fov_review_sources(
    *, panel_root: Path, gallery_root: Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    panel_root = Path(panel_root).resolve()
    gallery_root = Path(gallery_root).resolve()
    cohort_path = panel_root / "cohort_manifest.json"
    gallery_path = gallery_root / "gallery_manifest.json"
    cohort = _load(cohort_path, "Coorte full-FOV")
    gallery = _load(gallery_path, "Galeria full-FOV")
    cohort_unsigned = dict(cohort)
    cohort_signature = cohort_unsigned.pop("cohort_signature", None)
    gallery_unsigned = dict(gallery)
    gallery_signature = gallery_unsigned.pop("gallery_signature", None)
    if (
        cohort.get("schema") != COHORT_SCHEMA
        or cohort.get("status") != "complete_pending_human_review"
        or cohort_signature != _canonical_sha(cohort_unsigned)
        or cohort.get("spatial_policy") != FULL_FOV_MULTIPANEL_POLICY
        or cohort.get("panel_image_count_per_case") != 3
        or cohort.get("total_panel_image_count") != cohort.get("case_count", 0) * 3
        or cohort.get("organ_masks_read") != 0
        or cohort.get("lesion_masks_read") != 0
        or cohort.get("ground_truth_read") is not False
        or cohort.get("eligible_for_inference") is not False
        or cohort.get("research_only") is not True
        or cohort.get("clinical_use_allowed") is not False
    ):
        raise PipelineError("Coorte full-FOV 3x9 invalida antes da revisao.")
    if (
        gallery.get("schema") != GALLERY_SCHEMA
        or gallery.get("status") != "pending_human_review"
        or gallery_signature != _canonical_sha(gallery_unsigned)
        or gallery.get("cohort_signature") != cohort_signature
        or gallery.get("source_cohort_sha256") != _sha256(cohort_path)
        or gallery.get("index_sha256") != _sha256(gallery_root / "index.html")
        or gallery.get("case_count") != cohort.get("case_count")
        or gallery.get("total_panel_image_count") != cohort.get("total_panel_image_count")
        or gallery.get("organ_masks_read") != 0
        or gallery.get("lesion_masks_read") != 0
        or gallery.get("ground_truth_read") is not False
        or gallery.get("eligible_for_inference") is not False
    ):
        raise PipelineError("Galeria full-FOV 3x9 invalida antes da revisao.")
    cases = cohort.get("cases")
    items = gallery.get("items")
    if not isinstance(cases, list) or not isinstance(items, list) or len(cases) != len(items):
        raise PipelineError("Cobertura da galeria full-FOV divergiu da coorte.")
    for case, item in zip(cases, items, strict=True):
        if case.get("case_id") != item.get("case_id"):
            raise PipelineError("Ordem de casos da galeria full-FOV divergiu.")
        source_panels = case.get("panels")
        copied_panels = item.get("panels")
        if (
            case.get("panel_image_count") != 3
            or item.get("panel_count") != 3
            or not isinstance(source_panels, list)
            or not isinstance(copied_panels, list)
            or len(source_panels) != 3
            or len(copied_panels) != 3
        ):
            raise PipelineError("Caso full-FOV nao possui exatamente tres paineis.")
        manifest = _inside(panel_root, str(case.get("manifest", "")))
        if not manifest.is_file() or _sha256(manifest) != case.get("manifest_sha256"):
            raise PipelineError("Manifesto full-FOV mudou antes da revisao.")
        for expected_number, (source_record, copy_record) in enumerate(
            zip(source_panels, copied_panels, strict=True), start=1
        ):
            source = _inside(panel_root, str(source_record.get("panel", "")))
            copied = _inside(gallery_root, str(copy_record.get("image", "")))
            expected_hash = str(source_record.get("panel_sha256", ""))
            if (
                source_record.get("panel_number") != expected_number
                or copy_record.get("panel_number") != expected_number
                or not source.is_file()
                or not copied.is_file()
                or _sha256(source) != expected_hash
                or _sha256(copied) != expected_hash
                or copy_record.get("sha256") != expected_hash
            ):
                raise PipelineError("Painel full-FOV mudou antes da revisao.")
    return cohort, gallery


def create_full_fov_human_review(
    *, panel_root: Path, gallery_root: Path, output_path: Path,
    reviewer: str, approved: bool, note: str = "",
) -> dict[str, Any]:
    reviewer = str(reviewer).strip()
    note = str(note).strip()
    if approved is not True:
        raise PipelineError("Piloto full-FOV exige aprovacao humana explicita.")
    if not reviewer or len(reviewer) > 80 or len(note) > 1000:
        raise PipelineError("Identificacao ou nota de revisao full-FOV invalida.")
    panel_root = Path(panel_root).resolve()
    gallery_root = Path(gallery_root).resolve()
    cohort, gallery = validate_full_fov_review_sources(
        panel_root=panel_root, gallery_root=gallery_root,
    )
    base = {
        "schema": REVIEW_SCHEMA,
        "status": "approved_for_blind_timing_pilot",
        "review_scope": "technical_representation_only_not_diagnosis",
        "reviewer": reviewer,
        "reviewed_at_utc": datetime.now(timezone.utc).isoformat(),
        "approved": True,
        "all_cases_approved": True,
        "approved_case_ids": list(cohort["case_ids"]),
        "case_count": cohort["case_count"],
        "panel_image_count_per_case": 3,
        "total_panel_image_count": cohort["total_panel_image_count"],
        "note": note,
        "checks_confirmed": {
            "liver_extent_visible_across_three_panels": True,
            "full_acquired_fov_preserved": True,
            "destructive_crop_absent": True,
            "misleading_contour_absent": True,
            "rgb_fusion_interpretable": True,
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
        "organ_masks_read": 0,
        "lesion_masks_read": 0,
        "ground_truth_read": False,
        "research_only": True,
        "clinical_use_allowed": False,
        "requires_human_review": True,
    }
    review = {**base, "review_signature": _canonical_sha(base)}
    output_path = Path(output_path).resolve()
    if output_path.exists():
        raise PipelineError("Revisao full-FOV existente; sobrescrita recusada.")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    _write_json_atomic(output_path, review)
    return review


def verify_full_fov_human_review(
    *, panel_root: Path, gallery_root: Path, review_path: Path,
    expected_reviewer: str | None = None,
) -> dict[str, Any]:
    panel_root = Path(panel_root).resolve()
    gallery_root = Path(gallery_root).resolve()
    cohort, gallery = validate_full_fov_review_sources(
        panel_root=panel_root, gallery_root=gallery_root,
    )
    review = _load(Path(review_path).resolve(), "Revisao full-FOV")
    unsigned = dict(review)
    signature = unsigned.pop("review_signature", None)
    source = review.get("source")
    checks = review.get("checks_confirmed")
    if (
        review.get("schema") != REVIEW_SCHEMA
        or review.get("status") != "approved_for_blind_timing_pilot"
        or review.get("approved") is not True
        or review.get("all_cases_approved") is not True
        or review.get("approved_case_ids") != cohort["case_ids"]
        or review.get("case_count") != cohort["case_count"]
        or review.get("panel_image_count_per_case") != 3
        or review.get("total_panel_image_count") != cohort["total_panel_image_count"]
        or signature != _canonical_sha(unsigned)
        or not isinstance(checks, dict)
        or not checks
        or any(value is not True for value in checks.values())
        or not isinstance(source, dict)
        or source.get("panel_cohort_sha256") != _sha256(panel_root / "cohort_manifest.json")
        or source.get("panel_cohort_signature") != cohort["cohort_signature"]
        or source.get("gallery_manifest_sha256") != _sha256(gallery_root / "gallery_manifest.json")
        or source.get("gallery_signature") != gallery["gallery_signature"]
        or source.get("gallery_index_sha256") != gallery["index_sha256"]
        or review.get("diagnostic_review_performed") is not False
        or review.get("organ_masks_read") != 0
        or review.get("lesion_masks_read") != 0
        or review.get("ground_truth_read") is not False
        or review.get("research_only") is not True
        or review.get("clinical_use_allowed") is not False
    ):
        raise PipelineError("Revisao full-FOV invalida, incompleta ou adulterada.")
    if expected_reviewer is not None and review.get("reviewer") != expected_reviewer:
        raise PipelineError("Revisor full-FOV divergiu do esperado.")
    return review


__all__ = [
    "REVIEW_SCHEMA",
    "create_full_fov_human_review",
    "validate_full_fov_review_sources",
    "verify_full_fov_human_review",
]
