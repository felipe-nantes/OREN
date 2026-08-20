from __future__ import annotations

import json
from pathlib import Path

import pydicom
import pytest
from pydicom.dataset import FileDataset, FileMetaDataset
from pydicom.uid import ExplicitVRLittleEndian, generate_uid

from dtwin.core import PipelineError
from dtwin.learning import multiphase_ingest as mi
from dtwin.learning.raw_dicom_phase_resolver import (
    ARTERIAL,
    DELAYED,
    VENOUS,
    RawPhaseResolutionError,
    resolve_raw_dicom_phases,
)


def _dicom(
    path: Path,
    *,
    study_uid: str,
    series_uid: str,
    number: int,
    description: str,
    acquisition_time: str,
    contrast: bool = True,
    frames: int = 20,
    patient_name: str = "PHI^MUST_NOT_PERSIST",
    z_position: float | None = None,
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    meta = FileMetaDataset()
    meta.TransferSyntaxUID = ExplicitVRLittleEndian
    meta.MediaStorageSOPClassUID = generate_uid()
    meta.MediaStorageSOPInstanceUID = generate_uid()
    ds = FileDataset(str(path), {}, file_meta=meta, preamble=b"\0" * 128)
    ds.Modality = "MR"
    ds.PatientName = patient_name
    ds.PatientID = "SECRET-ID"
    ds.StudyInstanceUID = study_uid
    ds.SeriesInstanceUID = series_uid
    ds.SOPInstanceUID = generate_uid()
    ds.SeriesNumber = number
    ds.InstanceNumber = number
    ds.SeriesDescription = description
    ds.ProtocolName = description
    ds.SequenceName = "*fl3d1"
    ds.ImageType = ["ORIGINAL", "PRIMARY", "M"]
    ds.AcquisitionTime = acquisition_time
    ds.NumberOfFrames = frames
    ds.Rows = 64
    ds.Columns = 64
    ds.ImageOrientationPatient = [1, 0, 0, 0, 1, 0]
    if z_position is not None:
        ds.ImagePositionPatient = [0, 0, z_position]
    if contrast:
        ds.ContrastBolusAgent = "GADOLINIUM"
    ds.save_as(str(path), enforce_file_format=True)
    return path


def _triplet(root: Path, *, study_uid: str | None = None) -> None:
    study = study_uid or generate_uid()
    for number, name, time in (
        (7, "T1 ARTERIAL", "120100"),
        (8, "T1 PORTAL", "120145"),
        (9, "T1 DELAYED", "120400"),
    ):
        _dicom(
            root / f"series_{number}" / "image.dcm",
            study_uid=study,
            series_uid=generate_uid(),
            number=number,
            description=name,
            acquisition_time=time,
        )


def test_resolves_explicit_phase_semantics_and_materializes(tmp_path):
    raw = tmp_path / "raw"
    _triplet(raw)

    result = resolve_raw_dicom_phases(raw, tmp_path / "resolved")

    assert result.method == "explicit_dicom_phase_semantics"
    assert result.confidence == 1.0
    assert set(result.phase_dirs) == {ARTERIAL, VENOUS, DELAYED}
    assert all(len(list(directory.glob("*.dcm"))) == 1 for directory in result.phase_dirs.values())


def test_resolves_numbered_postcontrast_series_by_temporal_order(tmp_path):
    raw = tmp_path / "raw"
    study = generate_uid()
    for number, time in ((9, "131235.5"), (10, "131325.8"), (11, "131410.7"), (12, "131455.8")):
        _dicom(
            raw / f"series_{number}" / "image.dcm",
            study_uid=study,
            series_uid=generate_uid(),
            number=number,
            description=f"t1_vibe_fs_tra_bh {number - 8} + c",
            acquisition_time=time,
        )

    result = resolve_raw_dicom_phases(raw, tmp_path / "resolved")
    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))

    assert result.method == "ordered_axial_t1_postcontrast_series"
    assert result.confidence == 0.8
    assert manifest["selected"][ARTERIAL]["series_number"] == 9
    assert manifest["selected"][VENOUS]["series_number"] == 10
    assert manifest["selected"][DELAYED]["series_number"] == 12


def test_ignores_subtraction_series_with_duplicate_source_times(tmp_path):
    raw = tmp_path / "raw"
    study = generate_uid()
    originals = ((11, "105916.1775"), (12, "110001.1825"), (13, "110046.1850"))
    for number, time in originals:
        _dicom(
            raw / f"series_{number}" / "image.dcm",
            study_uid=study,
            series_uid=generate_uid(),
            number=number,
            description="AX T1 VIBE FS POST",
            acquisition_time=time,
        )
        _dicom(
            raw / f"sub_{number}" / "image.dcm",
            study_uid=study,
            series_uid=generate_uid(),
            number=number + 89,
            description=f"SUB_S{number}-S9_1",
            acquisition_time=time,
        )

    result = resolve_raw_dicom_phases(raw, tmp_path / "resolved")
    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))

    assert result.method == "ordered_axial_t1_postcontrast_series"
    assert [manifest["selected"][role]["series_number"] for role in (ARTERIAL, VENOUS, DELAYED)] == [11, 12, 13]


