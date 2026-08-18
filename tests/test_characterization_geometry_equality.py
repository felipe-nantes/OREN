"""Characterization: comparadores de igualdade de geometria (PHASE_03, OBSERVED_BEHAVIOR).

Estes testes FIXAM o comportamento atual dos três comparadores de geometria do
snapshot auditado; não afirmam que ele é correto. Divergência documentada
(LONG_PLAN P0 #1; mudança exige HG-03/04):

- ``webapp.server._mesma_geometria_sitk`` compara size/spacing/origin por
  igualdade EXATA e IGNORA direction. É o gate da união de máscaras por fase
  (server.py:984): uma máscara com direction divergente entraria na união.
- ``dtwin.segmentation_contract.same_geometry`` e
  ``dtwin.volumetry._same_geometry`` comparam também direction, com atol=1e-5.

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


def test_observed_server_ignora_direction_mas_contract_e_volumetry_nao():
    """OBSERVED_BEHAVIOR: só o comparador do webapp aceita direction divergente."""
    referencia = _imagem()
    flip = _imagem(direction=FLIP_Z)

    assert _mesma_geometria_sitk(referencia, flip) is True
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


def test_observed_direction_dentro_da_tolerancia_e_aceita_pelos_estritos():
    referencia = _imagem()
    direcao_quase = list(IDENTIDADE)
    direcao_quase[8] = 1.0 - 9e-6
    quase = _imagem(direction=tuple(direcao_quase))

    assert same_geometry(referencia, quase) is True
    assert volumetry_same_geometry(referencia, quase) is True
    # O webapp compara tuplas exatas de size/spacing/origin e ignora direction,
    # então também aceita — mas por cegueira, não por tolerância.
    assert _mesma_geometria_sitk(referencia, quase) is True
