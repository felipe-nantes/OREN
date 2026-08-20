"""Full-FOV liver-enriched multiphase panels using a coarse axial localizer only."""
from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageDraw
from scipy.ndimage import label as connected_components

from .core import PipelineError, array_from, now_utc, read_image, sha256_of
from .medgemma_panel import (
    PANEL_MANIFEST_FILENAME,
    _geometry_compatible,
    _require_file,
    _select_uniform_indices,
    _validate_case_manifest,
)
from .medgemma_panel_full_fov import _robust_nonzero_window
from .medgemma_panel_multiphase import (
    RGB_CHANNELS,
    _render_color_tile,
    _resolve_channel_map,
)

LIVER_ENRICHED_POLICY = "coarse_liver_localized_full_fov_interleaved_2or3x9_v1"


@dataclass(frozen=True)
class LiverEnrichedPanelSetResult:
    panel_paths: tuple[Path, ...]
    manifest_path: Path
    axial_indices: tuple[int, ...]
    panel_axial_indices: tuple[tuple[int, ...], ...]
    panel_count: int


def _largest_component(mask: np.ndarray) -> tuple[np.ndarray, float]:
    labels, count = connected_components(mask.astype(bool))
    if count < 1:
        raise PipelineError("Localizador hepatico vazio.")
    sizes = np.bincount(labels.ravel())
    component_id = int(np.argmax(sizes[1:]) + 1)
    component = labels == component_id
    return component, float(component.sum() / mask.sum())


def _expand_interval(
    *, start: int, end: int, lower: int, upper: int, minimum_planes: int,
) -> tuple[int, int]:
    start, end = max(lower, start), min(upper, end)
    while end - start + 1 < minimum_planes and (start > lower or end < upper):
        if start > lower:
            start -= 1
        if end - start + 1 < minimum_planes and end < upper:
            end += 1
    if end - start + 1 < minimum_planes:
        raise PipelineError("Extensao corporal insuficiente para o painel liver-enriched.")
    return start, end


def select_liver_enriched_indices(
    *, mask: np.ndarray, body_present: np.ndarray, spacing_z: float,
    padding_mm: float = 20.0, stable_min_planes: int = 9,
    stable_min_component_fraction: float = 0.75,
) -> tuple[tuple[tuple[int, ...], ...], dict[str, Any]]:
    """Choose interleaved 3x9 when localization is stable, otherwise 2x9 fallback."""
    if mask.ndim != 3 or body_present.ndim != 1 or mask.shape[0] != body_present.size:
        raise PipelineError("Geometria do localizador liver-enriched invalida.")
    body_indices = np.flatnonzero(body_present)
    if body_indices.size < 27:
        raise PipelineError("Volume possui menos de 27 planos corporais.")
    component, component_fraction = _largest_component(mask)
    component_indices = np.flatnonzero(component.reshape(component.shape[0], -1).any(axis=1))
    raw_indices = np.flatnonzero(mask.reshape(mask.shape[0], -1).any(axis=1))
    if component_indices.size == 0:
        raise PipelineError("Maior componente hepatico sem planos axiais.")
    stable = (
        component_indices.size >= stable_min_planes
        and component_fraction >= stable_min_component_fraction
    )
    if stable:
        padding_planes = max(1, int(np.ceil(float(padding_mm) / float(spacing_z))))
        start, end = _expand_interval(
            start=int(component_indices[0]) - padding_planes,
            end=int(component_indices[-1]) + padding_planes,
            lower=int(body_indices[0]),
            upper=int(body_indices[-1]),
            minimum_planes=27,
        )
        candidates = np.arange(start, end + 1, dtype=int)
        all_indices = _select_uniform_indices(candidates, 27)
        groups = tuple(tuple(all_indices[offset::3]) for offset in range(3))
        mode = "stable_coarse_localizer_interleaved_3x9"
    else:
        # Harmonized LLD dynamic T1 volumes run cranial-to-caudal in array order.
        # The fallback keeps the first 75% of the body-bearing span and ignores
        # the unreliable mask for slice selection.
        fallback_end_pos = int(np.floor((body_indices.size - 1) * 0.75))
        fallback = body_indices[: fallback_end_pos + 1]
        if fallback.size < 18:
            fallback = body_indices
        all_indices = _select_uniform_indices(fallback, 18)
        groups = tuple(tuple(all_indices[offset::2]) for offset in range(2))
        start, end = int(fallback[0]), int(fallback[-1])
        mode = "weak_localizer_mask_independent_cranial_75pct_interleaved_2x9"
    if any(len(group) != 9 or tuple(sorted(group)) != group for group in groups):
        raise PipelineError("Distribuicao intercalada liver-enriched invalida.")
    flattened = tuple(index for group in groups for index in group)
    if len(flattened) != len(set(flattened)):
        raise PipelineError("Painel liver-enriched repetiu cortes axiais.")
    mask_by_plane = component.reshape(component.shape[0], -1).any(axis=1)
    supported = [sum(bool(mask_by_plane[index]) for index in group) for group in groups]
    audit = {
        "selection_mode": mode,
        "localizer_stable": stable,
        "raw_localizer_axial_range": [int(raw_indices[0]), int(raw_indices[-1])],
        "largest_component_axial_range": [int(component_indices[0]), int(component_indices[-1])],
        "largest_component_plane_count": int(component_indices.size),
        "largest_component_fraction": component_fraction,
        "selected_axial_range": [int(start), int(end)],
        "selected_distinct_axial_count": len(flattened),
        "panel_localizer_supported_tile_counts": supported,
    }
    return groups, audit


