"""Blind whole-liver deterministic enhancement proposals for v22."""
from __future__ import annotations

import os
import shutil
import time
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np
import SimpleITK as sitk
from scipy import ndimage

from dtwin.benchmark.openswisshcc_alignment import _publish_directory, _sha256
from dtwin.benchmark.openswisshcc_enhancement_maps import (
    _compute_enhancement_state,
    _input_index,
    _registered_paths,
    _selection,
)
from dtwin.core import PipelineError
from dtwin.medgemma_screening import _write_json_atomic

CASE_SCHEMA = "argos-openswisshcc-enhancement-localizer-case-v22"
COHORT_SCHEMA = "argos-openswisshcc-enhancement-localizer-cohort-v22"
ALGORITHM_VERSION = "whole-liver-joint-enhancement-proposals-v1"
THRESHOLDS = (2.0, 3.0, 4.0)
MIN_COMPONENT_VOXELS = 8


def _threshold_key(value: float) -> str:
    return f"t{int(value)}"


def build_enhancement_proposals(
    *, joint_enhancement: np.ndarray, analysis_mask: np.ndarray, spacing_xyz: tuple[float, ...]
) -> dict[str, dict[str, Any]]:
    """Build predeclared connected-component proposal masks without labels."""

    joint = np.asarray(joint_enhancement, dtype=np.float32)
    analysis = np.asarray(analysis_mask, dtype=bool)
    if joint.shape != analysis.shape or not np.isfinite(joint[analysis]).all():
        raise PipelineError("Mapa conjunto invalido no localizador de realce v22.")
    voxel_volume = float(np.prod(spacing_xyz))
    result: dict[str, dict[str, Any]] = {}
    structure = ndimage.generate_binary_structure(3, 2)
    for threshold in THRESHOLDS:
        raw = analysis & (joint >= threshold)
        labels, count = ndimage.label(raw, structure=structure)
        sizes = np.bincount(labels.ravel(), minlength=int(count) + 1)
        keep_ids = np.flatnonzero(sizes >= MIN_COMPONENT_VOXELS)
        keep_ids = keep_ids[keep_ids != 0]
        mask = np.isin(labels, keep_ids)
        component_sizes = sorted(
            (int(sizes[index]) for index in keep_ids), reverse=True
        )
        result[_threshold_key(threshold)] = {
            "threshold": threshold,
            "mask": mask,
            "raw_voxels": int(raw.sum()),
            "proposal_voxels": int(mask.sum()),
            "proposal_volume_mm3": float(mask.sum() * voxel_volume),
            "component_count": len(component_sizes),
            "largest_component_voxels": component_sizes[0] if component_sizes else 0,
            "largest_component_mm3": float(component_sizes[0] * voxel_volume)
            if component_sizes
            else 0.0,
        }
    return result


