"""Signed technical-review gate for the label-blind OpenSwissHCC holdout."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any

from dtwin.benchmark.openswisshcc_alignment import _sha256
from dtwin.benchmark.openswisshcc_holdout_panels import COHORT_SCHEMA, GALLERY_SCHEMA
from dtwin.core import PipelineError
from dtwin.medgemma_screening import _write_json_atomic


REVIEW_SCHEMA = "argos-openswisshcc-holdout-uniform9-human-review-v1"
EXPECTED_CASE_COUNT = 44
EXPECTED_MULTIPHASE_COUNT = 43
EXPECTED_FALLBACK_INDEX = 28
FALLBACK_KIND = "venous_single_phase_fallback"


def _load(path: Path) -> dict[str, Any]:
    if not Path(path).is_file():
        raise PipelineError(f"Artefato holdout ausente: {path}")
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PipelineError(f"JSON holdout invalido: {path}") from exc
    if not isinstance(value, dict):
        raise PipelineError("Artefato holdout deve ser um objeto JSON.")
    return value


def _canonical_sha(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _safe(root: Path, relative: str) -> Path:
    root = Path(root).resolve()
    part = PurePosixPath(str(relative))
    if part.is_absolute() or ".." in part.parts:
        raise PipelineError("Caminho inseguro no gate do holdout.")
    path = (root / Path(*part.parts)).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise PipelineError("Arquivo do gate holdout ausente ou fora da raiz.")
    return path


def _verify_signature(value: dict[str, Any], field: str) -> bool:
    unsigned = dict(value)
    signature = str(unsigned.pop(field, ""))
    return len(signature) == 64 and signature == _canonical_sha(unsigned)


def _validate_sources(
    panel_root: Path, gallery_root: Path
) -> tuple[dict[str, Any], dict[str, Any], list[str]]:
    """Verify all pre-review artifacts without reading labels or lesion masks."""

    panel_root = Path(panel_root).resolve()
    gallery_root = Path(gallery_root).resolve()
    cohort_path = panel_root / "cohort_manifest.json"
    gallery_path = gallery_root / "gallery_manifest.json"
    cohort = _load(cohort_path)
    gallery = _load(gallery_path)
    if (
        cohort.get("schema") != COHORT_SCHEMA
        or cohort.get("status") != "complete_pending_human_review"
        or cohort.get("case_count") != EXPECTED_CASE_COUNT
        or cohort.get("multiphase_case_count") != EXPECTED_MULTIPHASE_COUNT
        or cohort.get("venous_fallback_case_count") != 1
        or cohort.get("all_panels_uniform9") is not True
        or cohort.get("all_panels_pending_human_review") is not True
        or cohort.get("lesion_masks_used") is not False
        or cohort.get("pathology_labels_used") is not False
        or cohort.get("holdout_ground_truth_opened") is not False
        or cohort.get("research_only") is not True
        or cohort.get("clinical_use_allowed") is not False
        or not _verify_signature(cohort, "cohort_signature")
    ):
        raise PipelineError("Coorte holdout pendente invalida ou adulterada.")
    if (
        gallery.get("schema") != GALLERY_SCHEMA
        or gallery.get("status") != "pending_human_review"
        or gallery.get("case_count") != EXPECTED_CASE_COUNT
        or gallery.get("panel_cohort_sha256") != _sha256(cohort_path)
        or gallery.get("index_sha256") != _sha256(gallery_root / "index.html")
        or gallery.get("holdout_ground_truth_opened") is not False
        or gallery.get("lesion_masks_used") is not False
        or gallery.get("research_only") is not True
        or gallery.get("clinical_use_allowed") is not False
        or not _verify_signature(gallery, "gallery_signature")
    ):
        raise PipelineError("Galeria holdout pendente invalida ou adulterada.")

    cohort_cases = cohort.get("cases")
    gallery_cases = gallery.get("cases")
    if not isinstance(cohort_cases, list) or not isinstance(gallery_cases, list):
        raise PipelineError("Casos da coorte/galeria holdout ausentes.")
    if len(cohort_cases) != EXPECTED_CASE_COUNT or len(gallery_cases) != EXPECTED_CASE_COUNT:
        raise PipelineError("Gate holdout exige exatamente 44 casos.")
    case_ids = [str(item.get("case_id", "")) for item in cohort_cases]
    if any(not case_id.startswith("anon-openswiss-") for case_id in case_ids) or len(set(case_ids)) != len(case_ids):
        raise PipelineError("Case IDs anonimos do holdout sao invalidos ou duplicados.")
    if case_ids != [str(item.get("case_id", "")) for item in gallery_cases]:
        raise PipelineError("Ordem da galeria holdout diverge da coorte.")

    fallback_indices: list[int] = []
    for expected_index, (cohort_case, gallery_case) in enumerate(
        zip(cohort_cases, gallery_cases, strict=True), start=1
    ):
        kind = str(cohort_case.get("candidate_kind", ""))
        if kind not in {"multiphase_rgb", FALLBACK_KIND} or gallery_case.get("candidate_kind") != kind:
            raise PipelineError("Tipo de painel holdout invalido ou divergente da galeria.")
        if kind == FALLBACK_KIND:
            fallback_indices.append(expected_index)
        if gallery_case.get("index") != expected_index:
            raise PipelineError("Indices da galeria holdout nao sao deterministas.")

        candidate_path = _safe(panel_root, str(cohort_case.get("candidate_manifest", "")))
        panel_path = _safe(panel_root, str(cohort_case.get("panel", "")))
        gallery_image = _safe(gallery_root, str(gallery_case.get("image", "")))
        candidate = _load(candidate_path)
        expected_panel_sha = str(cohort_case.get("panel_sha256", ""))
        if (
            _sha256(candidate_path) != cohort_case.get("candidate_manifest_sha256")
            or candidate.get("case_id") != cohort_case.get("case_id")
            or candidate.get("candidate_kind") != kind
            or candidate.get("candidate_signature") != cohort_case.get("candidate_signature")
            or candidate.get("status") != "rendered_pending_human_review"
            or candidate.get("panel_sha256") != expected_panel_sha
            or candidate.get("eligible_for_inference") is not False
            or candidate.get("lesion_mask_used") is not False
            or candidate.get("pathology_label_used") is not False
            or candidate.get("holdout_ground_truth_opened") is not False
            or _sha256(panel_path) != expected_panel_sha
            or _sha256(gallery_image) != expected_panel_sha
            or gallery_case.get("sha256") != expected_panel_sha
        ):
            raise PipelineError("Painel/candidato holdout divergiu antes da aprovacao.")
    if fallback_indices != [EXPECTED_FALLBACK_INDEX]:
        raise PipelineError("Fallback venoso holdout nao esta congelado exclusivamente no item 28.")
    return cohort, gallery, case_ids


def create_holdout_uniform9_review(
    *,
    panel_root: Path,
    gallery_root: Path,
    output_path: Path,
    reviewer: str,
    approved: bool,
    note: str = "",
) -> dict[str, Any]:
    """Create an immutable approval only after an explicit all-case review."""

    reviewer = str(reviewer).strip()
    note = str(note).strip()
    if approved is not True:
        raise PipelineError("A inferencia cega do holdout exige aprovacao humana explicita.")
    if not reviewer or len(reviewer) > 80:
        raise PipelineError("Identificacao do revisor holdout ausente ou invalida.")
    if len(note) > 1000:
        raise PipelineError("Nota de revisao holdout excede 1000 caracteres.")
    panel_root = Path(panel_root).resolve()
    gallery_root = Path(gallery_root).resolve()
    cohort, gallery, case_ids = _validate_sources(panel_root, gallery_root)
    payload: dict[str, Any] = {
        "schema": REVIEW_SCHEMA,
        "status": "approved_for_label_blind_inference",
        "review_scope": "technical_representation_only_not_diagnosis",
        "reviewer": reviewer,
        "reviewed_at_utc": datetime.now(timezone.utc).isoformat(),
        "approved": True,
        "all_cases_approved": True,
        "approved_case_ids": case_ids,
        "case_count": EXPECTED_CASE_COUNT,
        "multiphase_case_count": EXPECTED_MULTIPHASE_COUNT,
        "venous_fallback_case_count": 1,
        "venous_fallback_gallery_index": EXPECTED_FALLBACK_INDEX,
        "note": note,
        "checks_confirmed": {
            "liver_recognizable": True,
            "crop_non_destructive": True,
            "orientation_plausible": True,
            "rgb_alignment_non_destructive": True,
            "liver_contour_acceptable": True,
            "visible_phi_absent": True,
            "lesion_annotation_absent": True,
            "item_28_expected_venous_grayscale": True,
        },
        "source": {
            "panel_cohort_sha256": _sha256(panel_root / "cohort_manifest.json"),
            "panel_cohort_signature": cohort["cohort_signature"],
            "gallery_manifest_sha256": _sha256(gallery_root / "gallery_manifest.json"),
            "gallery_signature": gallery["gallery_signature"],
            "gallery_index_sha256": gallery["index_sha256"],
        },
        "diagnostic_review_performed": False,
        "labels_read": False,
        "lesion_masks_read": 0,
        "holdout_ground_truth_opened": False,
        "research_only": True,
        "clinical_use_allowed": False,
        "requires_human_review": True,
    }
    payload["review_signature"] = _canonical_sha(payload)
    output_path = Path(output_path).resolve()
    if output_path.exists():
        raise PipelineError("Revisao humana do holdout ja existe; recuso sobrescrever.")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    _write_json_atomic(output_path, payload)
    return payload


def verify_holdout_uniform9_review(
    *,
    panel_root: Path,
    gallery_root: Path,
    review_path: Path,
    expected_reviewer: str | None = None,
) -> dict[str, Any]:
    """Fail closed before model construction or any inference request."""

    panel_root = Path(panel_root).resolve()
    gallery_root = Path(gallery_root).resolve()
    cohort, gallery, case_ids = _validate_sources(panel_root, gallery_root)
    review = _load(Path(review_path).resolve())
    source = review.get("source")
    if (
        review.get("schema") != REVIEW_SCHEMA
        or review.get("status") != "approved_for_label_blind_inference"
        or review.get("approved") is not True
        or review.get("all_cases_approved") is not True
        or review.get("approved_case_ids") != case_ids
        or review.get("case_count") != EXPECTED_CASE_COUNT
        or review.get("multiphase_case_count") != EXPECTED_MULTIPHASE_COUNT
        or review.get("venous_fallback_case_count") != 1
        or review.get("venous_fallback_gallery_index") != EXPECTED_FALLBACK_INDEX
        or not _verify_signature(review, "review_signature")
        or not isinstance(source, dict)
        or source.get("panel_cohort_sha256") != _sha256(panel_root / "cohort_manifest.json")
        or source.get("panel_cohort_signature") != cohort["cohort_signature"]
        or source.get("gallery_manifest_sha256") != _sha256(gallery_root / "gallery_manifest.json")
        or source.get("gallery_signature") != gallery["gallery_signature"]
        or source.get("gallery_index_sha256") != gallery["index_sha256"]
        or review.get("diagnostic_review_performed") is not False
        or review.get("labels_read") is not False
        or review.get("lesion_masks_read") != 0
        or review.get("holdout_ground_truth_opened") is not False
        or review.get("research_only") is not True
        or review.get("clinical_use_allowed") is not False
    ):
        raise PipelineError("Revisao humana do holdout invalida, incompleta ou adulterada.")
    if expected_reviewer is not None and review.get("reviewer") != expected_reviewer:
        raise PipelineError("Revisor do holdout diverge do esperado.")
    return review
