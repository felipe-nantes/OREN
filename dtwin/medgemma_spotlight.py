#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Protótipo seguro de painel hepático com contexto extra-hepático atenuado.

O módulo opera somente sobre volume anonimizado e máscara do fígado. Não aceita,
lê ou procura máscara de lesão. Ele permanece separado do fluxo de produção até
que um piloto balanceado demonstre benefício.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from .core import PipelineError, array_from, read_image, sha256_of
from .medgemma_panel import (
    _geometry_compatible,
    _mask_bbox_2d,
    _render_tile,
    _select_uniform_indices,
    _window_limits,
)


@dataclass(frozen=True)
class SpotlightPanelResult:
    panel_path: Path
    panel_sha256: str
    axial_indices: tuple[int, ...]
    coronal_index: int
    sagittal_index: int
    outside_mask_intensity_fraction: float


def attenuate_outside_liver(
    image_2d: np.ndarray,
    liver_mask_2d: np.ndarray,
    *,
    window_low: float,
    outside_fraction: float,
) -> np.ndarray:
    """Preserva o fígado e aproxima o contexto externo do limite baixo da janela."""
    image = np.asarray(image_2d, dtype=np.float32)
    mask = np.asarray(liver_mask_2d, dtype=bool)
    if image.shape != mask.shape:
        raise PipelineError("Imagem e máscara 2D têm formas incompatíveis.")
    if isinstance(outside_fraction, bool) or not isinstance(outside_fraction, (int, float)):
        raise PipelineError("outside_fraction deve ser numérico.")
    fraction = float(outside_fraction)
    if not 0.0 <= fraction <= 0.5:
        raise PipelineError("outside_fraction deve estar entre 0.0 e 0.5.")
    attenuated = float(window_low) + (image - float(window_low)) * fraction
    return np.where(mask, image, attenuated).astype(np.float32, copy=False)


def render_uniform_spotlight_panel(
    *,
    volume_path: Path,
    liver_mask_path: Path,
    output_path: Path,
    outside_fraction: float = 0.15,
    crop_margin_fraction: float = 0.15,
    tile_size: int = 320,
    window_percentile_low: float = 1.0,
    window_percentile_high: float = 99.0,
) -> SpotlightPanelResult:
    """Gera a grade 4×3 baseline com somente o contexto fora do fígado atenuado."""
    volume_path = Path(volume_path)
    liver_mask_path = Path(liver_mask_path)
    output_path = Path(output_path)
    if not volume_path.is_file() or not liver_mask_path.is_file():
        raise PipelineError("Volume e máscara hepática preparados são obrigatórios.")
    if tile_size < 128:
        raise PipelineError("tile_size deve ser >= 128.")
    if not 0.0 <= float(crop_margin_fraction) <= 1.0:
        raise PipelineError("crop_margin_fraction deve estar entre 0.0 e 1.0.")
    if not 0.0 <= float(window_percentile_low) < float(window_percentile_high) <= 100.0:
        raise PipelineError("Percentis da janela de intensidade são inválidos.")

    volume_img = read_image(volume_path)
    mask_img = read_image(liver_mask_path)
    if volume_img.GetDimension() != 3 or not _geometry_compatible(volume_img, mask_img):
        raise PipelineError("Volume e máscara do fígado têm geometria 3D incompatível.")
    volume = array_from(volume_img).astype(np.float32)
    mask = array_from(mask_img) > 0
    if not np.any(mask):
        raise PipelineError("Máscara do fígado vazia.")

    axial_present = np.flatnonzero(mask.any(axis=(1, 2)))
    axial_indices = _select_uniform_indices(axial_present, 9)
    zc, yc, xc = (int(value) for value in np.rint(np.argwhere(mask).mean(axis=0)))
    del zc
    lo, hi = _window_limits(
        volume,
        mask,
        float(window_percentile_low),
        float(window_percentile_high),
    )
    # Valida a fração antes de iniciar qualquer renderização.
    attenuate_outside_liver(
        volume[axial_indices[0]],
        mask[axial_indices[0]],
        window_low=lo,
        outside_fraction=outside_fraction,
    )

    axial_bbox = _mask_bbox_2d(mask.any(axis=0), float(crop_margin_fraction))
    coronal_bbox = _mask_bbox_2d(mask.any(axis=1), float(crop_margin_fraction))
    sagittal_bbox = _mask_bbox_2d(mask.any(axis=2), float(crop_margin_fraction))
    sx, sy, sz = (float(value) for value in volume_img.GetSpacing())

    def render(
        image_2d: np.ndarray,
        mask_2d: np.ndarray,
        label: str,
        row_spacing: float,
        col_spacing: float,
        crop_bbox: tuple[int, int, int, int],
    ) -> Image.Image:
        return _render_tile(
            attenuate_outside_liver(
                image_2d,
                mask_2d,
                window_low=lo,
                outside_fraction=outside_fraction,
            ),
            mask_2d,
            label,
            tile_size,
            lo,
            hi,
            row_spacing,
            col_spacing,
            1,
            (255, 196, 0),
            crop_bbox,
            False,
        )

    tiles = [
        render(volume[z], mask[z], f"AXIAL {number}/9", sy, sx, axial_bbox)
        for number, z in enumerate(axial_indices, start=1)
    ]
    tiles.append(
        render(volume[:, yc, :], mask[:, yc, :], "CORONAL (CENTROIDE)", sz, sx, coronal_bbox)
    )
    tiles.append(
        render(volume[:, :, xc], mask[:, :, xc], "SAGITAL (CENTROIDE)", sz, sy, sagittal_bbox)
    )

    canvas = Image.new("RGB", (tile_size * 4, tile_size * 3), (10, 14, 20))
    for index, tile in enumerate(tiles[:9]):
        canvas.paste(tile, ((index % 3) * tile_size, (index // 3) * tile_size))
    canvas.paste(tiles[9], (3 * tile_size, 0))
    canvas.paste(tiles[10], (3 * tile_size, tile_size))
    notice = Image.new("RGB", (tile_size, tile_size), (18, 24, 32))
    ImageDraw.Draw(notice).multiline_text(
        (14, 18),
        "MODO PESQUISA\n\nContexto externo atenuado.\nSem marcacao de lesao.\n"
        "NAO e diagnostico.\nNAO e laudo medico.\n\nRevisao humana obrigatoria.",
        fill=(235, 240, 246),
        spacing=6,
    )
    canvas.paste(notice, (3 * tile_size, 2 * tile_size))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_name(f".{output_path.name}.tmp")
    canvas.save(temporary, format="PNG", optimize=True)
    temporary.replace(output_path)
    with Image.open(output_path) as exported:
        if exported.info:
            raise PipelineError("PNG spotlight contém metadados inesperados.")
    return SpotlightPanelResult(
        panel_path=output_path,
        panel_sha256=sha256_of(output_path),
        axial_indices=axial_indices,
        coronal_index=yc,
        sagittal_index=xc,
        outside_mask_intensity_fraction=float(outside_fraction),
    )
