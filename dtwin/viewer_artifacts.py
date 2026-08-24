"""Artefatos quantitativos e referências 2D do visualizador 3D.

Este módulo mede a fidelidade da *reconstrução* em relação à máscara que a
originou. As métricas daqui não são Dice nem acurácia de segmentação: sem uma
anotação humana independente, elas não podem dizer se a máscara representa a
anatomia verdadeira do paciente.
"""
from __future__ import annotations

import math
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import numpy as np
import pyvista as pv
import SimpleITK as sitk
from PIL import Image
from scipy import ndimage
from scipy.spatial import cKDTree

from .core import PipelineError, array_from, read_image, sha256_of

REFERENCE_PREFIX = "mri_reference_"
REFERENCE_SIZE_PX = 512


def _as_3d(image: sitk.Image, description: str) -> sitk.Image:
    """Remove apenas dimensões singleton extras; nunca escolhe um volume 4D."""
    if image.GetDimension() == 3:
        return image
    size = list(image.GetSize())
    if image.GetDimension() < 3 or any(int(value) != 1 for value in size[3:]):
        raise PipelineError(
            f"{description} precisa ser 3D (dimensões extras só podem ter tamanho 1)."
        )
    extract_size = size[:3] + [0] * (image.GetDimension() - 3)
    return sitk.Extract(image, extract_size, [0] * image.GetDimension())


def _same_geometry(left: sitk.Image, right: sitk.Image, atol: float = 1e-5) -> bool:
    return (
        left.GetSize() == right.GetSize()
        and np.allclose(left.GetSpacing(), right.GetSpacing(), atol=atol, rtol=0)
        and np.allclose(left.GetOrigin(), right.GetOrigin(), atol=atol, rtol=0)
        and np.allclose(left.GetDirection(), right.GetDirection(), atol=atol, rtol=0)
    )


def _canonical_reference_pair(
    volume_path: Path,
    organ_mask_path: Path,
) -> tuple[sitk.Image, sitk.Image]:
    volume = _as_3d(read_image(volume_path), "Volume de referência")
    mask = _as_3d(read_image(organ_mask_path), "Máscara hepática de referência")
    if not _same_geometry(volume, mask):
        # A imagem exibida é evidência auxiliar. Reamostrar a intensidade para a
        # grade da máscara preserva a geometria da segmentação sem alterar a
        # máscara nem qualquer entrada do classificador.
        volume = sitk.Resample(
            volume,
            mask,
            sitk.Transform(),
            sitk.sitkLinear,
            0.0,
            sitk.sitkFloat32,
        )
    try:
        volume = sitk.DICOMOrient(volume, "LPS")
        mask = sitk.DICOMOrient(mask, "LPS")
    except RuntimeError as exc:
        raise PipelineError(f"Falha ao orientar referências 2D em LPS: {exc}") from exc
    return volume, mask


def _physical_indices(points_lps: np.ndarray, image: sitk.Image) -> np.ndarray:
    """Converte pontos LPS (N,3) para índices contínuos xyz da imagem."""
    origin = np.asarray(image.GetOrigin(), dtype=np.float64)
    spacing = np.asarray(image.GetSpacing(), dtype=np.float64)
    direction = np.asarray(image.GetDirection(), dtype=np.float64).reshape(3, 3)
    return ((points_lps - origin) @ np.linalg.inv(direction).T) / spacing


