"""Phase-aware MRSegmentator adapter restricted to visualization shadow artifacts."""
from __future__ import annotations

import os
import shutil
import uuid
from pathlib import Path
from typing import Any, Callable, Mapping

import SimpleITK as sitk
import numpy as np

from .core import PipelineError
from .segmentation_contract import (
    assert_experimental_output,
    atomic_write_experimental_json,
    build_native_input_manifest,
    build_quality_manifest,
    experimental_paths,
    same_geometry,
)


ARTERIAL_KEYS = ("t1_arterial", "arterial", "art")
SECONDARY_KEYS = ("t1_delayed", "delayed", "t1_venous", "venous")


def _mask_array_on_reference(mask_path: Path, reference_path: Path) -> tuple[np.ndarray, sitk.Image]:
    image = sitk.ReadImage(str(mask_path))
    reference = sitk.ReadImage(str(reference_path))
    if not same_geometry(image, reference):
        image = sitk.Resample(
            image, reference, sitk.Transform(), sitk.sitkNearestNeighbor,
            0, sitk.sitkUInt8,
        )
    return sitk.GetArrayFromImage(image) > 0, reference


def mask_quality_metrics(mask: np.ndarray, reference: sitk.Image) -> dict[str, Any]:
    """Return label-blind mask checks used only to choose a display mask."""

    binary = np.asarray(mask, dtype=bool)
    voxels = int(binary.sum())
    spacing = tuple(float(value) for value in reference.GetSpacing())
    volume_ml = float(voxels * np.prod(spacing) / 1000.0)
    if voxels:
        cc = sitk.ConnectedComponent(sitk.GetImageFromArray(binary.astype(np.uint8)), True)
        stats = sitk.LabelShapeStatisticsImageFilter()
        stats.Execute(cc)
        sizes = sorted(
            (int(stats.GetNumberOfPixels(label)) for label in stats.GetLabels()),
            reverse=True,
        )
    else:
        sizes = []
    border = bool(
        binary[0].any() or binary[-1].any()
        or binary[:, 0].any() or binary[:, -1].any()
        or binary[:, :, 0].any() or binary[:, :, -1].any()
    ) if binary.size else False
    return {
        "foreground_voxels": voxels,
        "volume_ml": volume_ml,
        "component_count": len(sizes),
        "largest_component_fraction": float(sizes[0] / voxels) if sizes and voxels else 0.0,
        "touches_image_border": border,
    }


def mask_agreement(left: np.ndarray, right: np.ndarray) -> dict[str, float]:
    left = np.asarray(left, dtype=bool)
    right = np.asarray(right, dtype=bool)
    intersection = int(np.count_nonzero(left & right))
    left_count = int(left.sum())
    right_count = int(right.sum())
    union = int(np.count_nonzero(left | right))
    return {
        "dice": float(2 * intersection / (left_count + right_count))
        if left_count + right_count else 1.0,
        "jaccard": float(intersection / union) if union else 1.0,
        "left_to_right_volume_ratio": float(left_count / right_count) if right_count else 0.0,
    }


def protected_adaptive_fusion(
    primary: np.ndarray,
    secondary: np.ndarray,
    *,
    spacing_xyz: tuple[float, float, float],
    maximum_extension_mm: float = 12.0,
    maximum_added_fraction: float = 0.18,
) -> tuple[np.ndarray, dict[str, Any]]:
    """Fuse a second mask only near the primary and reject unsafe expansion."""

    primary = np.asarray(primary, dtype=bool)
    secondary = np.asarray(secondary, dtype=bool)
    if not primary.any() or not secondary.any():
        return primary.copy(), {"accepted": False, "reason": "empty_input_mask"}
    primary_image = sitk.GetImageFromArray(primary.astype(np.uint8))
    primary_image.SetSpacing(tuple(float(value) for value in spacing_xyz))
    distance = sitk.GetArrayFromImage(
        sitk.Abs(sitk.SignedMaurerDistanceMap(
            primary_image, insideIsPositive=False, squaredDistance=False,
            useImageSpacing=True,
        ))
    )
    extension = secondary & ~primary & (distance <= float(maximum_extension_mm))
    candidate = primary | extension
    candidate_image = sitk.GetImageFromArray(candidate.astype(np.uint8))
    candidate_image.SetSpacing(tuple(float(value) for value in spacing_xyz))
    candidate_image = sitk.BinaryFillhole(candidate_image, fullyConnected=True)
    cc = sitk.ConnectedComponent(candidate_image, True)
    relabel = sitk.RelabelComponent(cc, sortByObjectSize=True)
    candidate = sitk.GetArrayFromImage(relabel == 1) > 0
    primary_count = int(primary.sum())
    candidate_count = int(candidate.sum())
    added_fraction = float(max(candidate_count - primary_count, 0) / primary_count)
    primary_border = mask_quality_metrics(primary, primary_image)["touches_image_border"]
    candidate_border = mask_quality_metrics(candidate, candidate_image)["touches_image_border"]
    if added_fraction > float(maximum_added_fraction):
        return primary.copy(), {
            "accepted": False,
            "reason": "maximum_added_fraction_exceeded",
            "added_fraction": added_fraction,
        }
    if candidate_border and not primary_border:
        return primary.copy(), {
            "accepted": False,
            "reason": "new_image_border_contact",
            "added_fraction": added_fraction,
        }
    return candidate, {
        "accepted": True,
        "reason": "protected_near_primary_union",
        "added_fraction": added_fraction,
        "maximum_extension_mm": float(maximum_extension_mm),
    }


