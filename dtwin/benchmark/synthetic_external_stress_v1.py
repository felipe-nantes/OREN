"""Build a traceable synthetic multiphase liver MRI stress cohort.

This module is deliberately isolated from the frozen clinical benchmark.  It
uses NIH MRISegmenter volumes as third-institution backgrounds and transfers
class-specific enhancement signatures measured from public LLD-MMRI lesion
masks.  The result is suitable for pipeline and robustness testing only; it is
not an external clinical validation cohort and cannot estimate specificity.
"""
from __future__ import annotations

import hashlib
import json
import math
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable

import numpy as np
import SimpleITK as sitk
from scipy.ndimage import (
    binary_dilation,
    distance_transform_edt,
    gaussian_filter,
    label as connected_components,
)

from dtwin.core import PipelineError, sha256_of


SCHEMA = "argos-synthetic-external-stress-v1"
ALGORITHM_ID = "highpass-parenchyma-v2_centroid-motion-implant-v1"
REPO_ID = "wanglab/LLD-MMRI-MedSAM2"
REPO_REVISION = "b7e8da56b267587689d8440e8298205f3fc4914e"
PHASES = ("arterial", "venous", "delayed")
NIH_PHASE = {"arterial": "ART", "venous": "VEN", "delayed": "DEL"}
LLD_PHASE = {"arterial": "C+A", "venous": "C+V", "delayed": "C+Delay"}
CLASS_CATEGORY = {"hemangioma": 0, "simple_cyst": 4, "fnh": 5, "hcc": 6}
DEFAULT_TARGETS = {
    "no_focal_lesion": 100,
    "fnh": 50,
    "hcc": 60,
    "simple_cyst": 60,
    "hemangioma": 60,
}


@dataclass(frozen=True)
class ImageGeometry:
    size: tuple[int, ...]
    spacing: tuple[float, ...]
    origin: tuple[float, ...]
    direction: tuple[float, ...]


def _canonical_sha(value: object) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _geometry(image: sitk.Image) -> ImageGeometry:
    return ImageGeometry(
        size=tuple(image.GetSize()),
        spacing=tuple(image.GetSpacing()),
        origin=tuple(image.GetOrigin()),
        direction=tuple(image.GetDirection()),
    )


def _geometry_close(left: sitk.Image, right: sitk.Image, atol: float = 1e-4) -> bool:
    if left.GetSize() != right.GetSize():
        return False
    return all(
        np.allclose(a, b, rtol=0.0, atol=atol)
        for a, b in (
            (left.GetSpacing(), right.GetSpacing()),
            (left.GetOrigin(), right.GetOrigin()),
            (left.GetDirection(), right.GetDirection()),
        )
    )


def load_lld_class_cases(annotation_path: Path) -> dict[str, list[str]]:
    """Return mutually exclusive LLD case ids for the four in-protocol classes."""
    payload = json.loads(annotation_path.read_text(encoding="utf-8"))
    annotation = payload.get("Annotation_info")
    if not isinstance(annotation, dict):
        raise PipelineError("LLD annotation is missing Annotation_info")
    by_category: dict[int, list[str]] = {value: [] for value in CLASS_CATEGORY.values()}
    for case_id, series in annotation.items():
        categories: set[int] = set()
        for item in series:
            lesions = item.get("annotation", {}).get("lesion", {})
            categories.update(int(value["category"]) for value in lesions.values())
        if len(categories) != 1:
            raise PipelineError(f"LLD case {case_id} is not single-class: {sorted(categories)}")
        category = next(iter(categories))
        if category in by_category:
            by_category[category].append(str(case_id))
    result = {
        name: sorted(by_category[category])
        for name, category in CLASS_CATEGORY.items()
    }
    expected = {"hemangioma": 79, "simple_cyst": 53, "fnh": 46, "hcc": 157}
    counts = {name: len(cases) for name, cases in result.items()}
    if counts != expected:
        raise PipelineError(f"unexpected LLD class counts: {counts}; expected {expected}")
    return result


