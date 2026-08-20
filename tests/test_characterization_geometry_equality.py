"""Spec: comparadores de igualdade de geometria (PHASE_03 → PHASE_09).

Origem: characterization da PHASE_03, que FIXOU o comportamento então
observado — o comparador do webapp ignorava direction (era o gate da união de
fases). Em 2026-08-20 a decisão **HG-03, HUMAN_DECISIONS item 13** aprovou a
opção A1: o webapp passou a exigir direction com ``np.allclose(rtol=0,
atol=1e-6)``, mantendo size/spacing/origin EXATOS. Estes testes agora
AFIRMAM o comportamento aprovado:

- ``webapp.server._mesma_geometria_sitk``: size/spacing/origin exatos +
  direction com atol=1e-6 (mais estrito que os comparadores de contrato).
- ``dtwin.segmentation_contract.same_geometry`` e
  ``dtwin.volumetry._same_geometry``: size exato; spacing/origin/direction
  com atol=1e-5 (inalterados).

Se um destes testes quebrar, a semântica de igualdade geométrica mudou — pare
e consulte .fable/HUMAN_GATES.md (HG-03) antes de aceitar a mudança.
"""

from __future__ import annotations

import SimpleITK as sitk

from dtwin.segmentation_contract import same_geometry
from dtwin.volumetry import _same_geometry as volumetry_same_geometry
from webapp.server import _mesma_geometria_sitk

IDENTIDADE = (1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0)
FLIP_Z = (1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, -1.0)


def _imagem(
    size=(4, 5, 6),
    origin=(0.0, 0.0, 0.0),
    spacing=(1.0, 1.0, 1.0),
    direction=IDENTIDADE,
) -> sitk.Image:
    imagem = sitk.Image(int(size[0]), int(size[1]), int(size[2]), sitk.sitkUInt8)
    imagem.SetOrigin(tuple(float(v) for v in origin))
    imagem.SetSpacing(tuple(float(v) for v in spacing))
    imagem.SetDirection(tuple(float(v) for v in direction))
    return imagem


def test_todos_os_comparadores_rejeitam_direction_divergente():
    """HG-03 item 13 (2026-08-20): o webapp também rejeita o flip — antes o
    aceitava e a união fazia OR em array space fora do lugar físico."""
    referencia = _imagem()
    flip = _imagem(direction=FLIP_Z)

    assert _mesma_geometria_sitk(referencia, flip) is False
    assert same_geometry(referencia, flip) is False
    assert volumetry_same_geometry(referencia, flip) is False


def test_observed_server_rejeita_divergencia_de_size_spacing_origin():
    referencia = _imagem()
    assert _mesma_geometria_sitk(referencia, _imagem(size=(4, 5, 7))) is False
    assert _mesma_geometria_sitk(referencia, _imagem(spacing=(1.0, 1.0, 2.0))) is False
    assert _mesma_geometria_sitk(referencia, _imagem(origin=(0.0, 0.0, 0.5))) is False


def test_observed_server_usa_igualdade_exata_sem_tolerancia():
    """OBSERVED_BEHAVIOR: origin deslocado por 1e-9 já falha no webapp (sem atol),
    enquanto os comparadores estritos aceitam por estarem dentro de atol=1e-5."""
    referencia = _imagem()
    quase_igual = _imagem(origin=(0.0, 0.0, 1e-9))

    assert _mesma_geometria_sitk(referencia, quase_igual) is False
    assert same_geometry(referencia, quase_igual) is True
    assert volumetry_same_geometry(referencia, quase_igual) is True


def test_observed_contract_e_volumetry_respeitam_atol_1e_5():
    referencia = _imagem()
    dentro = _imagem(origin=(0.0, 0.0, 9e-6))
    fora = _imagem(origin=(0.0, 0.0, 1e-3))

    assert same_geometry(referencia, dentro) is True
    assert volumetry_same_geometry(referencia, dentro) is True
    assert same_geometry(referencia, fora) is False
    assert volumetry_same_geometry(referencia, fora) is False


def test_direction_quase_identica_tolerancias_por_comparador():
    referencia = _imagem()
    direcao_quase = list(IDENTIDADE)
    direcao_quase[8] = 1.0 - 9e-6
    quase = _imagem(direction=tuple(direcao_quase))

    assert same_geometry(referencia, quase) is True
    assert volumetry_same_geometry(referencia, quase) is True
    # HG-03 item 13: o webapp usa atol=1e-6 (mais estrito que o 1e-5 dos
    # comparadores de contrato) — desvio de 9e-6 é rejeitado por ele.
    assert _mesma_geometria_sitk(referencia, quase) is False

    direcao_micro = list(IDENTIDADE)
    direcao_micro[8] = 1.0 - 9e-7
    micro = _imagem(direction=tuple(direcao_micro))
    # Ruído abaixo de 1e-6 continua aceito pelos três.
    assert _mesma_geometria_sitk(referencia, micro) is True
    assert same_geometry(referencia, micro) is True
    assert volumetry_same_geometry(referencia, micro) is True