def compute_mesh_metrics(
    mask_path: Path,
    mesh: pv.PolyData,
    exported_mesh_path: Path,
    *,
    max_volume_error_percent: float = 2.0,
    max_surface_p95_voxels: float = 1.0,
) -> dict[str, Any]:
    """Mede a reconstrução contra sua máscara fonte, nunca contra ground truth."""
    mask_image = _as_3d(read_image(mask_path), "Máscara da estrutura")
    mask_array = array_from(mask_image) > 0
    voxel_count = int(np.count_nonzero(mask_array))
    if voxel_count == 0:
        raise PipelineError(f"Máscara vazia ao medir malha: {mask_path}")
    spacing = np.asarray(mask_image.GetSpacing(), dtype=np.float64)
    source_volume_ml = float(voxel_count * np.prod(spacing) / 1000.0)
    mesh_volume_ml = float(abs(float(mesh.volume)) / 1000.0)
    volume_error_percent = float(
        abs(mesh_volume_ml - source_volume_ml) / source_volume_ml * 100.0
    )

    distance_image = sitk.Abs(
        sitk.SignedMaurerDistanceMap(
            sitk.Cast(mask_image > 0, sitk.sitkUInt8),
            insideIsPositive=False,
            squaredDistance=False,
            useImageSpacing=True,
        )
    )
    distance_array = array_from(distance_image).astype(np.float32, copy=False)
    indices_xyz = _physical_indices(np.asarray(mesh.points, dtype=np.float64), mask_image)
    coordinates_zyx = np.vstack(
        [indices_xyz[:, 2], indices_xyz[:, 1], indices_xyz[:, 0]]
    )
    outside_value = float(np.max(distance_array)) if distance_array.size else 0.0
    deviations = ndimage.map_coordinates(
        distance_array,
        coordinates_zyx,
        order=1,
        mode="constant",
        cval=outside_value,
        prefilter=False,
    )
    deviations = deviations[np.isfinite(deviations)]
    if deviations.size == 0:
        raise PipelineError(f"Não foi possível medir a superfície de {mask_path}.")

    boundary = mesh.extract_feature_edges(
        boundary_edges=True,
        non_manifold_edges=True,
        feature_edges=False,
        manifold_edges=False,
    )
    boundary_edge_count = int(boundary.n_cells)
    bounds = tuple(float(value) for value in mesh.bounds)
    dimensions = [
        bounds[1] - bounds[0],
        bounds[3] - bounds[2],
        bounds[5] - bounds[4],
    ]
    p95 = float(np.percentile(deviations, 95))
    surface_limit_mm = float(max(spacing) * max_surface_p95_voxels)
    warnings: list[str] = []
    if volume_error_percent > max_volume_error_percent:
        warnings.append("mesh_volume_differs_from_source_mask")
    if p95 > surface_limit_mm:
        warnings.append("surface_deviation_above_source_grid_tolerance")
    if boundary_edge_count:
        warnings.append("mesh_not_watertight_or_non_manifold")

    return {
        "scope": "reconstruction_fidelity_to_source_mask",
        "not_segmentation_accuracy": True,
        "source_mask_sha256": sha256_of(mask_path),
        "mesh_sha256": sha256_of(exported_mesh_path),
        "source_voxels": voxel_count,
        "source_mask_volume_ml": round(source_volume_ml, 4),
        "mesh_volume_ml": round(mesh_volume_ml, 4),
        "mesh_volume_error_percent": round(volume_error_percent, 4),
        "surface_area_cm2": round(float(mesh.area) / 100.0, 4),
        "surface_deviation_to_source_mask_mm": {
            "mean": round(float(np.mean(deviations)), 4),
            "p95": round(p95, 4),
            "max": round(float(np.max(deviations)), 4),
            "method": "signed_maurer_distance_sampled_at_mesh_vertices",
        },
        "source_spacing_mm": [round(float(value), 6) for value in spacing],
        "dimensions_mm": [round(float(value), 4) for value in dimensions],
        "vertices": int(mesh.n_points),
        "triangles": int(mesh.n_cells),
        "watertight_and_manifold": boundary_edge_count == 0,
        "boundary_or_non_manifold_edges": boundary_edge_count,
        "quality_thresholds": {
            "max_volume_error_percent": float(max_volume_error_percent),
            "max_surface_p95_mm": round(surface_limit_mm, 4),
            "surface_tolerance_in_largest_source_voxels": float(max_surface_p95_voxels),
        },
        "reconstruction_quality_gate_passed": not warnings,
        "warnings": warnings,
    }


def _window_volume(volume: np.ndarray, mask: np.ndarray) -> tuple[np.ndarray, float, float]:
    finite = np.isfinite(volume)
    sample = volume[finite & mask]
    if sample.size < 32 or np.allclose(sample, sample.flat[0]):
        sample = volume[finite]
    if sample.size == 0:
        raise PipelineError("Volume de RM sem intensidades finitas para referência 2D.")
    low, high = np.percentile(sample, [1.0, 99.0])
    if not math.isfinite(float(low)) or not math.isfinite(float(high)) or high <= low:
        low, high = float(np.min(sample)), float(np.max(sample))
    if high <= low:
        high = low + 1.0
    scaled = np.clip((volume.astype(np.float32) - low) / (high - low), 0.0, 1.0)
    return np.rint(scaled * 255.0).astype(np.uint8), float(low), float(high)


