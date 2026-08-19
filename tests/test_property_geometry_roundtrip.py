"""Property tests — GEO-CONVERT-01 (PHASE_04_INVARIANTS).

Contrato (`.fable/CONTRACTS.md`, `GEO-CONVERT-01`): a conversão array<->SimpleITK
preserva a geometria de referência. Este arquivo codifica o invariante como
propriedade geral, gerada via Hypothesis, em vez de casos fixos: para
qualquer origin/spacing/direction fisicamente válidos e qualquer conteúdo de
voxel, `array_to_image(array_from(ref), ref)` deve reproduzir exatamente a
geometria e os dados de `ref` (round-trip sem perda).

Gap identificado na revisão PHASE_02 de CONTRACTS.md ("gap: round-trip
property test — fase 04"); TASK-2026-08-18-PH04-INV-01.
"""

from __future__ import annotations

import numpy as np
import SimpleITK as sitk
from hypothesis import given, settings
from hypothesis import strategies as st
from hypothesis.extra.numpy import arrays

from dtwin.core import array_from, array_to_image

SHAPE = (4, 5, 6)  # (z, y, x); pequeno o bastante para o Hypothesis explorar rápido

# Matrizes de direção 3x3 ortonormais válidas: identidade, permutações de
# eixo, flips e uma rotação oblíqua -- cobre os casos de aquisição do
# ARGOS/OREN (axial/coronal/sagital/flip/gantry tilt) sem reinventar geração
# aleatória de matrizes ortonormais.
_DIRECTIONS = [
    (1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0),  # identidade
    (1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, -1.0),  # Z invertido
    (-1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0),  # X invertido
    (0.0, 1.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, -1.0),  # permutação XY + Z invertido
    (
        1.0, 0.0, 0.0,
        0.0, 0.8660254037844387, -0.5,
        0.0, 0.5, 0.8660254037844387,
    ),  # rotação oblíqua de 30° em torno de X (gantry tilt)
]

_spacing = st.tuples(*[st.floats(min_value=0.05, max_value=50.0, allow_nan=False, allow_infinity=False)] * 3)
_origin = st.tuples(*[st.floats(min_value=-2000.0, max_value=2000.0, allow_nan=False, allow_infinity=False)] * 3)
_direction = st.sampled_from(_DIRECTIONS)
_voxels = arrays(dtype=np.uint8, shape=SHAPE, elements=st.integers(min_value=0, max_value=255))


def _referencia(spacing, origin, direction, voxels) -> sitk.Image:
    ref = sitk.GetImageFromArray(voxels)
    ref.SetSpacing(spacing)
    ref.SetOrigin(origin)
    ref.SetDirection(direction)
    return ref


@settings(max_examples=200, deadline=None)
@given(spacing=_spacing, origin=_origin, direction=_direction, voxels=_voxels)
def test_property_array_roundtrip_preserva_geometria_e_dados(spacing, origin, direction, voxels):
    """GEO-CONVERT-01: para qualquer geometria física válida, o round-trip
    array_from -> array_to_image reproduz origin/spacing/direction/size e os
    valores de voxel exatamente -- sem perda, sem arredondamento visível."""
    ref = _referencia(spacing, origin, direction, voxels)

    resultado = array_to_image(array_from(ref), ref)

    assert resultado.GetSize() == ref.GetSize()
    assert resultado.GetSpacing() == ref.GetSpacing()
    assert resultado.GetOrigin() == ref.GetOrigin()
    assert resultado.GetDirection() == ref.GetDirection()
    np.testing.assert_array_equal(array_from(resultado), voxels)


@settings(max_examples=200, deadline=None)
@given(spacing=_spacing, origin=_origin, direction=_direction, voxels=_voxels)
def test_property_array_to_image_ignora_geometria_do_array_de_entrada(spacing, origin, direction, voxels):
    """GEO-CONVERT-01 (caso adversarial): um array numpy não carrega
    geometria própria -- array_to_image deve herdar SEMPRE da referência
    passada explicitamente, nunca de metadado implícito do array de origem.
    Fabrica um array a partir de uma imagem COM outra geometria e confirma
    que só a geometria da referência final é usada."""
    origem_com_geometria_diferente = sitk.GetImageFromArray(voxels)
    origem_com_geometria_diferente.SetSpacing((9.0, 9.0, 9.0))
    origem_com_geometria_diferente.SetOrigin((-500.0, -500.0, -500.0))
    array_solto = array_from(origem_com_geometria_diferente)  # numpy puro, sem geometria

    ref = _referencia(spacing, origin, direction, voxels)
    resultado = array_to_image(array_solto, ref)

    assert resultado.GetSpacing() == ref.GetSpacing()
    assert resultado.GetOrigin() == ref.GetOrigin()
    assert resultado.GetDirection() == ref.GetDirection()
    assert resultado.GetSpacing() != origem_com_geometria_diferente.GetSpacing()