def list_nih_cases(nih_root: Path) -> list[str]:
    """List complete NIH background cases across the official train/test folders."""
    cases: list[str] = []
    for split, prefix in (("ImageTr", "train"), ("ImageTs", "test")):
        folder = nih_root / split
        for pre in sorted(folder.glob(f"{prefix}_*_PRE_0000.nii.gz")):
            case_id = pre.name.removesuffix("_PRE_0000.nii.gz")
            expected = [folder / f"{case_id}_{NIH_PHASE[phase]}_0000.nii.gz" for phase in PHASES]
            label_folder = nih_root / ("labelsTr" if prefix == "train" else "labelsTs")
            expected += [label_folder / f"{case_id}_{NIH_PHASE[phase]}.nii.gz" for phase in PHASES]
            if not all(path.is_file() for path in expected):
                raise PipelineError(f"NIH case {case_id} is missing a required phase or mask")
            cases.append(case_id)
    if len(cases) != 195:
        raise PipelineError(f"expected 195 complete NIH cases, found {len(cases)}")
    return cases


def _cycled_permutation(values: list[str], count: int, rng: np.random.Generator) -> list[str]:
    if not values:
        raise PipelineError("cannot sample from an empty source list")
    selected: list[str] = []
    while len(selected) < count:
        selected.extend(str(value) for value in rng.permutation(values))
    return selected[:count]


def build_plan(
    *,
    nih_cases: list[str],
    lld_cases: dict[str, list[str]],
    seed: int = 20260731,
    targets: dict[str, int] | None = None,
) -> list[dict[str, object]]:
    """Create a deterministic plan while retaining background/donor dependency ids."""
    targets = dict(DEFAULT_TARGETS if targets is None else targets)
    if set(targets) != set(DEFAULT_TARGETS) or any(value < 0 for value in targets.values()):
        raise PipelineError(f"invalid synthetic target map: {targets}")
    rng = np.random.default_rng(seed)
    labels = [label for label, count in targets.items() for _ in range(count)]
    labels = [str(value) for value in rng.permutation(labels)]
    backgrounds = _cycled_permutation(nih_cases, len(labels), rng)
    donor_queues = {
        label: _cycled_permutation(lld_cases[label], targets[label], rng)
        for label in CLASS_CATEGORY
    }
    donor_index = Counter()
    background_use = Counter()
    plan: list[dict[str, object]] = []
    for index, (label_name, background) in enumerate(zip(labels, backgrounds), start=1):
        source_donor = None
        category = None
        if label_name != "no_focal_lesion":
            source_donor = donor_queues[label_name][donor_index[label_name]]
            donor_index[label_name] += 1
            category = CLASS_CATEGORY[label_name]
        background_use[background] += 1
        row = {
            "case_id": f"anon-synth-ext-v1-{index:04d}",
            "label": label_name,
            "background_case_id": background,
            "background_dependency_group": f"nih:{background}",
            "background_variant": background_use[background],
            "donor_case_id": source_donor,
            "donor_category": category,
            "donor_dependency_group": None if source_donor is None else f"lld:{source_donor}",
            "seed": int(seed + index * 7919),
        }
        row["plan_signature"] = _canonical_sha(row)
        plan.append(row)
    return plan


def required_mask_files(plan: Iterable[dict[str, object]]) -> list[str]:
    files: set[str] = set()
    for row in plan:
        donor = row.get("donor_case_id")
        category = row.get("donor_category")
        if donor is None:
            continue
        for phase in PHASES:
            files.add(f"labels/{donor}_{category}_{LLD_PHASE[phase]}.nii.gz")
    return sorted(files)


