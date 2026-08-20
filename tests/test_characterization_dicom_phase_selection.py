"""Characterization: seleção de fases em DICOM bruto (PHASE_03, OBSERVED_BEHAVIOR).

Complementa tests/test_raw_dicom_phase_resolver.py fixando heurísticas de
seleção ainda não protegidas. NÃO afirma que a heurística é a clinicamente
correta: escolher heurística de fase é decisão humana sob HG-02. Se algum
destes testes quebrar, a regra de seleção de série/fase mudou — pare e
consulte .fable/HUMAN_GATES.md (HG-02) e o contrato ARGOS-GEO-001.

Todas as fixtures são DICOM sintéticos gerados em tmp_path; nenhum dado de
paciente é lido ou persistido.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydicom.dataset import FileDataset, FileMetaDataset
from pydicom.uid import ExplicitVRLittleEndian, generate_uid

from dtwin.learning.raw_dicom_phase_resolver import (
    ARTERIAL,
    DELAYED,
    VENOUS,
    RawPhaseResolutionError,
    resolve_raw_dicom_phases,
)

AXIAL = [1, 0, 0, 0, 1, 0]
SAGITAL = [0, 1, 0, 0, 0, 1]


def _dicom(
    path: Path,
    *,
    study_uid: str,
    number: int,
    description: str,
    acquisition_time: str,
    frames: int = 20,
    rows: int = 64,
    orientation: list[int] | None = None,
    contrast: bool = True,
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    meta = FileMetaDataset()
    meta.TransferSyntaxUID = ExplicitVRLittleEndian
    meta.MediaStorageSOPClassUID = generate_uid()
    meta.MediaStorageSOPInstanceUID = generate_uid()
    ds = FileDataset(str(path), {}, file_meta=meta, preamble=b"\0" * 128)
    ds.Modality = "MR"
    ds.PatientName = "SYNTHETIC^PHANTOM"
    ds.StudyInstanceUID = study_uid
    ds.SeriesInstanceUID = generate_uid()
    ds.SOPInstanceUID = generate_uid()
    ds.SeriesNumber = number
    ds.InstanceNumber = number
    ds.SeriesDescription = description
    ds.ProtocolName = description
    ds.SequenceName = "*fl3d1"
    ds.ImageType = ["ORIGINAL", "PRIMARY", "M"]
    ds.AcquisitionTime = acquisition_time
    ds.NumberOfFrames = frames
    ds.Rows = rows
    ds.Columns = 64
    ds.ImageOrientationPatient = list(orientation or AXIAL)
    if contrast:
        ds.ContrastBolusAgent = "GADOLINIUM"
    ds.save_as(str(path), enforce_file_format=True)
    return path


def _manifest(resultado) -> dict:
    return json.loads(Path(resultado.manifest_path).read_text(encoding="utf-8"))


def test_observed_rotulo_com_dois_papeis_nao_e_confiavel_e_cai_para_ordem_temporal(tmp_path):
    """OBSERVED_BEHAVIOR: uma série cujo texto casa com DOIS papéis (arterial e
    venoso) é tratada como NÃO rotulada. O estudo então resolve pelo caminho
    temporal, e essa mesma série acaba recebendo ARTERIAL por ser a mais
    precoce — o rótulo ambíguo não é honrado, mas também não interrompe."""
    raw, estudo = tmp_path / "raw", generate_uid()
    for numero, descricao, hora in (
        (7, "T1 ARTERIAL AND PORTAL VENOUS", "120100"),
        (8, "T1 PORTAL", "120145"),
        (9, "T1 DELAYED", "120400"),
    ):
        _dicom(raw / f"serie_{numero}" / "img.dcm", study_uid=estudo,
               number=numero, description=descricao, acquisition_time=hora)

    resultado = resolve_raw_dicom_phases(raw, tmp_path / "resolved")

    assert resultado.method == "ordered_axial_t1_postcontrast_series"
    assert resultado.confidence == 0.8
    manifesto = _manifest(resultado)
    selecionado = manifesto["selected"]
    assert selecionado[ARTERIAL]["series_number"] == 7
    # HG-02 item 14 (2026-08-20): a colisao original agora e auditavel — a
    # serie que casou com dois papeis carrega o registro no manifesto.
    assert manifesto["series_with_ambiguous_text_roles"] == 1
    assert selecionado[ARTERIAL]["ambiguous_text_roles"] == [ARTERIAL, VENOUS]


def test_observed_nome_da_pasta_sozinho_determina_o_papel_explicito(tmp_path):
    """OBSERVED_BEHAVIOR: o nome da pasta entra no texto normalizado; pastas
    arterial/venous/delayed resolvem por semântica explícita mesmo quando a
    SeriesDescription é genérica."""
    raw, estudo = tmp_path / "raw", generate_uid()
    for numero, pasta, hora in (
        (7, "arterial", "120100"),
        (8, "venous", "120145"),
        (9, "delayed", "120400"),
    ):
        _dicom(raw / pasta / "img.dcm", study_uid=estudo, number=numero,
               description="T1 VIBE FS", acquisition_time=hora)

    resultado = resolve_raw_dicom_phases(raw, tmp_path / "resolved")

    assert resultado.method == "explicit_dicom_phase_semantics"
    assert resultado.confidence == 1.0


def test_geometria_incompativel_tem_codigo_de_erro_proprio(tmp_path):
    """Correção deliberada (2026-08-18, HG-02 diagnóstico — não muda seleção):
    com Rows divergente entre as fases, o gate de geometria reprova o estudo
    e o erro emitido é `geometry_incompatible_series`, distinto do genérico
    `insufficient_dynamic_phases` — a causa real fica visível para triagem."""
    raw, estudo = tmp_path / "raw", generate_uid()
    for numero, descricao, hora, linhas in (
        (7, "T1 ARTERIAL", "120100", 64),
        (8, "T1 PORTAL", "120145", 64),
        (9, "T1 DELAYED", "120400", 128),
    ):
        _dicom(raw / f"serie_{numero}" / "img.dcm", study_uid=estudo, number=numero,
               description=descricao, acquisition_time=hora, rows=linhas)

    with pytest.raises(RawPhaseResolutionError) as excecao:
        resolve_raw_dicom_phases(raw, tmp_path / "resolved")
    assert excecao.value.code == "geometry_incompatible_series"


def test_observed_series_sagitais_nao_sao_elegiveis(tmp_path):
    raw, estudo = tmp_path / "raw", generate_uid()
    for numero, descricao, hora in (
        (7, "T1 ARTERIAL", "120100"),
        (8, "T1 PORTAL", "120145"),
        (9, "T1 DELAYED", "120400"),
    ):
        _dicom(raw / f"serie_{numero}" / "img.dcm", study_uid=estudo, number=numero,
               description=descricao, acquisition_time=hora, orientation=SAGITAL)

    with pytest.raises(RawPhaseResolutionError) as excecao:
        resolve_raw_dicom_phases(raw, tmp_path / "resolved")
    assert excecao.value.code == "insufficient_dynamic_phases"


def test_observed_serie_com_menos_de_tres_frames_nao_e_elegivel(tmp_path):
    """OBSERVED_BEHAVIOR: o piso de 3 frames elimina a série, e o estudo inteiro
    deixa de resolver — falha fechada, sem cair para duas fases."""
    raw, estudo = tmp_path / "raw", generate_uid()
    for numero, descricao, hora, quadros in (
        (7, "T1 ARTERIAL", "120100", 20),
        (8, "T1 PORTAL", "120145", 20),
        (9, "T1 DELAYED", "120400", 2),
    ):
        _dicom(raw / f"serie_{numero}" / "img.dcm", study_uid=estudo, number=numero,
               description=descricao, acquisition_time=hora, frames=quadros)

    with pytest.raises(RawPhaseResolutionError) as excecao:
        resolve_raw_dicom_phases(raw, tmp_path / "resolved")
    assert excecao.value.code == "insufficient_dynamic_phases"


def test_observed_com_quatro_dinamicas_a_fase_do_meio_e_descartada(tmp_path):
    """OBSERVED_BEHAVIOR: no caminho temporal a seleção é primeira/segunda/ÚLTIMA.
    Com quatro séries dinâmicas, a terceira não é usada — e, desde o HG-02
    item 14, o descarte fica registrado no manifesto."""
    raw, estudo = tmp_path / "raw", generate_uid()
    for numero, hora in ((7, "120100"), (8, "120145"), (9, "120300"), (10, "120400")):
        _dicom(raw / f"serie_{numero}" / "img.dcm", study_uid=estudo, number=numero,
               description="T1 VIBE FS POST", acquisition_time=hora)

    resultado = resolve_raw_dicom_phases(raw, tmp_path / "resolved")

    assert resultado.method == "ordered_axial_t1_postcontrast_series"
    selecionado = _manifest(resultado)["selected"]
    assert selecionado[ARTERIAL]["series_number"] == 7
    assert selecionado[VENOUS]["series_number"] == 8
    assert selecionado[DELAYED]["series_number"] == 10
    # HG-02 item 14 (2026-08-20): o descarte deixou de ser silencioso — a
    # intermediaria (serie 9) fica listada no manifesto.
    descartadas = _manifest(resultado)["unselected_eligible_dynamic_series"]
    assert [item["series_number"] for item in descartadas] == [9]


def test_observed_series_in_phase_e_opposed_sao_ignoradas_mesmo_com_rotulo_de_fase(tmp_path):
    """OBSERVED_BEHAVIOR: o vocabulário de exclusão vence o rótulo de fase. Sem
    ele, "T1 ARTERIAL IN PHASE" daria dois candidatos arteriais e o estudo
    ficaria ambíguo; com ele, a resolução explícita permanece intacta."""
    raw, estudo = tmp_path / "raw", generate_uid()
    for numero, descricao, hora in (
        (7, "T1 ARTERIAL", "120100"),
        (8, "T1 PORTAL", "120145"),
        (9, "T1 DELAYED", "120400"),
        (11, "T1 ARTERIAL IN PHASE", "120100"),
        (12, "T1 PORTAL OPPOSED", "120145"),
    ):
        _dicom(raw / f"serie_{numero}" / "img.dcm", study_uid=estudo, number=numero,
               description=descricao, acquisition_time=hora)

    resultado = resolve_raw_dicom_phases(raw, tmp_path / "resolved")

    assert resultado.method == "explicit_dicom_phase_semantics"
    selecionado = _manifest(resultado)["selected"]
    assert selecionado[ARTERIAL]["series_number"] == 7
    assert selecionado[VENOUS]["series_number"] == 8
    assert selecionado[DELAYED]["series_number"] == 9