def select_secondary_source(
    *, phase_paths: Mapping[str, Path | str], reference_volume: Path | str,
    primary_source: Path | str,
) -> dict[str, Any] | None:
    reference_path = Path(reference_volume).resolve()
    reference = sitk.ReadImage(str(reference_path))
    primary = Path(primary_source).resolve()
    for key in SECONDARY_KEYS:
        value = phase_paths.get(key)
        if value is None:
            continue
        candidate = Path(value).resolve()
        if candidate == primary or not candidate.is_file():
            continue
        if same_geometry(sitk.ReadImage(str(candidate)), reference):
            return {"source_path": candidate, "selected_phase": key}
    if reference_path != primary:
        return {"source_path": reference_path, "selected_phase": "reference"}
    return None


def should_run_secondary(
    primary_metrics: Mapping[str, Any], baseline_metrics: Mapping[str, Any] | None,
    *, fallback_used: bool,
) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    if fallback_used:
        reasons.append("primary_phase_fallback")
    if int(primary_metrics.get("component_count", 0)) != 1:
        reasons.append("primary_not_single_component")
    if float(primary_metrics.get("largest_component_fraction", 0.0)) < 0.985:
        reasons.append("primary_fragmented")
    if bool(primary_metrics.get("touches_image_border")):
        reasons.append("primary_touches_image_border")
    if baseline_metrics and float(baseline_metrics.get("volume_ml", 0.0)) > 0:
        ratio = float(primary_metrics.get("volume_ml", 0.0)) / float(baseline_metrics["volume_ml"])
        if ratio < 0.82 or ratio > 1.30:
            reasons.append("primary_baseline_volume_disagreement")
    return bool(reasons), reasons


def select_phase_aware_source(
    *,
    phase_paths: Mapping[str, Path | str],
    reference_volume: Path | str,
) -> dict[str, Any]:
    """Prefer a registered arterial phase; otherwise use the reference volume."""

    reference_path = Path(reference_volume).resolve()
    if not reference_path.is_file():
        raise PipelineError("Volume de referencia do shadow mode ausente.")
    reference = sitk.ReadImage(str(reference_path))
    arterial_path: Path | None = None
    for key in ARTERIAL_KEYS:
        value = phase_paths.get(key)
        if value is not None and Path(value).is_file():
            arterial_path = Path(value).resolve()
            break
    fallback_reason: str | None = None
    if arterial_path is not None:
        arterial = sitk.ReadImage(str(arterial_path))
        if same_geometry(arterial, reference):
            return {
                "source_path": arterial_path,
                "source_role": "t1_arterial_registered",
                "selected_phase": "arterial",
                "fallback_used": False,
                "fallback_reason": None,
            }
        fallback_reason = "arterial_geometry_not_registered"
    else:
        fallback_reason = "arterial_phase_unavailable"
    return {
        "source_path": reference_path,
        "source_role": "native_representative_reference",
        "selected_phase": "reference",
        "fallback_used": True,
        "fallback_reason": fallback_reason,
    }