def download_required_masks(
    *,
    plan: Iterable[dict[str, object]],
    lld_root: Path,
    downloader: Callable[..., str],
    workers: int = 8,
) -> list[Path]:
    """Download only public lesion masks needed by a frozen synthetic plan."""
    if not isinstance(workers, int) or isinstance(workers, bool) or not 1 <= workers <= 16:
        raise PipelineError("workers must be an integer in [1, 16]")
    filenames = required_mask_files(plan)

    def one(filename: str) -> Path:
        result = Path(
            downloader(
                repo_id=REPO_ID,
                repo_type="dataset",
                revision=REPO_REVISION,
                filename=filename,
                local_dir=str(lld_root),
            )
        )
        if not result.is_file() or result.stat().st_size <= 0:
            raise PipelineError(f"mask download failed: {filename}")
        return result

    with ThreadPoolExecutor(max_workers=workers) as executor:
        paths = list(executor.map(one, filenames))
    return paths


def _largest_component(mask: np.ndarray) -> np.ndarray:
    components, count = connected_components(mask.astype(bool))
    if count == 0:
        raise PipelineError("empty lesion mask")
    sizes = np.bincount(components.ravel())
    sizes[0] = 0
    return components == int(np.argmax(sizes))


def _location_scale(values: np.ndarray, *, minimum_voxels: int = 32) -> tuple[float, float]:
    values = np.asarray(values, dtype=np.float32)
    values = values[np.isfinite(values)]
    if values.size < minimum_voxels:
        raise PipelineError("too few finite voxels for robust intensity statistics")
    location = float(np.median(values))
    scale = float(1.4826 * np.median(np.abs(values - location)))
    if not math.isfinite(scale) or scale < 1e-3:
        scale = float(np.std(values))
    return location, max(scale, 1.0)


def _lld_paths(lld_root: Path, donor: str, category: int, phase: str) -> tuple[Path, Path]:
    token = LLD_PHASE[phase]
    image = lld_root / "images" / f"{donor}_{category}_{token}_0000.nii.gz"
    mask = lld_root / "labels" / f"{donor}_{category}_{token}.nii.gz"
    if not image.is_file() or not mask.is_file():
        raise PipelineError(f"missing LLD donor image/mask for {donor} {token}")
    return image, mask


def measure_donor_signature(lld_root: Path, donor: str, category: int) -> dict[str, object]:
    """Measure physical size and phase-specific lesion-to-liver contrast."""
    result: dict[str, object] = {"donor_case_id": donor, "category": category, "phases": {}}
    arterial_component: np.ndarray | None = None
    arterial_spacing: tuple[float, ...] | None = None
    for phase in PHASES:
        image_path, mask_path = _lld_paths(lld_root, donor, category, phase)
        image = sitk.ReadImage(str(image_path))
        mask_image = sitk.ReadImage(str(mask_path))
        if not _geometry_close(image, mask_image):
            raise PipelineError(f"LLD donor geometry mismatch: {donor} {phase}")
        array = sitk.GetArrayFromImage(image).astype(np.float32)
        component = _largest_component(sitk.GetArrayFromImage(mask_image) > 0)
        outer = binary_dilation(component, iterations=10)
        inner = binary_dilation(component, iterations=2)
        ring = outer & ~inner
        lesion_location, lesion_scale = _location_scale(array[component], minimum_voxels=16)
        ring_location, ring_scale = _location_scale(array[ring])
        result["phases"][phase] = {
            "contrast_z": float(np.clip((lesion_location - ring_location) / ring_scale, -6, 6)),
            "texture_ratio": float(np.clip(lesion_scale / ring_scale, 0.15, 4.0)),
        }
        if phase == "arterial":
            arterial_component = component
            arterial_spacing = tuple(reversed(image.GetSpacing()))
    assert arterial_component is not None and arterial_spacing is not None
    indices = np.argwhere(arterial_component)
    extent_voxels = indices.max(axis=0) - indices.min(axis=0) + 1
    extent_mm = extent_voxels * np.asarray(arterial_spacing)
    voxel_volume = float(np.prod(arterial_spacing))
    result["largest_component_voxels"] = int(arterial_component.sum())
    result["volume_ml"] = float(arterial_component.sum() * voxel_volume / 1000.0)
    result["extent_mm_zyx"] = [float(value) for value in extent_mm]
    result["signature"] = _canonical_sha(result)
    return result