def generate_liver_enriched_panel_set_multiphase(
    *, phase_paths: Mapping[str, Path], coarse_liver_mask_path: Path,
    case_manifest_path: Path, screening_config: dict[str, Any], output_dir: Path,
    model_trace: dict[str, Any], visible_phi_confirmed: bool = False,
) -> LiverEnrichedPanelSetResult:
    panel_cfg = screening_config.get("panel", {})
    if panel_cfg.get("spatial_focus") != "liver_enriched_full_fov":
        raise PipelineError("Painel liver-enriched exige spatial_focus=liver_enriched_full_fov.")
    if int(panel_cfg.get("axial_slices", 9)) != 9:
        raise PipelineError("Painel liver-enriched exige nove cortes axiais por painel.")
    channel_map = _resolve_channel_map(panel_cfg)
    required_phases = sorted(set(channel_map.values()))
    single_phase_replicated = len(required_phases) == 1
    paths = {str(name): Path(path) for name, path in phase_paths.items()}
    if set(required_phases) - set(paths):
        raise PipelineError("Fases obrigatorias ausentes no painel liver-enriched.")
    for name in required_phases:
        _require_file(paths[name], f"Fase liver-enriched '{name}'")
    coarse_liver_mask_path = Path(coarse_liver_mask_path)
    _require_file(coarse_liver_mask_path, "Localizador hepatico grosseiro")
    case_manifest = _validate_case_manifest(Path(case_manifest_path))
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    images = {name: read_image(paths[name]) for name in required_phases}
    reference = images[required_phases[0]]
    mask_image = read_image(coarse_liver_mask_path)
    if reference.GetDimension() != 3 or any(
        not _geometry_compatible(reference, image) for image in (*images.values(), mask_image)
    ):
        raise PipelineError("Fases e localizador liver-enriched devem compartilhar a grade 3D.")
    arrays = {name: array_from(image).astype(np.float32) for name, image in images.items()}
    mask = array_from(mask_image) > 0
    shape = arrays[required_phases[0]].shape
    low = float(panel_cfg.get("window_percentile_low", 2.0))
    high = float(panel_cfg.get("window_percentile_high", 98.0))
    normalized: dict[str, np.ndarray] = {}
    available: dict[str, np.ndarray] = {}
    phase_hashes: dict[str, str] = {}
    for name in required_phases:
        array = arrays[name]
        lo, hi = _robust_nonzero_window(array, low, high)
        normalized[name] = np.clip((array - lo) / (hi - lo), 0.0, 1.0)
        available[name] = np.isfinite(array) & (array != 0)
        phase_hashes[name] = sha256_of(paths[name])
    joint = np.logical_and.reduce([available[name] for name in required_phases])
    body_support = np.logical_or.reduce([available[name] for name in required_phases])
    minimum_fraction = float(panel_cfg.get("minimum_slice_nonzero_fraction", 0.02))
    axial_fraction = body_support.reshape(shape[0], -1).mean(axis=1)
    groups, localization = select_liver_enriched_indices(
        mask=mask,
        body_present=axial_fraction >= minimum_fraction,
        spacing_z=float(reference.GetSpacing()[2]),
        padding_mm=float(panel_cfg.get("localizer_padding_mm", 20.0)),
        stable_min_planes=int(panel_cfg.get("localizer_stable_min_planes", 9)),
        stable_min_component_fraction=float(
            panel_cfg.get("localizer_stable_min_component_fraction", 0.75)
        ),
    )
    coordinates = np.argwhere(body_support)
    _z, yc, xc = np.rint(coordinates.mean(axis=0)).astype(int)
    red, green, blue = (channel_map[channel] for channel in RGB_CHANNELS)
    fallback_phase = str(panel_cfg.get("fusion", {}).get("partial_fov_fallback_phase", "pv"))

    def fuse(selection) -> np.ndarray:
        rgb = np.stack(
            [normalized[red][selection], normalized[green][selection], normalized[blue][selection]],
            axis=-1,
        )
        partial = ~joint[selection]
        fallback = normalized[fallback_phase][selection]
        rgb[partial] = np.stack([fallback[partial]] * 3, axis=-1)
        return rgb

    tile_size = int(panel_cfg.get("tile_size", 384))
    sx, sy, sz = (float(value) for value in reference.GetSpacing())

    def render(rgb: np.ndarray, label: str, row_spacing: float, col_spacing: float) -> Image.Image:
        return _render_color_tile(
            rgb, np.zeros(rgb.shape[:2], dtype=bool), label, tile_size,
            row_spacing, col_spacing, 1, (255, 255, 255), 1.0,
        )

    coronal = render(fuse(np.s_[:, yc, :]), "CORONAL (CENTRO CORPORAL)", sz, sx)
    sagittal = render(fuse(np.s_[:, :, xc]), "SAGITAL (CENTRO CORPORAL)", sz, sy)
    panel_paths: list[Path] = []
    panel_records: list[dict[str, Any]] = []
    total = len(groups)
    for panel_number, indices in enumerate(groups, start=1):
        canvas = Image.new("RGB", (tile_size * 4, tile_size * 3), (10, 14, 20))
        for tile_number, z in enumerate(indices, start=1):
            tile = render(
                fuse(np.s_[z]),
                f"AXIAL {tile_number}/9 | PAINEL {panel_number}/{total} | Z={z}", sy, sx,
            )
            canvas.paste(tile, (((tile_number - 1) % 3) * tile_size, ((tile_number - 1) // 3) * tile_size))
        canvas.paste(coronal, (3 * tile_size, 0))
        canvas.paste(sagittal, (3 * tile_size, tile_size))
        notice = Image.new("RGB", (tile_size, tile_size), (18, 24, 32))
        ImageDraw.Draw(notice).multiline_text(
            (14, 18),
            "MODO PESQUISA\n\nFULL-FOV LIVER-ENRICHED\nSEM CONTORNO\nSEM CROP HEPATICO\n\n"
            f"PAINEL {panel_number}/{total}\nCORTES INTERCALADOS\nR={red} G={green} B={blue}\n\n"
            "Revisao humana obrigatoria.",
            fill=(235, 240, 246), spacing=6,
        )
        canvas.paste(notice, (3 * tile_size, 2 * tile_size))
        panel_path = output_dir / (
            f"medgemma_liver_screening_panel_{panel_number:03d}_of_{total:03d}.png"
        )
        canvas.save(panel_path, format="PNG", optimize=True)
        with Image.open(panel_path) as exported:
            metadata_keys = sorted(exported.info)
        if metadata_keys:
            raise PipelineError("PNG liver-enriched contem metadados inesperados.")
        panel_paths.append(panel_path)
        panel_records.append({
            "panel_number": panel_number,
            "panel_total": total,
            "image": panel_path.name,
            "sha256": sha256_of(panel_path),
            "axial_indices_zyx_absolute": list(indices),
            "axial_interval": [int(indices[0]), int(indices[-1])],
            "localizer_supported_tile_count": localization["panel_localizer_supported_tile_counts"][panel_number - 1],
            "png_metadata_keys": metadata_keys,
        })
    all_indices = tuple(index for group in groups for index in group)
    manifest = {
        "case_id": case_manifest["case_id"],
        "organ": "liver",
        "modality": "MRI",
        "regulatory_mode": "RESEARCH",
        "input_type": (
            "mri_single_phase_replicated_grayscale_full_fov_liver_enriched"
            if single_phase_replicated
            else "mri_multiphase_rgb_fusion_full_fov_liver_enriched"
        ),
        "spatial_policy": LIVER_ENRICHED_POLICY,
        "organ_mask_used": True,
        "organ_mask_use_scope": "coarse_axial_localization_only_not_rendered_not_cropped",
        "organ_mask_rendered": False,
        "lesion_mask_used": False,
        "ground_truth_used": False,
        "crop_to_liver": False,
        "contour_rendered": False,
        "panel_image_count": total,
        "panels": panel_records,
        "input_volume_sha256": phase_hashes[channel_map["red"]],
        "input_phase_sha256": phase_hashes,
        "coarse_liver_mask_sha256": sha256_of(coarse_liver_mask_path),
        "fusion_channel_map": channel_map,
        "single_phase_replicated_across_rgb": single_phase_replicated,
        "dynamic_enhancement_information_present": not single_phase_replicated,
        "localization": localization,
        "views": {
            "total_distinct_axial_indices": len(all_indices),
            "all_axial_indices_zyx_absolute": sorted(all_indices),
            "coronal_body_center_y": int(yc),
            "sagittal_body_center_x": int(xc),
        },
        "phi_metadata_removed": True,
        "visible_phi_review_required": True,
        "visible_phi_confirmed": bool(visible_phi_confirmed),
        "created_at": now_utc(),
        "requires_human_review": True,
        **model_trace,
        "notes": [
            "The organ mask is used only to select a generous axial range.",
            "No organ contour, crop, lesion mask, label, or ground truth is rendered.",
            "Interleaving makes every panel traverse the selected liver territory.",
            "Weak localizers trigger a mask-independent two-panel fallback.",
            (
                "A single source phase is replicated across RGB without creating "
                "synthetic phase differences."
                if single_phase_replicated
                else "RGB channels preserve the configured source phases."
            ),
            "Research use only.",
        ],
    }
    manifest_path = output_dir / PANEL_MANIFEST_FILENAME
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    return LiverEnrichedPanelSetResult(
        panel_paths=tuple(panel_paths), manifest_path=manifest_path,
        axial_indices=tuple(sorted(all_indices)), panel_axial_indices=groups,
        panel_count=total,
    )


__all__ = [
    "LIVER_ENRICHED_POLICY",
    "LiverEnrichedPanelSetResult",
    "generate_liver_enriched_panel_set_multiphase",
    "select_liver_enriched_indices",
]
