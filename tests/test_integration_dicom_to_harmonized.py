"""Integração — cadeia DICOM bruto → resolver → leitura de série → harmonização
(PHASE_05, wave 3).

As peças são testadas isoladamente em test_raw_dicom_phase_resolver.py (o
resolver, com DICOM sem pixels) e test_learning_multiphase_ingest.py (o
ingest, com imagens SimpleITK fabricadas). A costura NUNCA testada é a cadeia
real entre elas: o diretório materializado pelo resolver alimenta
`read_phase_series` (GDCM montando série multi-slice de arquivos reais, com
ordenação espacial) e o resultado é harmonizado na grade venosa.

Fixtures: estudos DICOM sintéticos COM PixelData (16-bit MR multi-slice),
sem nenhum dado de paciente real.

TASK-2026-08-18-PH05-INT-03.
"""

from __future__ import annotations

import numpy as np
import pytest
import SimpleITK as sitk
from pydicom.dataset import FileDataset, FileMetaDataset
from pydicom.uid import ExplicitVRLittleEndian, generate_uid

from dtwin.learning.multiphase_ingest import (
    ARTERIAL,
    DELAYED,
    MINIMUM_COVERAGE,
    VENOUS,
    harmonize_to_reference,
    read_phase_series,
)
from dtwin.learning.raw_dicom_phase_resolver import resolve_raw_dicom_phases

LINHAS = COLUNAS = 32
FATIAS = 8
ESPACAMENTO_XY = 1.0
ESPACAMENTO_Z = 2.0


def _serie_mr_com_pixels(
    destino,
    *,
    study_uid: str,
    numero: int,
    descricao: str,
    hora: str,
    origem_z: float = 0.0,
    intensidade_base: int = 100,
) -> None:
    """Escreve uma série MR multi-slice válida (com PixelData 16-bit) que o
    GDCM/SimpleITK consegue montar como volume."""
    series_uid = generate_uid()
    frame_uid = generate_uid()
    MR_IMAGE_STORAGE = "1.2.840.10008.5.1.4.1.1.4"  # SOP Class registrado (GDCM exige)
    for indice in range(FATIAS):
        meta = FileMetaDataset()
        meta.TransferSyntaxUID = ExplicitVRLittleEndian
        meta.MediaStorageSOPClassUID = MR_IMAGE_STORAGE
        meta.MediaStorageSOPInstanceUID = generate_uid()
        ds = FileDataset(None, {}, file_meta=meta, preamble=b"\0" * 128)
        ds.Modality = "MR"
        ds.PatientName = "SYNTHETIC^PHANTOM"
        ds.StudyInstanceUID = study_uid
        ds.SeriesInstanceUID = series_uid
        ds.FrameOfReferenceUID = frame_uid
        ds.SOPClassUID = meta.MediaStorageSOPClassUID
        ds.SOPInstanceUID = meta.MediaStorageSOPInstanceUID
        ds.SeriesNumber = numero
        ds.InstanceNumber = indice + 1
        ds.SeriesDescription = descricao
        ds.ProtocolName = descricao
        ds.SequenceName = "*fl3d1"
        ds.ImageType = ["ORIGINAL", "PRIMARY", "M"]
        ds.AcquisitionTime = hora
        ds.ContrastBolusAgent = "GADOLINIUM"
        ds.Rows = LINHAS
        ds.Columns = COLUNAS
        ds.PixelSpacing = [ESPACAMENTO_XY, ESPACAMENTO_XY]
        ds.SliceThickness = ESPACAMENTO_Z
        ds.SpacingBetweenSlices = ESPACAMENTO_Z
        ds.ImageOrientationPatient = [1, 0, 0, 0, 1, 0]
        ds.ImagePositionPatient = [0.0, 0.0, origem_z + indice * ESPACAMENTO_Z]
        ds.SamplesPerPixel = 1
        ds.PhotometricInterpretation = "MONOCHROME2"
        ds.BitsAllocated = 16
        ds.BitsStored = 16
        ds.HighBit = 15
        ds.PixelRepresentation = 0
        # conteúdo determinístico e distinto por fase e por fatia
        quadro = np.full(
            (LINHAS, COLUNAS), intensidade_base + indice, dtype=np.uint16
        )
        quadro[8:24, 8:24] = intensidade_base + 500  # "órgão" central
        ds.PixelData = quadro.tobytes()
        caminho = destino / f"img_{indice:03d}.dcm"
        caminho.parent.mkdir(parents=True, exist_ok=True)
        ds.save_as(str(caminho), enforce_file_format=True)