def build_donor_library(plan: Iterable[dict[str, object]], lld_root: Path) -> dict[str, object]:
    donors = sorted(
        {
            (str(row["donor_case_id"]), int(row["donor_category"]))
            for row in plan
            if row.get("donor_case_id") is not None
        }
    )
    entries = {
        donor: measure_donor_signature(lld_root, donor, category)
        for donor, category in donors
    }
    payload: dict[str, object] = {
        "schema": f"{SCHEMA}-donor-library",
        "source_repo_id": REPO_ID,
        "source_revision": REPO_REVISION,
        "donor_count": len(entries),
        "donors": entries,
    }
    payload["library_signature"] = _canonical_sha(payload)
    return payload


def _liver_bbox(mask: np.ndarray, margin: int = 4) -> tuple[slice, slice, slice]:
    points = np.argwhere(mask)
    if points.size == 0:
        raise PipelineError("NIH liver mask is empty")
    low = np.maximum(points.min(axis=0) - margin, 0)
    high = np.minimum(points.max(axis=0) + margin + 1, mask.shape)
    return tuple(slice(int(a), int(b)) for a, b in zip(low, high))  # type: ignore[return-value]


def synthesize_lesion_free_liver(
    phase_arrays: dict[str, np.ndarray],
    liver_masks: dict[str, np.ndarray] | np.ndarray,
    *,
    seed: int,
) -> dict[str, np.ndarray]:
    """Replace liver parenchyma with correlated nonfocal texture.

    This guarantees absence only in the synthetic construction, not by clinical
    review.  Outside-liver voxels and separately labelled vessels are retained.
    """
    rng = np.random.default_rng(seed)
    if isinstance(liver_masks, np.ndarray):
        masks = {phase: liver_masks for phase in PHASES}
    else:
        masks = liver_masks
    reference_mask = masks["arterial"]
    common = gaussian_filter(
        rng.normal(size=reference_mask.shape).astype(np.float32), (1.2, 3.0, 3.0)
    )
    bias = gaussian_filter(
        rng.normal(size=reference_mask.shape).astype(np.float32), (3.0, 10.0, 10.0)
    )
    output: dict[str, np.ndarray] = {}
    for phase in PHASES:
        phase_mask = masks[phase]
        bbox = _liver_bbox(phase_mask)
        local_mask = phase_mask[bbox]
        original = phase_arrays[phase]
        work = original.astype(np.float32, copy=True)
        local = work[bbox]
        local_common = common[bbox]
        local_bias = bias[bbox]
        local_common = (local_common - local_common[local_mask].mean()) / max(
            local_common[local_mask].std(), 1e-3
        )
        local_bias = (local_bias - local_bias[local_mask].mean()) / max(
            local_bias[local_mask].std(), 1e-3
        )
        distance = distance_transform_edt(local_mask)
        blend = np.clip(distance / 3.0, 0.0, 1.0).astype(np.float32)
        location, scale = _location_scale(local[local_mask])
        phase_noise = gaussian_filter(
            rng.normal(size=local_mask.shape).astype(np.float32), (0.8, 1.8, 1.8)
        )
        phase_noise = (phase_noise - phase_noise[local_mask].mean()) / max(
            phase_noise[local_mask].std(), 1e-3
        )
        # Retain scanner-scale high-frequency texture while discarding the
        # low-frequency focal signal that could encode an unknown real lesion.
        # The added fields are intentionally low-amplitude to avoid the coarse
        # speckle produced by a pure random-field replacement.
        high_frequency = local - gaussian_filter(local, (0.7, 2.0, 2.0))
        high_frequency = np.clip(high_frequency, -2.0 * scale, 2.0 * scale)
        texture = (
            location
            + 0.16 * scale * local_common
            + 0.08 * scale * local_bias
            + 0.06 * scale * phase_noise
            + 0.45 * high_frequency
        )
        local[local_mask] = (
            blend[local_mask] * texture[local_mask]
            + (1.0 - blend[local_mask]) * local[local_mask]
        )
        output[phase] = work
    return output


