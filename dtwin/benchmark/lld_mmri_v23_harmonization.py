"""Explicit physical-grid harmonization for LLD-MMRI v23 dynamic T1 phases."""
from __future__ import annotations

import json
import math
import os
import shutil
import time
import uuid
from pathlib import Path
from typing import Any

import numpy as np
import SimpleITK as sitk

from dtwin.benchmark.lld_mmri_v23_download import validate_lld_mmri_v23_download
from dtwin.benchmark.lld_mmri_v23_geometry_audit import AUDIT_SCHEMA, CASE_SCHEMA as AUDIT_CASE_SCHEMA
from dtwin.benchmark.lld_mmri_v23_preparation import _geometry, _read_valid_nifti, _same_geometry
from dtwin.benchmark.openswisshcc_alignment import _publish_directory, _sha256
from dtwin.benchmark.openswisshcc_v20_fusion import _canonical_sha
from dtwin.core import PipelineError
from dtwin.medgemma_screening import _write_json_atomic


HARMONIZATION_SCHEMA = "argos-lld-mmri-v23-dynamic-t1-harmonization-v1"
CASE_SCHEMA = "argos-lld-mmri-v23-dynamic-t1-harmonized-case-v1"
DYNAMIC_ROLES = ("t1_native", "t1_arterial", "t1_venous", "t1_delayed")
ALGORITHM_VERSION = "identity-physical-grid-to-venous-linear-v1"
LIVER_SUPPORT_THRESHOLD = 0.99