def _publish_mask(
    source_mask: Path, destination: Path, reference: Path, *, contracted: bool = True
) -> None:
    if contracted:
        assert_experimental_output(destination, destination.parent)
    image = sitk.ReadImage(str(source_mask))
    reference_image = sitk.ReadImage(str(reference))
    if not same_geometry(image, reference_image):
        image = sitk.Resample(
            image,
            reference_image,
            sitk.Transform(),
            sitk.sitkNearestNeighbor,
            0,
            sitk.sitkUInt8,
        )
    temporary = destination.with_name(f".{destination.stem}.{uuid.uuid4().hex[:8]}.tmp.nii.gz")
    try:
        sitk.WriteImage(sitk.Cast(image > 0, sitk.sitkUInt8), str(temporary), useCompression=True)
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)


def run_phase_aware_shadow(
    *,
    case_root: Path | str,
    phase_paths: Mapping[str, Path | str],
    reference_volume: Path | str,
    mrsegmentator_exe: Path | str,
    timeout_seconds: int = 180,
    backend_version: str = "2.0.0",
    segmenter: Callable[..., dict[str, Any]] | None = None,
    adaptive: bool = True,
    secondary_timeout_seconds: int = 55,
) -> dict[str, Any]:
    """Create v2 shadow artifacts without touching production masks or reports."""

    root = Path(case_root).resolve()
    reference = Path(reference_volume).resolve()
    executable = Path(mrsegmentator_exe).resolve()
    if not root.is_dir() or not executable.is_file():
        raise PipelineError("Case root ou executavel MRSegmentator ausente.")
    if timeout_seconds < 30 or timeout_seconds > 300:
        raise PipelineError("Timeout do shadow mode fora do intervalo seguro.")
    paths = experimental_paths(root)
    existing = [path.name for path in paths.__dict__.values() if path.exists()]
    if existing:
        raise PipelineError(f"Artefatos shadow ja existem; sobrescrita recusada: {existing}")

    selection = select_phase_aware_source(
        phase_paths=phase_paths,
        reference_volume=reference,
    )
    input_manifest = build_native_input_manifest(
        source_volume=selection["source_path"],
        reference_volume=reference,
        source_role=selection["source_role"],
    )
    input_manifest["selection"] = {
        "policy": "arterial_registered_else_native_reference_v1",
        "selected_phase": selection["selected_phase"],
        "fallback_used": selection["fallback_used"],
        "fallback_reason": selection["fallback_reason"],
    }
    atomic_write_experimental_json(paths.input_manifest, input_manifest, case_root=root)

    if segmenter is None:
        from .benchmark.mrsegmentator_chaos_runner import run_case as segmenter

    staging = root / f".segmentation_shadow_v2.{uuid.uuid4().hex[:8]}"
    try:
        result = segmenter(
            source=Path(selection["source_path"]),
            case_id="visualization-shadow-primary",
            mrsegmentator_exe=executable,
            staging=staging,
            timeout_seconds=timeout_seconds,
        )
        source_mask = staging / "masks" / "visualization-shadow-primary.nii.gz"
        legacy_source_mask = staging / "masks" / "visualization-shadow.nii.gz"
        if not source_mask.is_file() and legacy_source_mask.is_file():
            source_mask = legacy_source_mask
        if not source_mask.is_file():
            raise PipelineError("Segmentador shadow terminou sem mascara candidata.")
        primary_mask_path = staging / "primary_on_reference.nii.gz"
        _publish_mask(source_mask, primary_mask_path, reference, contracted=False)
        primary_array, reference_image = _mask_array_on_reference(primary_mask_path, reference)
        primary_metrics = mask_quality_metrics(primary_array, reference_image)
        if not primary_array.any():
            raise PipelineError("Segmentador shadow produziu mascara vazia.")

        baseline_metrics: dict[str, Any] | None = None
        baseline_path = root / "mask_organ.nii.gz"
        if baseline_path.is_file():
            baseline_array, _ = _mask_array_on_reference(baseline_path, reference)
            baseline_metrics = mask_quality_metrics(baseline_array, reference_image)
            baseline_metrics["agreement_with_primary"] = mask_agreement(
                primary_array, baseline_array
            )

        trigger, trigger_reasons = should_run_secondary(
            primary_metrics, baseline_metrics,
            fallback_used=bool(selection["fallback_used"]),
        )
        final_array = primary_array
        adaptive_receipt: dict[str, Any] = {
            "policy": "quality_triggered_secondary_protected_fusion_v1",
            "triggered": bool(adaptive and trigger),
            "trigger_reasons": trigger_reasons,
            "primary": primary_metrics,
            "baseline": baseline_metrics,
            "secondary": None,
            "agreement": None,
            "fusion": {"accepted": False, "reason": "not_triggered"},
            "selected_output": "primary",
        }
        secondary_elapsed = 0.0
        secondary = select_secondary_source(
            phase_paths=phase_paths,
            reference_volume=reference,
            primary_source=selection["source_path"],
        ) if adaptive and trigger else None
        if adaptive and trigger and secondary is None:
            adaptive_receipt["fusion"] = {
                "accepted": False, "reason": "secondary_phase_unavailable",
            }
        elif secondary is not None:
            secondary_staging = staging / "secondary"
            try:
                secondary_result = segmenter(
                    source=Path(secondary["source_path"]),
                    case_id="visualization-shadow-secondary",
                    mrsegmentator_exe=executable,
                    staging=secondary_staging,
                    timeout_seconds=min(int(secondary_timeout_seconds), int(timeout_seconds)),
                )
                secondary_source_mask = (
                    secondary_staging / "masks" / "visualization-shadow-secondary.nii.gz"
                )
                if secondary_source_mask.is_file():
                    secondary_mask_path = staging / "secondary_on_reference.nii.gz"
                    _publish_mask(
                        secondary_source_mask, secondary_mask_path, reference,
                        contracted=False,
                    )
                    secondary_array, _ = _mask_array_on_reference(secondary_mask_path, reference)
                    secondary_metrics = mask_quality_metrics(secondary_array, reference_image)
                    adaptive_receipt["secondary"] = {
                        **secondary_metrics,
                        "selected_phase": secondary["selected_phase"],
                    }
                    adaptive_receipt["agreement"] = mask_agreement(
                        primary_array, secondary_array
                    )
                    final_array, fusion = protected_adaptive_fusion(
                        primary_array, secondary_array,
                        spacing_xyz=tuple(float(value) for value in reference_image.GetSpacing()),
                    )
                    adaptive_receipt["fusion"] = fusion
                    if fusion.get("accepted"):
                        adaptive_receipt["selected_output"] = "protected_fusion"
                else:
                    adaptive_receipt["fusion"] = {
                        "accepted": False, "reason": "secondary_mask_missing",
                    }
                secondary_elapsed = float(secondary_result.get("elapsed_seconds", 0.0))
            except Exception as exc:  # noqa: BLE001
                # Secondary confirmation is optional. A technical failure must
                # never discard a valid primary mask or fail the exam.
                adaptive_receipt["fusion"] = {
                    "accepted": False,
                    "reason": "secondary_technical_failure_primary_preserved",
                    "failure_type": type(exc).__name__,
                }

        final_image = sitk.GetImageFromArray(final_array.astype(np.uint8))
        final_image.CopyInformation(reference_image)
        final_staging = staging / "final_on_reference.nii.gz"
        sitk.WriteImage(final_image, str(final_staging), useCompression=True)
        _publish_mask(final_staging, paths.visualization_mask, reference)
        quality = build_quality_manifest(
            backend_id="mrsegmentator",
            backend_version=backend_version,
            input_manifest=input_manifest,
            visualization_mask=paths.visualization_mask,
            reference_volume=reference,
            elapsed_seconds=float(result.get("elapsed_seconds", 0.0)) + secondary_elapsed,
            fallback_used=bool(selection["fallback_used"]),
        )
        quality["selection"] = input_manifest["selection"]
        quality["adaptive"] = adaptive_receipt
        if adaptive_receipt.get("triggered") and adaptive_receipt.get("selected_output") == "primary":
            quality["status"] = "APPROVED_WITH_WARNING"
        quality["ground_truth_read"] = False
        quality["lesion_masks_read"] = 0
        quality["production_files_written"] = False
        atomic_write_experimental_json(paths.quality_manifest, quality, case_root=root)
        return quality
    except Exception:
        # A partial candidate must never be mistaken for an approved shadow result.
        paths.visualization_mask.unlink(missing_ok=True)
        paths.quality_manifest.unlink(missing_ok=True)
        raise
    finally:
        shutil.rmtree(staging, ignore_errors=True)


__all__ = [
    "ARTERIAL_KEYS",
    "SECONDARY_KEYS",
    "mask_quality_metrics",
    "mask_agreement",
    "protected_adaptive_fusion",
    "select_secondary_source",
    "should_run_secondary",
    "select_phase_aware_source",
    "run_phase_aware_shadow",
]
