"""Label-blind anatomical plausibility gate for automatic LLD-MMRI liver masks."""
from __future__ import annotations

import math
import os
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

import SimpleITK as sitk

from dtwin.benchmark.lld_mmri_v23_preparation import _read_valid_nifti, _same_geometry
from dtwin.core import PipelineError

MASK_QUALITY_POLICY = "physical_liver_plausibility_largest_component_v1"
MINIMUM_LIVER_VOLUME_ML = 300.0
MINIMUM_AXIAL_EXTENT_MM = 60.0
MINIMUM_INPLANE_EXTENT_MM = 70.0
MINIMUM_LARGEST_COMPONENT_FRACTION = 0.90


def _component_metrics(mask_image: sitk.Image) -> tuple[sitk.Image | None, dict[str, Any]]:
    binary = sitk.Cast(mask_image > 0, sitk.sitkUInt8)
    components = sitk.ConnectedComponent(binary, True)
    statistics = sitk.LabelShapeStatisticsImageFilter()
    statistics.Execute(components)
    labels = list(statistics.GetLabels())
    total_voxels = sum(int(statistics.GetNumberOfPixels(label)) for label in labels)
    if not labels or total_voxels == 0:
        return None, {
            "raw_liver_voxels": 0,
            "component_count": 0,
            "largest_component_voxels": 0,
            "largest_component_fraction": 0.0,
        }
    largest = max(labels, key=lambda label: statistics.GetNumberOfPixels(label))
    largest_voxels = int(statistics.GetNumberOfPixels(largest))
    largest_mask = sitk.Cast(components == largest, sitk.sitkUInt8)
    largest_mask.CopyInformation(mask_image)
    return largest_mask, {
        "raw_liver_voxels": total_voxels,
        "component_count": len(labels),
        "largest_component_voxels": largest_voxels,
        "largest_component_fraction": largest_voxels / total_voxels,
    }


def evaluate_liver_mask_quality(mask_path: Path, reference: sitk.Image) -> dict[str, Any]:
    """Evaluate geometry and conservative adult-liver plausibility without labels."""

    mask_path = Path(mask_path).resolve()
    if not mask_path.is_file():
        return {"policy": MASK_QUALITY_POLICY, "gate_passed": False, "failure_reasons": ["mask_missing"]}
    mask_image = _read_valid_nifti(mask_path, role="liver_mask_venous")
    same_geometry = _same_geometry(reference, mask_image)
    largest_mask, metrics = _component_metrics(mask_image)
    spacing = tuple(float(value) for value in mask_image.GetSpacing())
    voxel_volume_ml = math.prod(spacing) / 1000.0
    if largest_mask is None:
        volume_ml = 0.0
        extents_mm = [0.0, 0.0, 0.0]
    else:
        shape = sitk.LabelShapeStatisticsImageFilter()
        shape.Execute(largest_mask)
        bounding_box = shape.GetBoundingBox(1)
        sizes = bounding_box[3:]
        extents_mm = [float(sizes[index]) * spacing[index] for index in range(3)]
        volume_ml = metrics["largest_component_voxels"] * voxel_volume_ml
    reasons: list[str] = []
    if not same_geometry:
        reasons.append("geometry_mismatch")
    if volume_ml < MINIMUM_LIVER_VOLUME_ML:
        reasons.append("physical_volume_below_minimum")
    if extents_mm[2] < MINIMUM_AXIAL_EXTENT_MM:
        reasons.append("axial_extent_below_minimum")
    if min(extents_mm[:2]) < MINIMUM_INPLANE_EXTENT_MM:
        reasons.append("inplane_extent_below_minimum")
    if metrics["largest_component_fraction"] < MINIMUM_LARGEST_COMPONENT_FRACTION:
        reasons.append("excessive_fragmentation")
    return {
        "policy": MASK_QUALITY_POLICY,
        "gate_passed": not reasons,
        "failure_reasons": reasons,
        "same_geometry": same_geometry,
        **metrics,
        "largest_component_volume_ml": volume_ml,
        "largest_component_extent_mm_xyz": extents_mm,
        "thresholds": {
            "minimum_liver_volume_ml": MINIMUM_LIVER_VOLUME_ML,
            "minimum_axial_extent_mm": MINIMUM_AXIAL_EXTENT_MM,
            "minimum_inplane_extent_mm": MINIMUM_INPLANE_EXTENT_MM,
            "minimum_largest_component_fraction": MINIMUM_LARGEST_COMPONENT_FRACTION,
        },
    }


def anatomically_gated_segmenter(
    source: Path,
    destination: Path,
    *,
    segmenter: Callable[[Path, Path], dict[str, Any] | None],
) -> dict[str, Any]:
    """Run a segmenter, reject implausible masks and retain only the liver component."""

    receipt = dict(segmenter(source, destination) or {})
    reference = _read_valid_nifti(Path(source), role="t1_venous")
    quality = evaluate_liver_mask_quality(destination, reference)
    receipt["mask_quality_gate"] = quality
    if not quality["gate_passed"]:
        Path(destination).unlink(missing_ok=True)
        raise PipelineError(
            "Mascara hepatica falhou no gate anatomico label-blind: "
            + ", ".join(quality["failure_reasons"])
        )
    mask_image = _read_valid_nifti(Path(destination), role="liver_mask_venous")
    largest_mask, _ = _component_metrics(mask_image)
    if largest_mask is None:
        Path(destination).unlink(missing_ok=True)
        raise PipelineError("Mascara hepatica vazia apos gate anatomico.")
    temporary = Path(destination).with_name(f".{Path(destination).name}.{uuid.uuid4().hex[:8]}.tmp.nii.gz")
    sitk.WriteImage(largest_mask, str(temporary), useCompression=True)
    os.replace(temporary, destination)
    receipt["postprocessing"] = "largest_3d_connected_component_only"
    return receipt
