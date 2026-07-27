"""Mask-independent full-FOV multiphase MRI research panel."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

import numpy as np
from PIL import Image, ImageDraw

from .core import PipelineError, array_from, now_utc, read_image, sha256_of
from .medgemma_panel import (
    PANEL_FILENAME,
    PANEL_MANIFEST_FILENAME,
    PanelResult,
    _geometry_compatible,
    _require_file,
    _select_uniform_indices,
    _validate_case_manifest,
)
from .medgemma_panel_multiphase import (
    RGB_CHANNELS,
    _render_color_tile,
    _resolve_channel_map,
)


FULL_FOV_POLICY = "mask_independent_full_acquired_fov_uniform9_v1"
FULL_FOV_MULTIPANEL_POLICY = "mask_independent_full_acquired_fov_3x9_v1"


@dataclass(frozen=True)
class FullFovPanelSetResult:
    panel_paths: tuple[Path, ...]
    manifest_path: Path
    axial_indices: tuple[int, ...]
    panel_axial_indices: tuple[tuple[int, ...], ...]
    coronal_index: int
    sagittal_index: int


def _robust_nonzero_window(array: np.ndarray, low: float, high: float) -> tuple[float, float]:
    values = array[np.isfinite(array) & (array != 0)]
    if values.size == 0:
        values = array[np.isfinite(array)]
    if values.size == 0:
        raise PipelineError("Fase full-FOV sem intensidades finitas.")
    lo, hi = np.percentile(values, [low, high]).astype(float)
    if hi - lo < 1e-6:
        lo, hi = float(values.min()), float(values.max())
    if hi - lo < 1e-6:
        raise PipelineError("Fase full-FOV sem contraste suficiente.")
    return lo, hi


def generate_full_fov_panel_multiphase(
    *,
    phase_paths: Mapping[str, Path],
    case_manifest_path: Path,
    screening_config: dict[str, Any],
    output_dir: Path,
    model_trace: dict[str, Any],
    visible_phi_confirmed: bool = False,
) -> PanelResult:
    """Render 9 systematic axial views plus body-centred coronal/sagittal views.

    No organ, lesion, label or ground-truth mask is accepted by this API.
    """

    panel_cfg = screening_config.get("panel", {})
    if panel_cfg.get("spatial_focus") != "full_fov_no_mask":
        raise PipelineError("Painel full-FOV exige spatial_focus=full_fov_no_mask.")
    if int(panel_cfg.get("axial_slices", 9)) != 9:
        raise PipelineError("Painel full-FOV exige exatamente nove cortes axiais.")
    channel_map = _resolve_channel_map(panel_cfg)
    required_phases = sorted(set(channel_map.values()))
    paths = {str(name): Path(path) for name, path in phase_paths.items()}
    if set(required_phases) - set(paths):
        raise PipelineError("Fases obrigatorias ausentes no painel full-FOV.")
    for name in required_phases:
        _require_file(paths[name], f"Fase full-FOV '{name}'")
    case_manifest = _validate_case_manifest(Path(case_manifest_path))
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    images = {name: read_image(paths[name]) for name in required_phases}
    reference = images[required_phases[0]]
    if reference.GetDimension() != 3 or any(
        not _geometry_compatible(reference, image) for image in images.values()
    ):
        raise PipelineError("Fases full-FOV devem compartilhar a mesma grade 3D.")
    arrays = {name: array_from(image).astype(np.float32) for name, image in images.items()}
    shape = arrays[required_phases[0]].shape
    low = float(panel_cfg.get("window_percentile_low", 2.0))
    high = float(panel_cfg.get("window_percentile_high", 98.0))
    if not 0 <= low < high <= 100:
        raise PipelineError("Percentis full-FOV invalidos.")
    normalized: dict[str, np.ndarray] = {}
    available: dict[str, np.ndarray] = {}
    phase_hashes: dict[str, str] = {}
    for name in required_phases:
        array = arrays[name]
        lo, hi = _robust_nonzero_window(array, low, high)
        normalized[name] = np.clip((array - lo) / (hi - lo), 0.0, 1.0)
        available[name] = np.isfinite(array) & (array != 0)
        phase_hashes[name] = sha256_of(paths[name])

    fusion_cfg = panel_cfg.get("fusion", {})
    fallback_phase = str(fusion_cfg.get("partial_fov_fallback_phase", "pv"))
    if fallback_phase not in normalized:
        raise PipelineError("Fallback full-FOV deve ser uma fase configurada.")
    joint = np.logical_and.reduce([available[name] for name in required_phases])
    body_support = np.logical_or.reduce([available[name] for name in required_phases])
    minimum_fraction = float(panel_cfg.get("minimum_slice_nonzero_fraction", 0.02))
    if not 0.0 < minimum_fraction < 1.0:
        raise PipelineError("minimum_slice_nonzero_fraction full-FOV invalida.")
    axial_fraction = body_support.reshape(shape[0], -1).mean(axis=1)
    axial_present = np.flatnonzero(axial_fraction >= minimum_fraction)
    if axial_present.size < 9:
        raise PipelineError("Volume full-FOV possui menos de nove planos corporais.")
    axial_indices = _select_uniform_indices(axial_present, 9)
    coordinates = np.argwhere(body_support)
    if coordinates.size == 0:
        raise PipelineError("Suporte corporal full-FOV vazio.")
    _z, yc, xc = np.rint(coordinates.mean(axis=0)).astype(int)

    red, green, blue = (channel_map[channel] for channel in RGB_CHANNELS)

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
    if tile_size < 128:
        raise PipelineError("tile_size full-FOV deve ser >=128.")
    sx, sy, sz = (float(value) for value in reference.GetSpacing())

    def render(rgb: np.ndarray, label: str, row_spacing: float, col_spacing: float) -> Image.Image:
        return _render_color_tile(
            rgb,
            np.zeros(rgb.shape[:2], dtype=bool),
            label,
            tile_size,
            row_spacing,
            col_spacing,
            1,
            (255, 255, 255),
            1.0,
        )

    tiles = [
        render(fuse(np.s_[z]), f"AXIAL FULL-FOV {index}/9", sy, sx)
        for index, z in enumerate(axial_indices, start=1)
    ]
    tiles.append(render(fuse(np.s_[:, yc, :]), "CORONAL (CENTRO CORPORAL)", sz, sx))
    tiles.append(render(fuse(np.s_[:, :, xc]), "SAGITAL (CENTRO CORPORAL)", sz, sy))
    canvas = Image.new("RGB", (tile_size * 4, tile_size * 3), (10, 14, 20))
    for index, tile in enumerate(tiles[:9]):
        canvas.paste(tile, ((index % 3) * tile_size, (index // 3) * tile_size))
    canvas.paste(tiles[9], (3 * tile_size, 0))
    canvas.paste(tiles[10], (3 * tile_size, tile_size))
    notice = Image.new("RGB", (tile_size, tile_size), (18, 24, 32))
    ImageDraw.Draw(notice).multiline_text(
        (14, 18),
        "MODO PESQUISA\n\nFULL-FOV SEM MASCARA\nSEM CONTORNO\nSEM CROP HEPATICO\n\n"
        f"R={red}  G={green}  B={blue}\n\nRevisao humana obrigatoria.",
        fill=(235, 240, 246),
        spacing=6,
    )
    canvas.paste(notice, (3 * tile_size, 2 * tile_size))
    panel_path = output_dir / PANEL_FILENAME
    canvas.save(panel_path, format="PNG", optimize=True)
    with Image.open(panel_path) as exported:
        metadata_keys = sorted(exported.info)
    if metadata_keys:
        raise PipelineError("PNG full-FOV contem metadados inesperados.")

    representative_phase = channel_map["red"]
    manifest = {
        "case_id": case_manifest["case_id"],
        "organ": "liver",
        "modality": "MRI",
        "regulatory_mode": "RESEARCH",
        "input_type": "mri_multiphase_rgb_fusion_full_fov_no_mask",
        "spatial_policy": FULL_FOV_POLICY,
        "lesion_pre_marked": False,
        "organ_mask_used": False,
        "lesion_mask_used": False,
        "ground_truth_used": False,
        "crop_to_liver": False,
        "contour_rendered": False,
        "panel_image": panel_path.name,
        "panel_sha256": sha256_of(panel_path),
        "input_volume_sha256": phase_hashes[representative_phase],
        "input_phase_sha256": phase_hashes,
        "fusion_channel_map": channel_map,
        "phases_used": required_phases,
        "panel_count": 11,
        "views": {
            "axial_indices_zyx_absolute": list(axial_indices),
            "axial_source_range": [int(axial_present[0]), int(axial_present[-1])],
            "coronal_body_center_y": int(yc),
            "sagittal_body_center_x": int(xc),
        },
        "png_metadata_keys": metadata_keys,
        "phi_metadata_removed": True,
        "visible_phi_review_required": True,
        "visible_phi_confirmed": bool(visible_phi_confirmed),
        "created_at": now_utc(),
        "requires_human_review": True,
        **model_trace,
        "notes": [
            "No organ, lesion, label, or ground-truth mask was read or rendered.",
            "The complete in-plane acquired field of view is preserved.",
            "Nine distinct axial planes sample the complete body-bearing source span.",
            "Burned-in pixel PHI requires visual review before inference.",
            "Research use only.",
        ],
    }
    manifest_path = output_dir / PANEL_MANIFEST_FILENAME
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    return PanelResult(
        panel_path=panel_path,
        manifest_path=manifest_path,
        panel_count=11,
        axial_indices=axial_indices,
        coronal_index=int(yc),
        sagittal_index=int(xc),
        panel_paths=(panel_path,),
    )


def generate_full_fov_panel_set_multiphase(
    *,
    phase_paths: Mapping[str, Path],
    case_manifest_path: Path,
    screening_config: dict[str, Any],
    output_dir: Path,
    model_trace: dict[str, Any],
    visible_phi_confirmed: bool = False,
) -> FullFovPanelSetResult:
    """Render three mask-independent panels with 27 distinct axial planes.

    This is an opt-in coverage pilot. It samples the complete body-bearing
    source span but does not claim complete voxel or every-slice coverage.
    """

    panel_cfg = screening_config.get("panel", {})
    if panel_cfg.get("spatial_focus") != "full_fov_no_mask":
        raise PipelineError("Conjunto full-FOV exige spatial_focus=full_fov_no_mask.")
    panel_image_count = int(panel_cfg.get("panel_image_count", 1))
    slices_per_panel = int(panel_cfg.get("axial_slices", 9))
    if panel_image_count != 3 or slices_per_panel != 9:
        raise PipelineError("Piloto full-FOV multipainel exige 3 paineis de 9 cortes.")
    channel_map = _resolve_channel_map(panel_cfg)
    required_phases = sorted(set(channel_map.values()))
    paths = {str(name): Path(path) for name, path in phase_paths.items()}
    if set(required_phases) - set(paths):
        raise PipelineError("Fases obrigatorias ausentes no conjunto full-FOV.")
    for name in required_phases:
        _require_file(paths[name], f"Fase full-FOV '{name}'")
    case_manifest = _validate_case_manifest(Path(case_manifest_path))
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    images = {name: read_image(paths[name]) for name in required_phases}
    reference = images[required_phases[0]]
    if reference.GetDimension() != 3 or any(
        not _geometry_compatible(reference, image) for image in images.values()
    ):
        raise PipelineError("Fases full-FOV devem compartilhar a mesma grade 3D.")
    arrays = {name: array_from(image).astype(np.float32) for name, image in images.items()}
    shape = arrays[required_phases[0]].shape
    low = float(panel_cfg.get("window_percentile_low", 2.0))
    high = float(panel_cfg.get("window_percentile_high", 98.0))
    if not 0 <= low < high <= 100:
        raise PipelineError("Percentis full-FOV invalidos.")
    normalized: dict[str, np.ndarray] = {}
    available: dict[str, np.ndarray] = {}
    phase_hashes: dict[str, str] = {}
    for name in required_phases:
        array = arrays[name]
        lo, hi = _robust_nonzero_window(array, low, high)
        normalized[name] = np.clip((array - lo) / (hi - lo), 0.0, 1.0)
        available[name] = np.isfinite(array) & (array != 0)
        phase_hashes[name] = sha256_of(paths[name])

    fusion_cfg = panel_cfg.get("fusion", {})
    fallback_phase = str(fusion_cfg.get("partial_fov_fallback_phase", "pv"))
    if fallback_phase not in normalized:
        raise PipelineError("Fallback full-FOV deve ser uma fase configurada.")
    joint = np.logical_and.reduce([available[name] for name in required_phases])
    body_support = np.logical_or.reduce([available[name] for name in required_phases])
    minimum_fraction = float(panel_cfg.get("minimum_slice_nonzero_fraction", 0.02))
    if not 0.0 < minimum_fraction < 1.0:
        raise PipelineError("minimum_slice_nonzero_fraction full-FOV invalida.")
    axial_fraction = body_support.reshape(shape[0], -1).mean(axis=1)
    axial_present = np.flatnonzero(axial_fraction >= minimum_fraction)
    required_axials = panel_image_count * slices_per_panel
    if axial_present.size < required_axials:
        raise PipelineError(
            f"Volume full-FOV possui {axial_present.size} planos corporais; "
            f"o piloto 3x9 exige {required_axials}."
        )
    axial_indices = _select_uniform_indices(axial_present, required_axials)
    panel_axial_indices = tuple(
        tuple(axial_indices[start : start + slices_per_panel])
        for start in range(0, required_axials, slices_per_panel)
    )
    coordinates = np.argwhere(body_support)
    if coordinates.size == 0:
        raise PipelineError("Suporte corporal full-FOV vazio.")
    _z, yc, xc = np.rint(coordinates.mean(axis=0)).astype(int)
    red, green, blue = (channel_map[channel] for channel in RGB_CHANNELS)

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
    if tile_size < 128:
        raise PipelineError("tile_size full-FOV deve ser >=128.")
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
    for panel_number, indices in enumerate(panel_axial_indices, start=1):
        canvas = Image.new("RGB", (tile_size * 4, tile_size * 3), (10, 14, 20))
        for tile_number, z in enumerate(indices, start=1):
            tile = render(
                fuse(np.s_[z]),
                f"AXIAL {tile_number}/9 | PAINEL {panel_number}/3 | Z={z}",
                sy,
                sx,
            )
            canvas.paste(tile, (((tile_number - 1) % 3) * tile_size, ((tile_number - 1) // 3) * tile_size))
        canvas.paste(coronal, (3 * tile_size, 0))
        canvas.paste(sagittal, (3 * tile_size, tile_size))
        notice = Image.new("RGB", (tile_size, tile_size), (18, 24, 32))
        ImageDraw.Draw(notice).multiline_text(
            (14, 18),
            "MODO PESQUISA\n\nFULL-FOV SEM MASCARA\nSEM CONTORNO\nSEM CROP HEPATICO\n\n"
            f"PAINEL {panel_number}/3\nZ {indices[0]}-{indices[-1]}\nR={red} G={green} B={blue}\n\n"
            "Revisao humana obrigatoria.",
            fill=(235, 240, 246),
            spacing=6,
        )
        canvas.paste(notice, (3 * tile_size, 2 * tile_size))
        panel_path = output_dir / f"medgemma_liver_screening_panel_{panel_number:03d}_of_003.png"
        canvas.save(panel_path, format="PNG", optimize=True)
        with Image.open(panel_path) as exported:
            metadata_keys = sorted(exported.info)
        if metadata_keys:
            raise PipelineError("PNG full-FOV multipainel contem metadados inesperados.")
        panel_paths.append(panel_path)
        panel_records.append(
            {
                "panel_number": panel_number,
                "panel_image": panel_path.name,
                "panel_sha256": sha256_of(panel_path),
                "axial_indices_zyx_absolute": list(indices),
                "axial_range": [int(indices[0]), int(indices[-1])],
                "png_metadata_keys": metadata_keys,
            }
        )

    representative_phase = channel_map["red"]
    manifest = {
        "case_id": case_manifest["case_id"],
        "organ": "liver",
        "modality": "MRI",
        "regulatory_mode": "RESEARCH",
        "input_type": "mri_multiphase_rgb_fusion_full_fov_no_mask",
        "spatial_policy": FULL_FOV_MULTIPANEL_POLICY,
        "lesion_pre_marked": False,
        "organ_mask_used": False,
        "lesion_mask_used": False,
        "ground_truth_used": False,
        "crop_to_liver": False,
        "contour_rendered": False,
        "panel_image_count": len(panel_paths),
        "panels": panel_records,
        "input_volume_sha256": phase_hashes[representative_phase],
        "input_phase_sha256": phase_hashes,
        "fusion_channel_map": channel_map,
        "phases_used": required_phases,
        "views": {
            "total_distinct_axial_indices": len(axial_indices),
            "all_axial_indices_zyx_absolute": list(axial_indices),
            "axial_source_range": [int(axial_present[0]), int(axial_present[-1])],
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
            "No organ, lesion, label, or ground-truth mask was read or rendered.",
            "The complete in-plane acquired field of view is preserved.",
            "Twenty-seven distinct axial planes systematically sample the body-bearing source span.",
            "This protocol does not claim every source slice or every liver voxel is represented.",
            "Research use only.",
        ],
    }
    manifest_path = output_dir / PANEL_MANIFEST_FILENAME
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    return FullFovPanelSetResult(
        panel_paths=tuple(panel_paths),
        manifest_path=manifest_path,
        axial_indices=axial_indices,
        panel_axial_indices=panel_axial_indices,
        coronal_index=int(yc),
        sagittal_index=int(xc),
    )


__all__ = [
    "FULL_FOV_MULTIPANEL_POLICY",
    "FULL_FOV_POLICY",
    "FullFovPanelSetResult",
    "generate_full_fov_panel_multiphase",
    "generate_full_fov_panel_set_multiphase",
]
