"""Invariantes do piloto de teto T2/DWI por embedding.

O que estes testes protegem: a comparacao contra os 79,49% do braco B
(docs/143) so' e' legitima se a geometria de recorte for IDENTICA. Um ajuste
silencioso de margem, tile ou numero de cortes invalidaria o gate sem que
ninguem percebesse -- o numero continuaria saindo, so' que comparavel a nada.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np
import pytest
import SimpleITK as sitk


REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "tools" / "build_lld_mmri_v23_roi_ceiling_t2dwi_embedding_pilot.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("t2dwi_pilot", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


pilot = _load_module()


def test_crop_geometry_matches_the_reference_arm_exactly():
    """docs/143 usou margem 0,35, tile 448 e 3 cortes. Divergir invalida o gate."""
    assert pilot.MARGIN == 0.35
    assert pilot.TILE == 448
    assert pilot.N_SLICES == 3


def test_gate_is_the_prespecified_baseline_plus_two_points():
    assert pilot.BASELINE_B == 0.7949
    assert pilot.GATE_MARGIN == 0.02
    assert pilot.GATE_BALANCED == pytest.approx(0.8149)


def test_crop_geometry_is_square_and_centred_on_the_lesion():
    mask = np.zeros((20, 100, 100), dtype=bool)
    mask[8:13, 40:60, 30:50] = True
    z_indices, ya, yb, xa, xb = pilot.crop_geometry(mask)
    assert (yb - ya) == (xb - xa), "recorte deve ser quadrado para nao distorcer a lesao"
    assert ya < 50 < yb and xa < 40 < xb, "caixa deve conter o centro da lesao"
    assert len(z_indices) <= pilot.N_SLICES
    assert all(8 <= z <= 12 for z in z_indices), "cortes devem cair dentro da lesao"


def test_crop_geometry_rejects_a_lesion_too_small_to_be_meaningful():
    mask = np.zeros((20, 100, 100), dtype=bool)
    mask[10, 50, 50] = True
    assert pilot.crop_geometry(mask) is None


def test_single_slice_lesion_yields_one_slice_not_a_crash():
    mask = np.zeros((20, 100, 100), dtype=bool)
    mask[10, 40:60, 40:60] = True
    z_indices, *_ = pilot.crop_geometry(mask)
    assert z_indices == [10]


def test_window_is_robust_to_outliers_and_ignores_background():
    array = np.zeros((4, 10, 10), dtype=np.float32)
    array[0, :, :] = 100.0
    array[1, :, :] = 200.0
    array[2, 0, 0] = 100000.0  # outlier extremo
    result = pilot.window(array)
    assert result.min() >= 0.0 and result.max() <= 1.0
    assert result[3].max() == 0.0, "fundo zerado deve permanecer no piso da janela"


def test_window_returns_zeros_when_there_is_no_signal():
    assert pilot.window(np.zeros((3, 5, 5), dtype=np.float32)).max() == 0.0


def _image(array: np.ndarray, spacing, origin) -> sitk.Image:
    image = sitk.GetImageFromArray(array.astype(np.float32))
    image.SetSpacing(spacing)
    image.SetOrigin(origin)
    return image


def test_resampling_preserves_physical_position_not_voxel_index():
    """Uma fatia marcada numa posicao fisica deve reaparecer na MESMA posicao
    fisica na grade de referencia, mesmo com espacamento diferente."""
    moving = np.zeros((10, 20, 20), dtype=np.float32)
    moving[5, :, :] = 1.0                       # z fisico = 5 * 4.0 = 20.0 mm
    reference = np.zeros((40, 20, 20), dtype=np.float32)
    resampled, support = pilot.resample_to_reference(
        _image(moving, (1.0, 1.0, 4.0), (0.0, 0.0, 0.0)),
        _image(reference, (1.0, 1.0, 1.0), (0.0, 0.0, 0.0)),
    )
    peak = int(np.argmax(resampled.max(axis=(1, 2))))
    assert abs(peak - 20) <= 1, "o sinal deve cair na posicao fisica, nao no indice"
    assert support.any()


def test_support_marks_uncovered_region_when_source_field_of_view_is_smaller():
    moving = np.ones((5, 20, 20), dtype=np.float32)
    reference = np.zeros((40, 20, 20), dtype=np.float32)
    _, support = pilot.resample_to_reference(
        _image(moving, (1.0, 1.0, 1.0), (0.0, 0.0, 0.0)),
        _image(reference, (1.0, 1.0, 1.0), (0.0, 0.0, 0.0)),
    )
    covered = float(support.mean())
    assert 0.0 < covered < 1.0, "FOV menor deve gerar cobertura parcial, nao total"


def test_minimum_coverage_threshold_is_explicit():
    """Cobertura insuficiente vira sinal ausente com indicador, nunca remocao
    silenciosa do denominador."""
    assert pilot.MIN_COVERAGE == 0.90