def _render_reference_slice(
    gray: np.ndarray,
    mask: np.ndarray,
    pixel_spacing_uv_mm: tuple[float, float],
    candidate_mask: np.ndarray | None = None,
) -> Image.Image:
    if gray.ndim != 2 or mask.shape != gray.shape:
        raise PipelineError("Plano 2D inválido ao criar referência do visualizador.")
    height, width = gray.shape
    physical_width = max(float(width) * pixel_spacing_uv_mm[0], 1e-6)
    physical_height = max(float(height) * pixel_spacing_uv_mm[1], 1e-6)
    scale = min(
        (REFERENCE_SIZE_PX - 20) / physical_width,
        (REFERENCE_SIZE_PX - 20) / physical_height,
    )
    target = (
        max(1, int(round(physical_width * scale))),
        max(1, int(round(physical_height * scale))),
    )
    gray_image = Image.fromarray(gray, mode="L").resize(target, Image.Resampling.BILINEAR)
    boundary = mask & ~ndimage.binary_erosion(mask, iterations=1, border_value=0)
    boundary_image = Image.fromarray((boundary * 255).astype(np.uint8), mode="L").resize(
        target, Image.Resampling.NEAREST
    )
    rgb = Image.merge("RGB", (gray_image, gray_image, gray_image))
    yellow = Image.new("RGB", target, (255, 211, 49))
    rgb.paste(yellow, mask=boundary_image)
    if candidate_mask is not None:
        if candidate_mask.shape != gray.shape:
            raise PipelineError("Plano candidato incompatível com a referência 2D.")
        candidate_boundary = candidate_mask & ~ndimage.binary_erosion(
            candidate_mask, iterations=1, border_value=0
        )
        candidate_boundary_image = Image.fromarray(
            (candidate_boundary * 255).astype(np.uint8), mode="L"
        ).resize(target, Image.Resampling.NEAREST)
        amber = Image.new("RGB", target, (255, 132, 0))
        rgb.paste(amber, mask=candidate_boundary_image)
    canvas = Image.new("RGB", (REFERENCE_SIZE_PX, REFERENCE_SIZE_PX), (8, 13, 17))
    offset = ((REFERENCE_SIZE_PX - target[0]) // 2, (REFERENCE_SIZE_PX - target[1]) // 2)
    canvas.paste(rgb, offset)
    return canvas


def _save_png_atomic(image: Image.Image, path: Path) -> None:
    temp = path.with_name(f".{path.name}.tmp")
    try:
        image.save(temp, format="PNG", optimize=True)
        temp.replace(path)
    finally:
        temp.unlink(missing_ok=True)


def generate_reference_images(
    volume_path: Path,
    organ_mask_path: Path,
    output_dir: Path,
    candidate_mask_path: Path | None = None,
) -> dict[str, Any]:
    """Gera stack axial completo do fígado e referências ortogonais sem PHI."""
    output_dir.mkdir(parents=True, exist_ok=True)
    volume_image, mask_image = _canonical_reference_pair(volume_path, organ_mask_path)
    volume = array_from(volume_image)
    mask = array_from(mask_image) > 0
    candidate: np.ndarray | None = None
    if candidate_mask_path is not None and Path(candidate_mask_path).is_file():
        candidate_image = _as_3d(read_image(Path(candidate_mask_path)), "Máscara candidata")
        try:
            candidate_image = sitk.DICOMOrient(candidate_image, "LPS")
        except RuntimeError as exc:
            raise PipelineError(f"Falha ao orientar máscara candidata em LPS: {exc}") from exc
        if not _same_geometry(mask_image, candidate_image):
            raise PipelineError("Máscara candidata incompatível com a referência 2D.")
        candidate = array_from(candidate_image) > 0
    if volume.ndim != 3 or mask.ndim != 3 or volume.shape != mask.shape:
        raise PipelineError("Volume e máscara incompatíveis para referências 2D.")
    locations = np.argwhere(mask)
    if locations.size == 0:
        raise PipelineError("Máscara hepática vazia ao criar referências 2D.")
    gray, low, high = _window_volume(volume, mask)
    spacing_x, spacing_y, spacing_z = (float(value) for value in mask_image.GetSpacing())
    centroid_z, centroid_y, centroid_x = np.rint(locations.mean(axis=0)).astype(int)
    axial_indices = np.flatnonzero(mask.any(axis=(1, 2))).astype(int).tolist()
    candidate_present = candidate is not None and bool(candidate.any())
    if candidate_present:
        candidate_z = int(np.argmax(candidate.sum(axis=(1, 2))))
        candidate_y = int(np.argmax(candidate.sum(axis=(0, 2))))
        candidate_x = int(np.argmax(candidate.sum(axis=(0, 1))))
    else:
        candidate_z, candidate_y, candidate_x = centroid_z, centroid_y, centroid_x

    expected_files: set[str] = set()
    axial_frames: list[dict[str, Any]] = []
    total = len(axial_indices)
    for order, z_index in enumerate(axial_indices, start=1):
        filename = f"{REFERENCE_PREFIX}axial_{order:03d}_of_{total:03d}.png"
        expected_files.add(filename)
        path = output_dir / filename
        _save_png_atomic(
            _render_reference_slice(
                gray[z_index], mask[z_index], (spacing_x, spacing_y),
                candidate[z_index] if candidate is not None else None,
            ),
            path,
        )
        position = mask_image.TransformIndexToPhysicalPoint(
            (int(centroid_x), int(centroid_y), int(z_index))
        )
        relative = 0.0 if total == 1 else (order - 1) / (total - 1) * 100.0
        axial_frames.append(
            {
                "file": filename,
                "sha256": sha256_of(path),
                "index": int(z_index),
                "position_lps_mm": round(float(position[2]), 4),
                "relative_liver_position_percent": round(float(relative), 2),
                "candidate_visible_in_plane": bool(
                    candidate_present and candidate[z_index].any()
                ),
            }
        )

    axial_default_index = min(
        range(len(axial_indices)),
        key=lambda index: abs(axial_indices[index] - candidate_z),
    )

    orthogonal: dict[str, dict[str, Any]] = {}
    planes = {
        "coronal": (
            np.flipud(gray[:, candidate_y, :]),
            np.flipud(mask[:, candidate_y, :]),
            np.flipud(candidate[:, candidate_y, :]) if candidate is not None else None,
            (spacing_x, spacing_z),
            candidate_y,
            1,
            {"top": "S", "bottom": "I", "left": "R", "right": "L"},
        ),
        "sagittal": (
            np.flipud(gray[:, :, candidate_x]),
            np.flipud(mask[:, :, candidate_x]),
            np.flipud(candidate[:, :, candidate_x]) if candidate is not None else None,
            (spacing_y, spacing_z),
            candidate_x,
            0,
            {"top": "S", "bottom": "I", "left": "A", "right": "P"},
        ),
    }
    for orientation, (plane, plane_mask, plane_candidate, plane_spacing, index, axis, labels) in planes.items():
        filename = f"{REFERENCE_PREFIX}{orientation}_centroid.png"
        expected_files.add(filename)
        path = output_dir / filename
        _save_png_atomic(
            _render_reference_slice(plane, plane_mask, plane_spacing, plane_candidate), path
        )
        point_index = [int(centroid_x), int(centroid_y), int(centroid_z)]
        point_index[axis] = int(index)
        position = mask_image.TransformIndexToPhysicalPoint(tuple(point_index))
        orthogonal[orientation] = {
            "default_frame_index": 0,
            "selection_basis": (
                "maximum_unconfirmed_candidate_cross_section"
                if candidate_present else "liver_centroid"
            ),
            "frames": [
                {
                    "file": filename,
                    "sha256": sha256_of(path),
                    "index": int(index),
                    "position_lps_mm": round(float(position[axis]), 4),
                    "candidate_visible_in_plane": bool(
                        plane_candidate is not None and plane_candidate.any()
                    ),
                }
            ],
            "orientation_labels": labels,
        }

    for stale in output_dir.glob(f"{REFERENCE_PREFIX}*.png"):
        if stale.name not in expected_files:
            stale.unlink()

    return {
        "source": "anonymized_mr_volume_with_automatic_liver_mask_boundary",
        "diagnostic_use": False,
        "contains_phi_metadata": False,
        "overlay": (
            "automatic_liver_boundary_yellow_and_unconfirmed_candidate_amber"
            if candidate is not None and bool(candidate.any())
            else "automatic_liver_mask_boundary_yellow"
        ),
        "window": {
            "method": "fixed_liver_percentile_1_99_for_entire_case",
            "lower": round(low, 6),
            "upper": round(high, 6),
        },
        "views": {
            "axial": {
                "coverage": "all_liver_bearing_planes",
                "default_frame_index": int(axial_default_index),
                "selection_basis": (
                    "maximum_unconfirmed_candidate_cross_section"
                    if candidate_present else "liver_midpoint"
                ),
                "frames": axial_frames,
                "orientation_labels": {
                    "top": "A",
                    "bottom": "P",
                    "left": "R",
                    "right": "L",
                },
            },
            **orthogonal,
        },
    }


def acquisition_summary(
    volume_path: Path,
    organ_mask_path: Path,
    *,
    mesh_isotropic_spacing_mm: float | None,
    mesh_smoothing_sigma_mm: float | None,
) -> dict[str, Any]:
    volume, mask = _canonical_reference_pair(volume_path, organ_mask_path)
    mask_array = array_from(mask) > 0
    axial = np.flatnonzero(mask_array.any(axis=(1, 2))).astype(int).tolist()
    return {
        "modality": "MR",
        "display_orientation": "LPS",
        "size_xyz": [int(value) for value in volume.GetSize()],
        "source_spacing_mm": [round(float(value), 6) for value in volume.GetSpacing()],
        "source_direction": [round(float(value), 8) for value in volume.GetDirection()],
        "liver_axial_first_index": axial[0] if axial else None,
        "liver_axial_last_index": axial[-1] if axial else None,
        "liver_axial_planes": len(axial),
        "mesh_isotropic_spacing_mm": mesh_isotropic_spacing_mm,
        "mesh_smoothing_sigma_mm": mesh_smoothing_sigma_mm,
        "interpolation_disclosure": (
            "A superfície entre cortes é reconstruída por interpolação; "
            "detalhe não presente na aquisição não pode ser recuperado."
        ),
    }


def nearest_surface_relationships(
    meshes_by_role: dict[str, pv.PolyData],
    target_roles: Iterable[str],
    source_role: str = "lesao",
) -> list[dict[str, Any]]:
    """Exploratory distances from a selected region to available surfaces."""
    source_mesh = meshes_by_role.get(source_role)
    if source_mesh is None or source_mesh.n_points == 0:
        return []
    source = np.asarray(source_mesh.points, dtype=np.float64)
    relationships: list[dict[str, Any]] = []
    for role in target_roles:
        target = meshes_by_role.get(role)
        if target is None or target.n_points == 0:
            continue
        distances, _ = cKDTree(np.asarray(target.points, dtype=np.float64)).query(
            source, k=1
        )
        relationships.append(
            {
                "source_role": source_role,
                "target_role": role,
                "minimum_surface_distance_mm": round(float(np.min(distances)), 4),
                "method": "nearest_mesh_vertex",
                "approximate": True,
            }
        )
    return relationships


def lesion_segment_overlap(
    lesion_mask_path: Path,
    segment_masks: dict[str, Path],
) -> dict[str, Any] | None:
    if not lesion_mask_path.is_file() or not segment_masks:
        return None
    lesion_image = _as_3d(read_image(lesion_mask_path), "Máscara de lesão")
    lesion = array_from(lesion_image) > 0
    lesion_voxels = int(np.count_nonzero(lesion))
    if lesion_voxels == 0:
        return None
    overlaps: list[dict[str, Any]] = []
    for role, path in sorted(segment_masks.items()):
        segment_image = _as_3d(read_image(path), f"Máscara {role}")
        if not _same_geometry(lesion_image, segment_image):
            continue
        overlap = int(np.count_nonzero(lesion & (array_from(segment_image) > 0)))
        if overlap:
            overlaps.append(
                {
                    "segment_role": role,
                    "overlap_voxels": overlap,
                    "lesion_overlap_percent": round(overlap / lesion_voxels * 100.0, 4),
                }
            )
    overlaps.sort(key=lambda item: (-item["overlap_voxels"], item["segment_role"]))
    return {
        "source": "manual_lesion_mask_and_automatic_couinaud_masks",
        "lesion_voxels": lesion_voxels,
        "dominant_segment_role": overlaps[0]["segment_role"] if overlaps else None,
        "overlaps": overlaps,
        "not_surgical_planning": True,
    }