def _ellipsoid_mask(
    shape: tuple[int, int, int],
    spacing_zyx: np.ndarray,
    extent_mm_zyx: np.ndarray,
    rng: np.random.Generator,
) -> np.ndarray:
    radii_mm = np.clip(extent_mm_zyx * rng.uniform(0.42, 0.58, size=3), 3.0, 32.0)
    radii_vox = np.maximum(radii_mm / spacing_zyx, 1.5)
    liver_placeholder = np.zeros(shape, dtype=bool)
    # The actual placement is performed by implant_lesion, where the liver EDT is available.
    center = np.asarray(shape, dtype=float) / 2.0
    low = np.maximum(np.floor(center - radii_vox - 3).astype(int), 0)
    high = np.minimum(np.ceil(center + radii_vox + 4).astype(int), shape)
    slices = tuple(slice(int(a), int(b)) for a, b in zip(low, high))
    grid = np.ogrid[tuple(slice(0, b - a) for a, b in zip(low, high))]
    normalized = sum(
        ((axis - (center[dim] - low[dim])) / radii_vox[dim]) ** 2
        for dim, axis in enumerate(grid)
    )
    perturbation = gaussian_filter(rng.normal(size=normalized.shape).astype(np.float32), 1.2)
    perturbation /= max(float(perturbation.std()), 1e-3)
    liver_placeholder[slices] = normalized + 0.18 * perturbation <= 1.0
    return _largest_component(liver_placeholder)


def implant_lesion(
    phase_arrays: dict[str, np.ndarray],
    liver_masks: dict[str, np.ndarray] | np.ndarray,
    spacing_xyz: tuple[float, float, float],
    donor_signature: dict[str, object],
    *,
    seed: int,
) -> tuple[dict[str, np.ndarray], dict[str, np.ndarray]]:
    rng = np.random.default_rng(seed)
    if isinstance(liver_masks, np.ndarray):
        masks = {phase: liver_masks for phase in PHASES}
    else:
        masks = liver_masks
    arterial_liver = masks["arterial"]
    spacing_zyx = np.asarray(tuple(reversed(spacing_xyz)), dtype=float)
    extent = np.asarray(donor_signature["extent_mm_zyx"], dtype=float)
    template = _ellipsoid_mask(arterial_liver.shape, spacing_zyx, extent, rng)
    template_points = np.argwhere(template)
    template_center = np.round(template_points.mean(axis=0)).astype(int)
    template_radius_mm = float(np.max(extent) * 0.58)
    liver_distance = distance_transform_edt(arterial_liver, sampling=spacing_zyx)
    candidates = np.argwhere(liver_distance >= min(template_radius_mm, 24.0))
    if candidates.size == 0:
        threshold = float(np.percentile(liver_distance[arterial_liver], 92))
        candidates = np.argwhere(liver_distance >= threshold)
    target_center = candidates[int(rng.integers(len(candidates)))]
    shift = target_center - template_center
    target_mask = np.zeros_like(arterial_liver, dtype=bool)
    shifted = template_points + shift
    valid = np.all((shifted >= 0) & (shifted < np.asarray(arterial_liver.shape)), axis=1)
    shifted = shifted[valid]
    target_mask[tuple(shifted.T)] = True
    target_mask &= arterial_liver
    target_mask = _largest_component(target_mask)
    if target_mask.sum() < 8:
        raise PipelineError("synthetic target lesion became too small")
    arterial_center = np.argwhere(arterial_liver).mean(axis=0)
    target_points = np.argwhere(target_mask)
    result: dict[str, np.ndarray] = {}
    target_masks: dict[str, np.ndarray] = {}
    phase_stats = donor_signature["phases"]
    for phase in PHASES:
        phase_liver = masks[phase]
        center_shift = np.round(np.argwhere(phase_liver).mean(axis=0) - arterial_center).astype(int)
        phase_points = target_points + center_shift
        valid = np.all((phase_points >= 0) & (phase_points < np.asarray(phase_liver.shape)), axis=1)
        phase_points = phase_points[valid]
        phase_target = np.zeros_like(phase_liver, dtype=bool)
        phase_target[tuple(phase_points.T)] = True
        phase_target &= phase_liver
        phase_target = _largest_component(phase_target)
        if phase_target.sum() < 8:
            raise PipelineError(f"synthetic target lesion became too small in {phase}")
        target_masks[phase] = phase_target
        outer = binary_dilation(phase_target, iterations=8) & phase_liver
        ring = outer & ~binary_dilation(phase_target, iterations=2)
        distance = distance_transform_edt(phase_target)
        alpha = np.clip(distance / 2.0, 0.25, 1.0).astype(np.float32)
        common = gaussian_filter(
            rng.normal(size=phase_target.shape).astype(np.float32), (0.6, 1.0, 1.0)
        )
        common = (common - common[phase_target].mean()) / max(
            common[phase_target].std(), 1e-3
        )
        work = phase_arrays[phase].astype(np.float32, copy=True)
        location, scale = _location_scale(work[ring])
        stats = phase_stats[phase]
        center = location + float(stats["contrast_z"]) * scale
        texture_scale = scale * float(stats["texture_ratio"])
        phase_noise = gaussian_filter(
            rng.normal(size=phase_target.shape).astype(np.float32), (0.35, 0.65, 0.65)
        )
        phase_noise = (phase_noise - phase_noise[phase_target].mean()) / max(
            phase_noise[phase_target].std(), 1e-3
        )
        lesion = center + texture_scale * (0.72 * common + 0.28 * phase_noise)
        work[phase_target] = (
            alpha[phase_target] * lesion[phase_target]
            + (1.0 - alpha[phase_target]) * work[phase_target]
        )
        result[phase] = work
    return result, target_masks