def _json(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PipelineError(f"{label} ausente ou invalido.") from exc
    if not isinstance(value, dict):
        raise PipelineError(f"{label} deve ser objeto.")
    return value


def _jsonl(path: Path, label: str) -> list[dict[str, Any]]:
    try:
        rows = [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]
    except (OSError, json.JSONDecodeError) as exc:
        raise PipelineError(f"{label} ausente ou invalido.") from exc
    if not rows or any(not isinstance(row, dict) for row in rows):
        raise PipelineError(f"{label} vazio ou invalido.")
    return rows


def _validate_failed_audit(audit_root: Path, manifest: dict[str, Any]) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    audit_root = Path(audit_root).resolve()
    summary = _json(audit_root / "summary.json", "Resumo da auditoria geometrica")
    cases_path = audit_root / "cases.jsonl"
    rows = _jsonl(cases_path, "Casos da auditoria geometrica")
    unsigned = dict(summary)
    signature = unsigned.pop("audit_signature", None)
    case_ids = [case["case_id"] for case in manifest["cases"]]
    if (
        summary.get("schema") != AUDIT_SCHEMA
        or summary.get("status") != "failed_do_not_segment"
        or summary.get("technical_gate_passed") is not False
        or signature != _canonical_sha(unsigned)
        or summary.get("cases_sha256") != _sha256(cases_path)
        or summary.get("protocol_signature") != manifest["protocol_signature"]
        or summary.get("download_manifest_signature") != manifest["manifest_signature"]
        or summary.get("case_count") != manifest["case_count"]
        or summary.get("image_count") != manifest["image_count"]
        or summary.get("case_ids") != case_ids
        or summary.get("ground_truth_read") is not False
        or summary.get("labels_read") is not False
        or summary.get("lesion_masks_read") != 0
        or len(rows) != manifest["case_count"]
    ):
        raise PipelineError("Auditoria geometrica falha LLD-MMRI invalida ou adulterada.")
    indexed = {}
    for case_id, row in zip(case_ids, rows, strict=True):
        unsigned_row = dict(row)
        row_signature = unsigned_row.pop("case_audit_signature", None)
        if (
            row.get("schema") != AUDIT_CASE_SCHEMA
            or row.get("case_id") != case_id
            or row_signature != _canonical_sha(unsigned_row)
            or row.get("ground_truth_read") is not False
            or row.get("lesion_masks_read") != 0
        ):
            raise PipelineError("Caso da auditoria geometrica LLD-MMRI invalido.")
        indexed[case_id] = row
    return summary, indexed


def _materialize(source: Path, destination: Path) -> str:
    try:
        os.link(source, destination)
        return "hardlink"
    except OSError:
        shutil.copyfile(source, destination)
        return "copy"


def _harmonize(moving: sitk.Image, reference: sitk.Image) -> tuple[sitk.Image, float]:
    identity = sitk.Transform(3, sitk.sitkIdentity)
    output = sitk.Resample(
        sitk.Cast(moving, sitk.sitkFloat32),
        reference,
        identity,
        sitk.sitkLinear,
        0.0,
        sitk.sitkFloat32,
    )
    support_source = sitk.Image(moving.GetSize(), sitk.sitkUInt8) + 1
    support_source.CopyInformation(moving)
    support = sitk.Resample(
        support_source,
        reference,
        identity,
        sitk.sitkNearestNeighbor,
        0,
        sitk.sitkUInt8,
    )
    coverage = float(np.count_nonzero(sitk.GetArrayViewFromImage(support))) / float(
        np.prod(reference.GetSize())
    )
    return output, coverage


def dynamic_liver_support_fractions(
    harmonized_case: dict[str, Any], liver_mask: sitk.Image
) -> dict[str, float]:
    """Measure source-grid support over an automatic liver mask, without labels."""

    liver = np.asarray(sitk.GetArrayFromImage(liver_mask)) > 0
    liver_voxels = int(liver.sum())
    files = harmonized_case.get("files") if isinstance(harmonized_case, dict) else None
    if liver_voxels <= 0 or not isinstance(files, list):
        raise PipelineError("Mascara ou caso harmonizado invalido para cobertura hepatica.")
    by_role = {str(item.get("role")): item for item in files}
    if set(by_role) != set(DYNAMIC_ROLES):
        raise PipelineError("Fases harmonizadas incompletas para cobertura hepatica.")
    fractions = {}
    for role in DYNAMIC_ROLES:
        geometry = by_role[role].get("source_geometry")
        if not isinstance(geometry, dict):
            raise PipelineError("Geometria fonte ausente para cobertura hepatica.")
        support_source = sitk.Image(
            [int(value) for value in geometry["size_xyz"]], sitk.sitkUInt8
        ) + 1
        support_source.SetSpacing(tuple(float(value) for value in geometry["spacing_xyz"]))
        support_source.SetOrigin(tuple(float(value) for value in geometry["origin_xyz"]))
        support_source.SetDirection(tuple(float(value) for value in geometry["direction"]))
        support = sitk.Resample(
            support_source,
            liver_mask,
            sitk.Transform(3, sitk.sitkIdentity),
            sitk.sitkNearestNeighbor,
            0,
            sitk.sitkUInt8,
        )
        supported = np.asarray(sitk.GetArrayFromImage(support)) > 0
        fractions[role] = float(np.count_nonzero(liver & supported)) / float(liver_voxels)
    return fractions


def harmonize_lld_mmri_v23_dynamic_t1(
    *, protocol_root: Path, download_root: Path, failed_audit_root: Path, output_root: Path
) -> dict[str, Any]:
    """Harmonize grids only; do not claim motion correction or inference eligibility."""

    download_root = Path(download_root).resolve()
    manifest = validate_lld_mmri_v23_download(protocol_root=protocol_root, destination=download_root)
    audit, audited = _validate_failed_audit(failed_audit_root, manifest)
    output_root = Path(output_root).resolve()
    if output_root.exists():
        raise PipelineError("Harmonizacao LLD-MMRI existente; sobrescrita recusada.")
    output_root.parent.mkdir(parents=True, exist_ok=True)
    staging = output_root.parent / f"._lldv23harm_{uuid.uuid4().hex[:8]}"
    staging.mkdir()
    rows = []
    started_all = time.perf_counter()
    try:
        cases_root = staging / "cases"
        cases_root.mkdir()
        for case in manifest["cases"]:
            case_started = time.perf_counter()
            case_id = str(case["case_id"])
            audit_row = audited[case_id]
            sources = {}
            images = {}
            for role in DYNAMIC_ROLES:
                item = case["images"][role]
                source = (download_root / str(item["relative_path"])).resolve()
                if not source.is_relative_to(download_root) or _sha256(source) != item["sha256"]:
                    raise PipelineError("Fonte dinamica LLD-MMRI mudou antes da harmonizacao.")
                sources[role] = source
                images[role] = _read_valid_nifti(source, role=role)
            reference = images["t1_venous"]
            case_dir = cases_root / case_id
            case_dir.mkdir()
            files = []
            for role in DYNAMIC_ROLES:
                destination = case_dir / f"{role}.nii.gz"
                transformed = not _same_geometry(images[role], reference)
                if transformed:
                    output, coverage = _harmonize(images[role], reference)
                    sitk.WriteImage(output, str(destination), useCompression=True)
                    method = "identity_physical_resample_linear_float32"
                else:
                    method = _materialize(sources[role], destination)
                    coverage = 1.0
                persisted = _read_valid_nifti(destination, role=role)
                if not _same_geometry(persisted, reference):
                    raise PipelineError("Harmonizacao LLD-MMRI nao produziu a grade venosa exata.")
                files.append(
                    {
                        "role": role,
                        "relative_path": f"cases/{case_id}/{destination.name}",
                        "bytes": destination.stat().st_size,
                        "sha256": _sha256(destination),
                        "source_sha256": case["images"][role]["sha256"],
                        "source_geometry": _geometry(images[role]),
                        "output_geometry": _geometry(persisted),
                        "transformed": transformed,
                        "method": method,
                        "whole_reference_grid_support_fraction": coverage,
                    }
                )
            base = {
                "schema": CASE_SCHEMA,
                "case_id": case_id,
                "status": "harmonized_pending_liver_coverage_and_human_review",
                "algorithm_version": ALGORITHM_VERSION,
                "reference_role": "t1_venous",
                "files": files,
                "source_audit_case_signature": audit_row["case_audit_signature"],
                "motion_correction_claimed": False,
                "anatomical_registration_claimed": False,
                "eligible_for_inference": False,
                "elapsed_seconds": time.perf_counter() - case_started,
                "ground_truth_read": False,
                "labels_read": False,
                "lesion_masks_read": 0,
                "research_only": True,
                "clinical_use_allowed": False,
                "requires_human_review": True,
            }
            row = dict(base)
            row["case_harmonization_signature"] = _canonical_sha(base)
            rows.append(row)
        rows_path = staging / "cases.jsonl"
        rows_path.write_text(
            "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows),
            encoding="utf-8",
        )
        transformed = [item for row in rows for item in row["files"] if item["transformed"]]
        base = {
            "schema": HARMONIZATION_SCHEMA,
            "status": "complete_pending_liver_coverage_and_human_review",
            "algorithm_version": ALGORITHM_VERSION,
            "case_count": len(rows),
            "case_ids": [row["case_id"] for row in rows],
            "dynamic_image_count": len(rows) * len(DYNAMIC_ROLES),
            "transformed_image_count": len(transformed),
            "unchanged_image_count": len(rows) * len(DYNAMIC_ROLES) - len(transformed),
            "minimum_whole_grid_support_fraction": min(
                item["whole_reference_grid_support_fraction"] for item in transformed
            ),
            "cases_sha256": _sha256(rows_path),
            "protocol_signature": manifest["protocol_signature"],
            "download_manifest_signature": manifest["manifest_signature"],
            "source_failed_audit_signature": audit["audit_signature"],
            "reference_role": "t1_venous",
            "transform": "identity_in_physical_coordinates",
            "interpolator": "linear",
            "output_pixel_type_for_transformed": "float32",
            "default_value": 0.0,
            "motion_correction_claimed": False,
            "anatomical_registration_claimed": False,
            "liver_support_gate_evaluated": False,
            "human_review_completed": False,
            "eligible_for_inference": False,
            "elapsed_seconds": time.perf_counter() - started_all,
            "ground_truth_read": False,
            "labels_read": False,
            "lesion_masks_read": 0,
            "research_only": True,
            "clinical_use_allowed": False,
            "requires_human_review": True,
        }
        summary = dict(base)
        summary["harmonization_signature"] = _canonical_sha(base)
        _write_json_atomic(staging / "summary.json", summary)
        _publish_directory(staging, output_root)
        return summary
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def verify_lld_mmri_v23_harmonization(
    *, protocol_root: Path, download_root: Path, failed_audit_root: Path, harmonization_root: Path
) -> dict[str, Any]:
    """Re-read every harmonized phase and validate all hashes and grids."""

    manifest = validate_lld_mmri_v23_download(protocol_root=protocol_root, destination=download_root)
    audit, _ = _validate_failed_audit(failed_audit_root, manifest)
    root = Path(harmonization_root).resolve()
    summary = _json(root / "summary.json", "Resumo da harmonizacao LLD-MMRI")
    rows_path = root / "cases.jsonl"
    rows = _jsonl(rows_path, "Casos harmonizados LLD-MMRI")
    unsigned = dict(summary)
    signature = unsigned.pop("harmonization_signature", None)
    if (
        summary.get("schema") != HARMONIZATION_SCHEMA
        or summary.get("status") != "complete_pending_liver_coverage_and_human_review"
        or signature != _canonical_sha(unsigned)
        or summary.get("algorithm_version") != ALGORITHM_VERSION
        or summary.get("case_ids") != [case["case_id"] for case in manifest["cases"]]
        or summary.get("case_count") != manifest["case_count"]
        or summary.get("dynamic_image_count") != manifest["case_count"] * len(DYNAMIC_ROLES)
        or summary.get("cases_sha256") != _sha256(rows_path)
        or summary.get("protocol_signature") != manifest["protocol_signature"]
        or summary.get("download_manifest_signature") != manifest["manifest_signature"]
        or summary.get("source_failed_audit_signature") != audit["audit_signature"]
        or summary.get("motion_correction_claimed") is not False
        or summary.get("anatomical_registration_claimed") is not False
        or summary.get("eligible_for_inference") is not False
        or summary.get("ground_truth_read") is not False
        or summary.get("labels_read") is not False
        or summary.get("lesion_masks_read") != 0
        or len(rows) != manifest["case_count"]
    ):
        raise PipelineError("Resumo da harmonizacao LLD-MMRI invalido ou adulterado.")
    transformed = 0
    for case, row in zip(manifest["cases"], rows, strict=True):
        unsigned_row = dict(row)
        row_signature = unsigned_row.pop("case_harmonization_signature", None)
        files = row.get("files")
        if (
            row.get("schema") != CASE_SCHEMA
            or row.get("case_id") != case["case_id"]
            or row_signature != _canonical_sha(unsigned_row)
            or row.get("algorithm_version") != ALGORITHM_VERSION
            or row.get("eligible_for_inference") is not False
            or row.get("ground_truth_read") is not False
            or row.get("labels_read") is not False
            or row.get("lesion_masks_read") != 0
            or not isinstance(files, list)
            or [item.get("role") for item in files] != list(DYNAMIC_ROLES)
        ):
            raise PipelineError("Caso harmonizado LLD-MMRI invalido.")
        images = {}
        for item in files:
            path = (root / str(item["relative_path"])).resolve()
            coverage = item.get("whole_reference_grid_support_fraction")
            if (
                not path.is_relative_to(root)
                or not path.is_file()
                or path.stat().st_size != item.get("bytes")
                or _sha256(path) != item.get("sha256")
                or item.get("source_sha256") != case["images"][item["role"]]["sha256"]
                or isinstance(coverage, bool)
                or not isinstance(coverage, (int, float))
                or not math.isfinite(float(coverage))
                or not 0 < float(coverage) <= 1
            ):
                raise PipelineError("Arquivo harmonizado LLD-MMRI ausente ou adulterado.")
            image = _read_valid_nifti(path, role=item["role"])
            if item.get("output_geometry") != _geometry(image):
                raise PipelineError("Geometria harmonizada LLD-MMRI divergiu do arquivo.")
            images[item["role"]] = image
            transformed += bool(item.get("transformed"))
        if any(not _same_geometry(images["t1_venous"], images[role]) for role in DYNAMIC_ROLES):
            raise PipelineError("Fases harmonizadas LLD-MMRI nao compartilham a grade venosa.")
    if transformed != summary.get("transformed_image_count"):
        raise PipelineError("Contagem de fases harmonizadas LLD-MMRI divergiu.")
    return summary


__all__ = [
    "ALGORITHM_VERSION",
    "CASE_SCHEMA",
    "DYNAMIC_ROLES",
    "HARMONIZATION_SCHEMA",
    "LIVER_SUPPORT_THRESHOLD",
    "harmonize_lld_mmri_v23_dynamic_t1",
    "dynamic_liver_support_fractions",
    "verify_lld_mmri_v23_harmonization",
]
