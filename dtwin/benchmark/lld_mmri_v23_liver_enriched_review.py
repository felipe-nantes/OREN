"""Signed technical-review gate for the LLD-MMRI v23 liver-enriched pilot."""
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from dtwin.benchmark.lld_mmri_v23_liver_enriched_pilot import COHORT_SCHEMA, GALLERY_SCHEMA
from dtwin.benchmark.openswisshcc_alignment import _sha256
from dtwin.benchmark.openswisshcc_v20_fusion import _canonical_sha
from dtwin.core import PipelineError
from dtwin.medgemma_panel_liver_enriched import LIVER_ENRICHED_POLICY
from dtwin.medgemma_screening import _write_json_atomic


REVIEW_SCHEMA = "argos-lld-mmri-v23-liver-enriched-human-review-v1"
FULL_REVIEW_SCHEMA = "argos-lld-mmri-v23-liver-enriched-full-human-review-v1"


def _load(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PipelineError(f"{label} ausente ou invalido.") from exc
    if not isinstance(value, dict):
        raise PipelineError(f"{label} deve ser objeto JSON.")
    return value


def _safe(root: Path, relative: str) -> Path:
    path = (root / str(relative)).resolve()
    if not path.is_relative_to(root):
        raise PipelineError("Caminho liver-enriched fora da raiz autorizada.")
    return path


def validate_liver_enriched_review_sources(
    *, panel_root: Path, gallery_root: Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    panel_root = Path(panel_root).resolve()
    gallery_root = Path(gallery_root).resolve()
    cohort_path = panel_root / "cohort_manifest.json"
    gallery_path = gallery_root / "gallery_manifest.json"
    cohort = _load(cohort_path, "Coorte liver-enriched")
    gallery = _load(gallery_path, "Galeria liver-enriched")
    cohort_unsigned = dict(cohort)
    cohort_signature = cohort_unsigned.pop("cohort_signature", None)
    gallery_unsigned = dict(gallery)
    gallery_signature = gallery_unsigned.pop("gallery_signature", None)
    cases = cohort.get("cases")
    items = gallery.get("items")
    technical_failure_ids = cohort.get("technical_failure_case_ids", [])
    full_contract = cohort.get("protocol_case_count") is not None
    if (
        cohort.get("schema") != COHORT_SCHEMA
        or cohort.get("status") != "complete_pending_human_review"
        or cohort_signature != _canonical_sha(cohort_unsigned)
        or cohort.get("spatial_policy") != LIVER_ENRICHED_POLICY
        or cohort.get("stable_localizer_case_count", 0)
        + cohort.get("weak_localizer_fallback_case_count", 0) != cohort.get("case_count")
        or cohort.get("total_panel_image_count")
        != cohort.get("stable_localizer_case_count", 0) * 3
        + cohort.get("weak_localizer_fallback_case_count", 0) * 2
        or cohort.get("organ_masks_rendered") != 0
        or cohort.get("lesion_masks_read") != 0
        or cohort.get("ground_truth_read") is not False
        or cohort.get("eligible_for_inference") is not False
        or cohort.get("research_only") is not True
        or cohort.get("clinical_use_allowed") is not False
        or not isinstance(cases, list)
        or len(cases) != cohort.get("case_count")
        or not isinstance(technical_failure_ids, list)
        or (
            full_contract
            and (
                cohort.get("protocol_case_count")
                != cohort.get("case_count") + cohort.get("technical_failure_case_count", -1)
                or len(technical_failure_ids) != cohort.get("technical_failure_case_count")
                or len(set(technical_failure_ids)) != len(technical_failure_ids)
                or set(technical_failure_ids) & set(cohort.get("case_ids", []))
                or cohort.get("technical_failures_excluded_from_inference") is not True
                or cohort.get("technical_failures_count_as_primary_metric_errors") is not True
            )
        )
    ):
        raise PipelineError("Coorte liver-enriched invalida antes da revisao.")
    if (
        gallery.get("schema") != GALLERY_SCHEMA
        or gallery.get("status") != "pending_human_review"
        or gallery_signature != _canonical_sha(gallery_unsigned)
        or gallery.get("cohort_signature") != cohort_signature
        or gallery.get("source_cohort_sha256") != _sha256(cohort_path)
        or gallery.get("index_sha256") != _sha256(gallery_root / "index.html")
        or gallery.get("case_count") != cohort.get("case_count")
        or gallery.get("total_panel_image_count") != cohort.get("total_panel_image_count")
        or gallery.get("organ_masks_rendered") != 0
        or gallery.get("lesion_masks_read") != 0
        or gallery.get("ground_truth_read") is not False
        or gallery.get("eligible_for_inference") is not False
        or not isinstance(items, list)
        or len(items) != len(cases)
    ):
        raise PipelineError("Galeria liver-enriched invalida antes da revisao.")
    for case, item in zip(cases, items, strict=True):
        expected_count = 3 if case.get("localizer_stable") is True else 2
        source_panels = case.get("panels")
        gallery_panels = item.get("panels")
        manifest_path = _safe(panel_root, str(case.get("manifest", "")))
        if (
            case.get("case_id") != item.get("case_id")
            or case.get("selection_mode") != item.get("selection_mode")
            or item.get("localizer_stable") is not case.get("localizer_stable")
            or case.get("panel_image_count") != expected_count
            or item.get("panel_count") != expected_count
            or not isinstance(source_panels, list)
            or not isinstance(gallery_panels, list)
            or len(source_panels) != expected_count
            or len(gallery_panels) != expected_count
            or not manifest_path.is_file()
            or _sha256(manifest_path) != case.get("manifest_sha256")
        ):
            raise PipelineError("Caso liver-enriched divergiu antes da revisao.")
        manifest = _load(manifest_path, "Manifesto liver-enriched")
        if (
            manifest.get("spatial_policy") != LIVER_ENRICHED_POLICY
            or manifest.get("panel_image_count") != expected_count
            or manifest.get("organ_mask_rendered") is not False
            or manifest.get("lesion_mask_used") is not False
            or manifest.get("ground_truth_used") is not False
            or manifest.get("crop_to_liver") is not False
            or manifest.get("contour_rendered") is not False
        ):
            raise PipelineError("Manifesto liver-enriched violou o contrato visual.")
        for number, (source, copied) in enumerate(
            zip(source_panels, gallery_panels, strict=True), start=1
        ):
            source_path = _safe(panel_root, str(source.get("panel", "")))
            copied_path = _safe(gallery_root, str(copied.get("image", "")))
            expected_hash = str(source.get("panel_sha256", ""))
            if (
                source.get("panel_number") != number
                or copied.get("panel_number") != number
                or not source_path.is_file()
                or not copied_path.is_file()
                or _sha256(source_path) != expected_hash
                or _sha256(copied_path) != expected_hash
                or copied.get("sha256") != expected_hash
            ):
                raise PipelineError("Painel liver-enriched mudou antes da revisao.")
    return cohort, gallery


def create_liver_enriched_human_review(
    *, panel_root: Path, gallery_root: Path, output_path: Path,
    reviewer: str, approved: bool, note: str = "",
) -> dict[str, Any]:
    reviewer = str(reviewer).strip()
    note = str(note).strip()
    if approved is not True:
        raise PipelineError("Piloto liver-enriched exige aprovacao humana explicita.")
    if not reviewer or len(reviewer) > 80 or len(note) > 1000:
        raise PipelineError("Identificacao ou nota liver-enriched invalida.")
    panel_root = Path(panel_root).resolve()
    gallery_root = Path(gallery_root).resolve()
    cohort, gallery = validate_liver_enriched_review_sources(
        panel_root=panel_root, gallery_root=gallery_root,
    )
    full_contract = cohort.get("protocol_case_count") is not None
    base = {
        "schema": FULL_REVIEW_SCHEMA if full_contract else REVIEW_SCHEMA,
        "status": (
            "approved_for_blind_full_cohort_inference"
            if full_contract else "approved_for_blind_timing_pilot"
        ),
        "review_scope": "technical_representation_only_not_diagnosis",
        "reviewer": reviewer,
        "reviewed_at_utc": datetime.now(timezone.utc).isoformat(),
        "approved": True,
        "all_cases_approved": True,
        "approved_case_ids": list(cohort["case_ids"]),
        "case_count": cohort["case_count"],
        "stable_3panel_case_count": cohort["stable_localizer_case_count"],
        "fallback_2panel_case_count": cohort["weak_localizer_fallback_case_count"],
        "total_panel_image_count": cohort["total_panel_image_count"],
        "protocol_case_count": cohort.get("protocol_case_count", cohort["case_count"]),
        "technical_failure_case_count": cohort.get("technical_failure_case_count", 0),
        "technical_failure_case_ids": list(cohort.get("technical_failure_case_ids", [])),
        "technical_failures_excluded_from_inference": True,
        "technical_failures_count_as_primary_metric_errors": True,
        "note": note,
        "checks_confirmed": {
            "liver_recognizable_in_every_panel": True,
            "no_panel_contains_only_non_hepatic_anatomy": True,
            "full_in_plane_fov_preserved": True,
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
        "organ_masks_rendered": 0,
        "lesion_masks_read": 0,
        "ground_truth_read": False,
        "research_only": True,
        "clinical_use_allowed": False,
        "requires_human_review": True,
    }
    review = {**base, "review_signature": _canonical_sha(base)}
    output_path = Path(output_path).resolve()
    if output_path.exists():
        raise PipelineError("Revisao liver-enriched existente; sobrescrita recusada.")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    _write_json_atomic(output_path, review)
    return review


def verify_liver_enriched_human_review(
    *, panel_root: Path, gallery_root: Path, review_path: Path,
    expected_reviewer: str | None = None,
) -> dict[str, Any]:
    panel_root = Path(panel_root).resolve()
    gallery_root = Path(gallery_root).resolve()
    cohort, gallery = validate_liver_enriched_review_sources(
        panel_root=panel_root, gallery_root=gallery_root,
    )
    review = _load(Path(review_path).resolve(), "Revisao liver-enriched")
    unsigned = dict(review)
    signature = unsigned.pop("review_signature", None)
    source = review.get("source")
    checks = review.get("checks_confirmed")
    full_contract = cohort.get("protocol_case_count") is not None
    expected_schema = FULL_REVIEW_SCHEMA if full_contract else REVIEW_SCHEMA
    expected_status = (
        "approved_for_blind_full_cohort_inference"
        if full_contract else "approved_for_blind_timing_pilot"
    )
    if (
        review.get("schema") != expected_schema
        or review.get("status") != expected_status
        or review.get("approved") is not True
        or review.get("all_cases_approved") is not True
        or review.get("approved_case_ids") != cohort["case_ids"]
        or review.get("case_count") != cohort["case_count"]
        or review.get("stable_3panel_case_count") != cohort["stable_localizer_case_count"]
        or review.get("fallback_2panel_case_count") != cohort["weak_localizer_fallback_case_count"]
        or review.get("total_panel_image_count") != cohort["total_panel_image_count"]
        or review.get("protocol_case_count")
        != cohort.get("protocol_case_count", cohort["case_count"])
        or review.get("technical_failure_case_count")
        != cohort.get("technical_failure_case_count", 0)
        or review.get("technical_failure_case_ids")
        != cohort.get("technical_failure_case_ids", [])
        or review.get("technical_failures_excluded_from_inference") is not True
        or review.get("technical_failures_count_as_primary_metric_errors") is not True
        or signature != _canonical_sha(unsigned)
        or not isinstance(checks, dict)
        or any(value is not True for value in checks.values())
        or not isinstance(source, dict)
        or source.get("panel_cohort_sha256") != _sha256(panel_root / "cohort_manifest.json")
        or source.get("panel_cohort_signature") != cohort["cohort_signature"]
        or source.get("gallery_manifest_sha256") != _sha256(gallery_root / "gallery_manifest.json")
        or source.get("gallery_signature") != gallery["gallery_signature"]
        or source.get("gallery_index_sha256") != gallery["index_sha256"]
        or review.get("diagnostic_review_performed") is not False
        or review.get("organ_masks_rendered") != 0
        or review.get("lesion_masks_read") != 0
        or review.get("ground_truth_read") is not False
        or review.get("research_only") is not True
        or review.get("clinical_use_allowed") is not False
    ):
        raise PipelineError("Revisao liver-enriched invalida, incompleta ou adulterada.")
    if expected_reviewer is not None and review.get("reviewer") != expected_reviewer:
        raise PipelineError("Revisor liver-enriched divergiu do esperado.")
    return review


__all__ = [
    "REVIEW_SCHEMA", "FULL_REVIEW_SCHEMA", "create_liver_enriched_human_review",
    "validate_liver_enriched_review_sources", "verify_liver_enriched_human_review",
]