def test_prefers_contrast_tagged_series_over_ambiguous_pre_post_labels(tmp_path):
    raw = tmp_path / "raw"
    study = generate_uid()
    for number, time, contrast in (
        (15, "102220", False), (16, "102344", False),
        (19, "102900", True), (20, "102947", True), (21, "103227", True),
    ):
        _dicom(
            raw / f"series_{number}" / "image.dcm",
            study_uid=study,
            series_uid=generate_uid(),
            number=number,
            description="t1 vibe ax fs BH pre-post",
            acquisition_time=time,
            contrast=contrast,
        )

    result = resolve_raw_dicom_phases(raw, tmp_path / "resolved")
    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    assert [manifest["selected"][role]["series_number"] for role in (ARTERIAL, VENOUS, DELAYED)] == [19, 20, 21]


def test_manifest_does_not_persist_phi_or_raw_descriptions(tmp_path):
    raw = tmp_path / "raw"
    _triplet(raw)
    result = resolve_raw_dicom_phases(raw, tmp_path / "resolved")
    payload = result.manifest_path.read_text(encoding="utf-8")

    assert "PHI^MUST_NOT_PERSIST" not in payload
    assert "SECRET-ID" not in payload
    assert "T1 ARTERIAL" not in payload
    assert json.loads(payload)["phi_persisted"] is False


def test_rejects_multiple_eligible_studies(tmp_path):
    raw = tmp_path / "raw"
    _triplet(raw / "study_a", study_uid=generate_uid())
    _triplet(raw / "study_b", study_uid=generate_uid())

    with pytest.raises(PipelineError, match="Mais de um estudo"):
        resolve_raw_dicom_phases(raw, tmp_path / "resolved")


def test_rejects_unlabeled_noncontrast_series(tmp_path):
    raw = tmp_path / "raw"
    study = generate_uid()
    for number in (1, 2, 3):
        _dicom(
            raw / f"series_{number}" / "image.dcm",
            study_uid=study,
            series_uid=generate_uid(),
            number=number,
            description="generic abdominal acquisition",
            acquisition_time=f"12{number:02d}00",
            contrast=False,
        )

    with pytest.raises(PipelineError, match="Não foi possível identificar"):
        resolve_raw_dicom_phases(raw, tmp_path / "resolved")


def test_single_series_failure_is_typed_for_safe_monophase_fallback(tmp_path):
    raw = tmp_path / "raw"
    _dicom(
        raw / "only" / "image.dcm",
        study_uid=generate_uid(),
        series_uid=generate_uid(),
        number=4,
        description="AX T1 VIBE FS POST",
        acquisition_time="120100",
    )

    with pytest.raises(RawPhaseResolutionError) as captured:
        resolve_raw_dicom_phases(raw, tmp_path / "resolved")

    assert captured.value.code == "insufficient_dynamic_phases"
    assert not (tmp_path / "resolved").exists()


def test_ambiguous_multiphase_failure_is_not_single_phase_eligible(tmp_path):
    raw = tmp_path / "raw"
    _triplet(raw / "study_a", study_uid=generate_uid())
    _triplet(raw / "study_b", study_uid=generate_uid())

    with pytest.raises(RawPhaseResolutionError) as captured:
        resolve_raw_dicom_phases(raw, tmp_path / "resolved")

    assert captured.value.code == "ambiguous_explicit_multiphase_studies"


def test_rejects_duplicate_temporal_order(tmp_path):
    raw = tmp_path / "raw"
    study = generate_uid()
    for number in (9, 10, 11):
        _dicom(
            raw / f"series_{number}" / "image.dcm",
            study_uid=study,
            series_uid=generate_uid(),
            number=number,
            description=f"t1_vibe {number} + c",
            acquisition_time="120100",
        )

    with pytest.raises(PipelineError, match="Não foi possível identificar"):
        resolve_raw_dicom_phases(raw, tmp_path / "resolved")


def test_non_mr_files_are_ignored(tmp_path):
    raw = tmp_path / "raw"
    _triplet(raw)
    path = next(raw.rglob("*.dcm"))
    ds = pydicom.dcmread(str(path))
    ds.Modality = "CT"
    ds.SeriesInstanceUID = generate_uid()
    ds.save_as(str(raw / "ct.dcm"), enforce_file_format=True)

    result = resolve_raw_dicom_phases(raw, tmp_path / "resolved")
    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    assert manifest["series_discovered"] == 3


def test_classic_slices_are_sorted_by_physical_position_not_filename(tmp_path):
    study, series = generate_uid(), generate_uid()
    high = _dicom(
        tmp_path / "1-10.dcm", study_uid=study, series_uid=series, number=10,
        description="T1 PORTAL", acquisition_time="120100", z_position=10.0,
    )
    low = _dicom(
        tmp_path / "1-2.dcm", study_uid=study, series_uid=series, number=2,
        description="T1 PORTAL", acquisition_time="120100", z_position=-2.0,
    )
    middle = _dicom(
        tmp_path / "1-1.dcm", study_uid=study, series_uid=series, number=1,
        description="T1 PORTAL", acquisition_time="120100", z_position=4.0,
    )

    ordered = mi._sort_files_spatially([high, low, middle])
    assert [Path(path).name for path in ordered] == ["1-2.dcm", "1-1.dcm", "1-10.dcm"]
