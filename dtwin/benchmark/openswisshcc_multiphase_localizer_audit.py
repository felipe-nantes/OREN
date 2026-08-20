"""Retrospective development-only audit of blind multiphase candidates."""
from __future__ import annotations

import json
import shutil
import uuid
from pathlib import Path
from typing import Any

import numpy as np
import SimpleITK as sitk

from dtwin.benchmark.openswisshcc_alignment import _publish_directory, _sha256
from dtwin.benchmark.openswisshcc_lesion_localizer import CASE_SCHEMA, RUN_SCHEMA
from dtwin.benchmark.openswisshcc_multiphase_localizer import ALGORITHM_VERSION
from dtwin.core import PipelineError
from dtwin.medgemma_screening import _write_json_atomic

AUDIT_SCHEMA = "argos-openswisshcc-multiphase-localizer-audit-v22"
EXTRACTION_SCHEMA = "argos-openswisshcc-v16-authorized-mask-extraction-v1"


def _load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PipelineError(f"JSON invalido na auditoria multifasica: {path}") from exc
    if not isinstance(value, dict):
        raise PipelineError("JSON da auditoria multifasica deve ser objeto.")
    return value


def _refuse_holdout(*paths: Path) -> None:
    if any(
        any("holdout" in part.lower() for part in Path(path).resolve().parts)
        for path in paths
    ):
        raise PipelineError("Auditoria multifasica recusou caminho de holdout.")


def _mask(path: Path, expected_hash: str) -> tuple[sitk.Image, np.ndarray]:
    if not path.is_file() or _sha256(path) != expected_hash:
        raise PipelineError("Mascara da auditoria multifasica ausente ou adulterada.")
    image = sitk.ReadImage(str(path))
    array = sitk.GetArrayFromImage(image) > 0
    return image, array


def _geometry_equal(left: sitk.Image, right: sitk.Image) -> bool:
    return (
        left.GetSize() == right.GetSize()
        and np.allclose(left.GetSpacing(), right.GetSpacing(), rtol=0, atol=1e-5)
        and np.allclose(left.GetOrigin(), right.GetOrigin(), rtol=0, atol=1e-3)
        and np.allclose(left.GetDirection(), right.GetDirection(), rtol=0, atol=1e-6)
    )


def audit_arterial_union_pilot(
    *,
    union_localizer_root: Path,
    venous_localizer_root: Path,
    authorized_extraction_root: Path,
    output_root: Path,
) -> dict[str, Any]:
    """Compare already-frozen masks; never expose masks to an inference path."""

    paths = tuple(
        map(
            Path,
            (
                union_localizer_root,
                venous_localizer_root,
                authorized_extraction_root,
                output_root,
            ),
        )
    )
    _refuse_holdout(*paths)
    union_root, venous_root, extraction_root, output_root = paths
    summary = _load(union_root / "summary.json")
    extraction = _load(extraction_root / "extraction_manifest.json")
    if (
        summary.get("schema") != RUN_SCHEMA
        or summary.get("algorithm_version") != ALGORITHM_VERSION
        or summary.get("status") != "complete_scores_only_no_decision"
        or summary.get("ground_truth_read") is not False
        or summary.get("ground_truth_lesion_mask_used") is not False
        or summary.get("final_decision") is not None
        or extraction.get("schema") != EXTRACTION_SCHEMA
    ):
        raise PipelineError("Fontes da auditoria multifasica invalidas.")
    extraction_by_case: dict[str, list[dict[str, Any]]] = {}
    for item in extraction.get("masks", []):
        extraction_by_case.setdefault(str(item.get("case_id", "")), []).append(item)

    rows: list[dict[str, Any]] = []
    for case_id in summary.get("case_ids", []):
        union_manifest = _load(union_root / case_id / "localizer_manifest.json")
        venous_manifest = _load(venous_root / case_id / "localizer_manifest.json")
        if (
            union_manifest.get("schema") != CASE_SCHEMA
            or venous_manifest.get("schema") != CASE_SCHEMA
            or union_manifest.get("case_id") != case_id
            or venous_manifest.get("case_id") != case_id
            or union_manifest.get("ground_truth_read") is not False
            or venous_manifest.get("ground_truth_read") is not False
        ):
            raise PipelineError("Manifesto cego invalido na auditoria multifasica.")
        union_img, union = _mask(
            union_root / case_id / "liver_lesion_candidates_in_liver.nii.gz",
            union_manifest["filtered_candidate_mask_sha256"],
        )
        venous_img, venous = _mask(
            venous_root / case_id / "liver_lesion_candidates_in_liver.nii.gz",
            venous_manifest["filtered_candidate_mask_sha256"],
        )
        if not _geometry_equal(union_img, venous_img):
            raise PipelineError("Geometria venosa/union divergiu na auditoria.")
        records = sorted(
            extraction_by_case.get(case_id, []), key=lambda item: item["lesion_id"]
        )
        venous_hits = union_hits = 0
        for item in records:
            lesion_img, lesion = _mask(
                extraction_root / item["relative_path"], item["sha256"]
            )
            if not _geometry_equal(union_img, lesion_img):
                raise PipelineError("Geometria da mascara publica divergiu na auditoria.")
            venous_hits += int(np.any(lesion & venous))
            union_hits += int(np.any(lesion & union))
        rows.append(
            {
                "case_id": case_id,
                "manual_venous_lesion_count": len(records),
                "venous_case_hit": bool(venous_hits) if records else None,
                "union_case_hit": bool(union_hits) if records else None,
                "case_rescued_by_arterial": bool(union_hits and not venous_hits)
                if records
                else None,
                "venous_lesion_hits": venous_hits,
                "union_lesion_hits": union_hits,
                "venous_candidate_voxels": int(venous.sum()),
                "union_candidate_voxels": int(union.sum()),
                "new_arterial_voxels": int((union & ~venous).sum()),
                "combined_seconds": float(union_manifest["elapsed_seconds"]),
            }
        )

    with_masks = [row for row in rows if row["manual_venous_lesion_count"] > 0]
    result: dict[str, Any] = {
        "schema": AUDIT_SCHEMA,
        "status": "retrospective_development_pilot_complete",
        "case_count": len(rows),
        "cases_with_manual_venous_masks": len(with_masks),
        "venous_case_hits": sum(bool(row["venous_case_hit"]) for row in with_masks),
        "union_case_hits": sum(bool(row["union_case_hit"]) for row in with_masks),
        "cases_rescued_by_arterial": sum(
            bool(row["case_rescued_by_arterial"]) for row in with_masks
        ),
        "venous_lesion_hits": sum(row["venous_lesion_hits"] for row in with_masks),
        "union_lesion_hits": sum(row["union_lesion_hits"] for row in with_masks),
        "max_combined_seconds": max(row["combined_seconds"] for row in rows),
        "rows": rows,
        "inference_executed": False,
        "medgemma_called": False,
        "lesion_masks_used_for_inference": False,
        "lesion_masks_sent_to_medgemma": False,
        "holdout_opened": False,
        "development_only": True,
        "qualified": False,
        "research_only": True,
        "clinical_use_allowed": False,
        "requires_human_review": True,
    }
    if output_root.exists():
        raise PipelineError("Saida da auditoria multifasica ja existe.")
    output_root.parent.mkdir(parents=True, exist_ok=True)
    staging = output_root.parent / f"._v22multi_audit_{uuid.uuid4().hex[:8]}"
    staging.mkdir()
    try:
        _write_json_atomic(staging / "audit.json", result)
        _publish_directory(staging, output_root)
        return result
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise


__all__ = ["AUDIT_SCHEMA", "audit_arterial_union_pilot"]