def _nih_paths(nih_root: Path, case_id: str, phase: str) -> tuple[Path, Path]:
    train = case_id.startswith("train")
    image_dir = "ImageTr" if train else "ImageTs"
    label_dir = "labelsTr" if train else "labelsTs"
    token = NIH_PHASE[phase]
    return (
        nih_root / image_dir / f"{case_id}_{token}_0000.nii.gz",
        nih_root / label_dir / f"{case_id}_{token}.nii.gz",
    )


def generate_case(
    *,
    row: dict[str, object],
    nih_root: Path,
    donor_library: dict[str, object],
    output_root: Path,
) -> dict[str, object]:
    case_dir = output_root / "cases" / str(row["case_id"])
    if case_dir.exists() and any(case_dir.iterdir()):
        raise PipelineError(f"refusing to overwrite existing synthetic case: {case_dir}")
    case_dir.mkdir(parents=True, exist_ok=True)
    images: dict[str, sitk.Image] = {}
    arrays: dict[str, np.ndarray] = {}
    liver_masks: dict[str, np.ndarray] = {}
    for phase in PHASES:
        image_path, label_path = _nih_paths(nih_root, str(row["background_case_id"]), phase)
        image = sitk.ReadImage(str(image_path))
        label_image = sitk.ReadImage(str(label_path))
        if not _geometry_close(image, label_image):
            raise PipelineError(f"NIH geometry mismatch for {row['background_case_id']} {phase}")
        images[phase] = image
        arrays[phase] = sitk.GetArrayFromImage(image)
        liver_masks[phase] = sitk.GetArrayFromImage(label_image) == 5
    synthetic = synthesize_lesion_free_liver(arrays, liver_masks, seed=int(row["seed"]))
    lesion_masks = {phase: np.zeros_like(liver_masks[phase], dtype=bool) for phase in PHASES}
    if row["donor_case_id"] is not None:
        signature = donor_library["donors"][str(row["donor_case_id"])]
        synthetic, lesion_masks = implant_lesion(
            synthetic,
            liver_masks,
            images["arterial"].GetSpacing(),
            signature,
            seed=int(row["seed"]) + 1,
        )
    phase_records: dict[str, object] = {}
    for phase in PHASES:
        source_array = arrays[phase]
        clipped = np.clip(synthetic[phase], np.min(source_array), np.max(source_array))
        final_array = np.rint(clipped).astype(source_array.dtype)
        output_image = sitk.GetImageFromArray(final_array)
        output_image.CopyInformation(images[phase])
        destination = case_dir / f"{phase}.nii.gz"
        sitk.WriteImage(output_image, str(destination), True)
        phase_records[phase] = {
            "relative_path": destination.relative_to(output_root).as_posix(),
            "sha256": sha256_of(destination),
        }
    liver_records: dict[str, object] = {}
    lesion_records: dict[str, object] = {}
    for phase in PHASES:
        liver_image = sitk.GetImageFromArray(liver_masks[phase].astype(np.uint8))
        liver_image.CopyInformation(images[phase])
        liver_path = case_dir / f"liver_mask_{phase}.nii.gz"
        sitk.WriteImage(liver_image, str(liver_path), True)
        lesion_image = sitk.GetImageFromArray(lesion_masks[phase].astype(np.uint8))
        lesion_image.CopyInformation(images[phase])
        lesion_path = case_dir / f"lesion_mask_{phase}.nii.gz"
        sitk.WriteImage(lesion_image, str(lesion_path), True)
        liver_records[phase] = {
            "relative_path": liver_path.relative_to(output_root).as_posix(),
            "sha256": sha256_of(liver_path),
            "voxels": int(liver_masks[phase].sum()),
        }
        lesion_records[phase] = {
            "relative_path": lesion_path.relative_to(output_root).as_posix(),
            "sha256": sha256_of(lesion_path),
            "voxels": int(lesion_masks[phase].sum()),
        }
    record = dict(row)
    record.update(
        {
            "schema": f"{SCHEMA}-case",
            "phases": phase_records,
            "liver_masks": liver_records,
            "lesion_masks": lesion_records,
            "synthetic": True,
            "synthesis_algorithm": ALGORITHM_ID,
            "clinical_ground_truth": False,
        }
    )
    record["record_signature"] = _canonical_sha(record)
    (case_dir / "case_manifest.json").write_text(
        json.dumps(record, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return record


def write_cohort_manifest(
    *, output_root: Path, plan: list[dict[str, object]], donor_library: dict[str, object]
) -> dict[str, object]:
    records = [
        json.loads((output_root / "cases" / str(row["case_id"]) / "case_manifest.json").read_text())
        for row in plan
    ]
    labels = Counter(str(record["label"]) for record in records)
    unique_backgrounds = {str(record["background_case_id"]) for record in records}
    unique_donors = {
        str(record["donor_case_id"])
        for record in records
        if record["donor_case_id"] is not None
    }
    cases_path = output_root / "cases.jsonl"
    cases_path.write_text(
        "".join(json.dumps(record, sort_keys=True, ensure_ascii=False) + "\n" for record in records),
        encoding="utf-8",
    )
    payload: dict[str, object] = {
        "schema": SCHEMA,
        "status": "synthetic_technical_stress_only",
        "case_count": len(records),
        "label_counts": dict(sorted(labels.items())),
        "phases_required": list(PHASES),
        "all_phases_materialized": True,
        "background_source": "NIH Clinical Center MRISegmenter",
        "unique_background_patient_count": len(unique_backgrounds),
        "lesion_signature_source": "LLD-MMRI-MedSAM2",
        "unique_lesion_donor_count": len(unique_donors),
        "donor_library_signature": donor_library["library_signature"],
        "synthesis_algorithm": ALGORITHM_ID,
        "statistically_independent_case_count": None,
        "specificity_estimation_allowed": False,
        "external_clinical_validation_allowed": False,
        "publication_validation_claim_allowed": False,
        "clinical_use_allowed": False,
        "reason": (
            "Output cases reuse patient anatomy and algorithmically erase or implant lesions; "
            "labels are construction labels, not radiologist-confirmed diagnoses."
        ),
        "cases_jsonl": "cases.jsonl",
        "cases_jsonl_sha256": sha256_of(cases_path),
    }
    payload["cohort_signature"] = _canonical_sha(payload)
    (output_root / "cohort_manifest.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return payload


def verify_cohort(output_root: Path) -> dict[str, object]:
    """Fail closed on missing, tampered, geometrically inconsistent synthetic data."""
    manifest_path = output_root / "cohort_manifest.json"
    cases_path = output_root / "cases.jsonl"
    if not manifest_path.is_file() or not cases_path.is_file():
        raise PipelineError("synthetic cohort manifest or cases.jsonl is missing")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    records = [
        json.loads(line)
        for line in cases_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if manifest.get("schema") != SCHEMA or manifest.get("status") != "synthetic_technical_stress_only":
        raise PipelineError("unexpected synthetic cohort schema or status")
    if manifest.get("cases_jsonl_sha256") != sha256_of(cases_path):
        raise PipelineError("cases.jsonl hash does not match the cohort manifest")
    if manifest.get("case_count") != len(records):
        raise PipelineError("synthetic case count does not match the cohort manifest")
    if manifest.get("specificity_estimation_allowed") is not False:
        raise PipelineError("synthetic cohort must explicitly forbid specificity estimation")
    if manifest.get("external_clinical_validation_allowed") is not False:
        raise PipelineError("synthetic cohort must explicitly forbid external validation claims")
    labels = Counter(str(record["label"]) for record in records)
    if dict(sorted(labels.items())) != manifest.get("label_counts"):
        raise PipelineError("synthetic label counts do not match the cohort manifest")
    for record in records:
        phase_geometries: list[ImageGeometry] = []
        for phase in PHASES:
            phase_record = record["phases"][phase]
            image_path = output_root / phase_record["relative_path"]
            if not image_path.is_file() or sha256_of(image_path) != phase_record["sha256"]:
                raise PipelineError(f"missing or tampered phase: {record['case_id']} {phase}")
            image = sitk.ReadImage(str(image_path))
            phase_geometries.append(_geometry(image))
            liver_record = record["liver_masks"][phase]
            lesion_record = record["lesion_masks"][phase]
            liver_path = output_root / liver_record["relative_path"]
            lesion_path = output_root / lesion_record["relative_path"]
            for path, expected in (
                (liver_path, liver_record["sha256"]),
                (lesion_path, lesion_record["sha256"]),
            ):
                if not path.is_file() or sha256_of(path) != expected:
                    raise PipelineError(f"missing or tampered mask: {record['case_id']} {phase}")
            liver_image = sitk.ReadImage(str(liver_path))
            lesion_image = sitk.ReadImage(str(lesion_path))
            if not _geometry_close(image, liver_image) or not _geometry_close(image, lesion_image):
                raise PipelineError(f"output geometry mismatch: {record['case_id']} {phase}")
            liver = sitk.GetArrayFromImage(liver_image) > 0
            lesion = sitk.GetArrayFromImage(lesion_image) > 0
            if np.any(lesion & ~liver):
                raise PipelineError(f"lesion outside liver: {record['case_id']} {phase}")
            expected_positive = record["label"] != "no_focal_lesion"
            if bool(lesion.any()) != expected_positive:
                raise PipelineError(f"lesion-mask polarity mismatch: {record['case_id']} {phase}")
        if len(set(phase_geometries)) != 1:
            raise PipelineError(f"phase grids differ: {record['case_id']}")
    report: dict[str, object] = {
        "schema": f"{SCHEMA}-verification",
        "status": "verified_synthetic_technical_stress_only",
        "case_count": len(records),
        "label_counts": dict(sorted(labels.items())),
        "all_hashes_verified": True,
        "all_phase_grids_identical_per_case": True,
        "all_lesions_inside_phase_specific_liver": True,
        "specificity_estimation_allowed": False,
        "external_clinical_validation_allowed": False,
        "cohort_signature": manifest["cohort_signature"],
    }
    report["verification_signature"] = _canonical_sha(report)
    return report