def _save_mask_atomic(mask: np.ndarray, reference: sitk.Image, path: Path) -> None:
    image = sitk.GetImageFromArray(np.asarray(mask, dtype=np.uint8))
    image.CopyInformation(reference)
    temporary = path.with_name(f"._p_{uuid.uuid4().hex[:8]}.nii.gz")
    try:
        sitk.WriteImage(image, str(temporary), True)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def build_enhancement_localizer_cohort(
    *,
    input_manifest_path: Path,
    input_root: Path,
    alignment_root: Path,
    selection_manifest_path: Path,
    output_root: Path,
    progress: Callable[[int, int, str, float], None] | None = None,
) -> dict[str, Any]:
    """Generate blind whole-liver proposals for full87 in frozen order."""

    case_ids, modes = _selection(selection_manifest_path)
    inputs = _input_index(input_manifest_path, input_root)
    if any(case_id not in inputs for case_id in case_ids):
        raise PipelineError("Input ausente no localizador de realce v22.")
    output_root = Path(output_root).resolve()
    if output_root.exists():
        raise PipelineError("Destino do localizador de realce v22 ja existe.")
    output_root.parent.mkdir(parents=True, exist_ok=True)
    staging = output_root.parent / f"._v22enh_loc_{uuid.uuid4().hex[:8]}"
    staging.mkdir()
    records: list[dict[str, Any]] = []
    try:
        for index, case_id in enumerate(case_ids, 1):
            started = time.monotonic()
            base: dict[str, Any] = {
                "schema": CASE_SCHEMA,
                "case_id": case_id,
                "algorithm_version": ALGORITHM_VERSION,
                "dynamic_alignment_mode": modes[case_id],
                "ground_truth_read": False,
                "ground_truth_lesion_mask_used": False,
                "metrics_calculated": False,
                "final_decision": None,
                "research_only": True,
                "clinical_use_allowed": False,
                "requires_human_review": True,
            }
            if modes[case_id] != "registered_to_venous":
                record = {
                    **base,
                    "status": "unavailable_unregistered_fallback",
                    "proposals": None,
                    "elapsed_seconds": 0.0,
                }
                records.append(record)
                if progress:
                    progress(index, len(case_ids), case_id, 0.0)
                continue
            source = inputs[case_id]
            arterial_path, delayed_path, registered_hashes = _registered_paths(
                case_id, alignment_root
            )
            venous = sitk.ReadImage(str(source["paths"]["t1_venous"]))
            state = _compute_enhancement_state(
                arterial=sitk.ReadImage(str(arterial_path)),
                venous=venous,
                delayed=sitk.ReadImage(str(delayed_path)),
                liver_mask=sitk.ReadImage(str(source["paths"]["liver_mask_venous"])),
            )
            proposals = build_enhancement_proposals(
                joint_enhancement=state["joint_enhancement"],
                analysis_mask=state["analysis_mask"],
                spacing_xyz=venous.GetSpacing(),
            )
            case_dir = staging / case_id
            case_dir.mkdir()
            proposal_records = []
            for key, item in proposals.items():
                filename = f"joint_enhancement_proposals_{key}.nii.gz"
                path = case_dir / filename
                _save_mask_atomic(item["mask"], venous, path)
                proposal_records.append(
                    {
                        "threshold_key": key,
                        "threshold": item["threshold"],
                        "filename": filename,
                        "bytes": path.stat().st_size,
                        "sha256": _sha256(path),
                        **{
                            name: value
                            for name, value in item.items()
                            if name not in {"mask", "threshold"}
                        },
                    }
                )
            elapsed = time.monotonic() - started
            record = {
                **base,
                "status": "complete_blind_proposals",
                "analysis_mask_voxels": state["analysis_mask_voxels"],
                "normalization": state["normalization"],
                "proposals": proposal_records,
                "source_hashes": {**source["hashes"], **registered_hashes},
                "elapsed_seconds": round(elapsed, 4),
            }
            _write_json_atomic(case_dir / "manifest.json", record)
            records.append(record)
            if progress:
                progress(index, len(case_ids), case_id, elapsed)

        summary: dict[str, Any] = {
            "schema": COHORT_SCHEMA,
            "status": "complete_blind_proposals_with_declared_fallbacks",
            "algorithm_version": ALGORITHM_VERSION,
            "case_count": len(records),
            "available_case_count": sum(
                row["status"] == "complete_blind_proposals" for row in records
            ),
            "unavailable_case_ids": [
                row["case_id"]
                for row in records
                if row["status"] != "complete_blind_proposals"
            ],
            "case_ids": case_ids,
            "thresholds": list(THRESHOLDS),
            "minimum_component_voxels": MIN_COMPONENT_VOXELS,
            "case_manifest_hashes": {
                row["case_id"]: _sha256(staging / row["case_id"] / "manifest.json")
                for row in records
                if row["status"] == "complete_blind_proposals"
            },
            "max_case_seconds": max(float(row["elapsed_seconds"]) for row in records),
            "labels_read": False,
            "ground_truth_lesion_masks_read": 0,
            "inference_executed": False,
            "research_only": True,
            "clinical_use_allowed": False,
            "requires_human_review": True,
        }
        _write_json_atomic(staging / "summary.json", summary)
        _publish_directory(staging, output_root)
        return summary
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise


__all__ = [
    "ALGORITHM_VERSION",
    "CASE_SCHEMA",
    "COHORT_SCHEMA",
    "THRESHOLDS",
    "build_enhancement_localizer_cohort",
    "build_enhancement_proposals",
]