def _estudo_trifasico(raiz, *, origem_z_arterial: float = 0.0) -> None:
    estudo = generate_uid()
    _serie_mr_com_pixels(
        raiz / "serie_7", study_uid=estudo, numero=7, descricao="T1 ARTERIAL",
        hora="120100", origem_z=origem_z_arterial, intensidade_base=100,
    )
    _serie_mr_com_pixels(
        raiz / "serie_8", study_uid=estudo, numero=8, descricao="T1 PORTAL",
        hora="120145", origem_z=0.0, intensidade_base=200,
    )
    _serie_mr_com_pixels(
        raiz / "serie_9", study_uid=estudo, numero=9, descricao="T1 DELAYED",
        hora="120400", origem_z=0.0, intensidade_base=300,
    )


def test_cadeia_completa_resolver_leitura_harmonizacao(tmp_path):
    """A cadeia real: resolver materializa as 3 fases a partir do estudo bruto;
    read_phase_series monta cada série multi-slice; arterial e tardia são
    harmonizadas na grade venosa com cobertura total e intensidade preservada."""
    raw = tmp_path / "raw"
    _estudo_trifasico(raw)

    resolucao = resolve_raw_dicom_phases(raw, tmp_path / "resolved")
    assert resolucao.method == "explicit_dicom_phase_semantics"

    fases = {}
    for papel in (ARTERIAL, VENOUS, DELAYED):
        imagem = read_phase_series(resolucao.phase_dirs[papel])
        assert imagem.GetSize() == (COLUNAS, LINHAS, FATIAS), papel
        assert imagem.GetSpacing() == (ESPACAMENTO_XY, ESPACAMENTO_XY, ESPACAMENTO_Z), papel
        fases[papel] = imagem

    referencia = fases[VENOUS]
    for papel in (ARTERIAL, DELAYED):
        harmonizada, cobertura = harmonize_to_reference(fases[papel], referencia)
        assert cobertura == pytest.approx(1.0), f"{papel}: cobertura parcial inesperada"
        assert harmonizada.GetSize() == referencia.GetSize()
        assert harmonizada.GetSpacing() == referencia.GetSpacing()
        assert harmonizada.GetOrigin() == referencia.GetOrigin()
        assert harmonizada.GetDirection() == referencia.GetDirection()

    # intensidade preservada na grade idêntica: a fase tardia tem base 300 e
    # o "órgão" em 800 — a harmonização não pode deslocar nem reescalar
    tardia, _ = harmonize_to_reference(fases[DELAYED], referencia)
    arr = sitk.GetArrayFromImage(tardia)
    assert int(arr[0, 16, 16]) == 800  # dentro do "órgão", fatia 0
    assert int(arr[0, 0, 0]) == 300  # fundo, fatia 0


def test_cadeia_ordena_fatias_por_posicao_fisica_apos_o_resolver(tmp_path):
    """O eixo Z do volume montado tem de seguir a POSIÇÃO física, não o nome
    dos arquivos materializados — o conteúdo de cada fatia (base+indice)
    denuncia qualquer embaralhamento."""
    raw = tmp_path / "raw"
    _estudo_trifasico(raw)
    resolucao = resolve_raw_dicom_phases(raw, tmp_path / "resolved")

    venosa = read_phase_series(resolucao.phase_dirs[VENOUS])
    arr = sitk.GetArrayFromImage(venosa)
    fundos = [int(arr[z, 0, 0]) for z in range(FATIAS)]
    assert fundos == [200 + z for z in range(FATIAS)], (
        "fatias fora de ordem física após resolver+leitura"
    )


def test_cadeia_com_fase_fisicamente_disjunta_reprova_na_cobertura(tmp_path):
    """O resolver aceita o estudo (Rows/Columns/orientação batem — extensão
    física não é critério dele), mas a harmonização REPROVA: a arterial
    deslocada para fora do volume venoso cobre < MINIMUM_COVERAGE da grade.
    É a divisão de responsabilidade ratificada em ARGOS-GEO-002."""
    raw = tmp_path / "raw"
    deslocamento_disjunto = FATIAS * ESPACAMENTO_Z * 10  # bem longe
    _estudo_trifasico(raw, origem_z_arterial=deslocamento_disjunto)

    resolucao = resolve_raw_dicom_phases(raw, tmp_path / "resolved")
    assert resolucao.method == "explicit_dicom_phase_semantics"

    referencia = read_phase_series(resolucao.phase_dirs[VENOUS])
    arterial = read_phase_series(resolucao.phase_dirs[ARTERIAL])
    _, cobertura = harmonize_to_reference(arterial, referencia)

    assert cobertura < MINIMUM_COVERAGE, (
        f"aquisição disjunta deveria reprovar (cobertura={cobertura})"
    )
