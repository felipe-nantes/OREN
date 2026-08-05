from pathlib import Path

import pydicom
from pydicom.dataset import FileDataset, FileMetaDataset
from pydicom.uid import ExplicitVRLittleEndian, MRImageStorage, generate_uid

from dtwin.benchmark.dataset_audit import (
    AUDIT_SCHEMA,
    audit_dataset_roots,
    select_best_mr_series,
    select_monophase_evidence_series,
)


def _write_series(
    directory: Path,
    *,
    description: str,
    slices: int = 20,
    echo_time: float = 2.3,
    modality: str = "MR",
    nonuniform: bool = False,
) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    series_uid = generate_uid()
    for index in range(slices):
        metadata = FileMetaDataset()
        metadata.TransferSyntaxUID = ExplicitVRLittleEndian
        metadata.MediaStorageSOPClassUID = MRImageStorage
        metadata.MediaStorageSOPInstanceUID = generate_uid()
        dataset = FileDataset(str(directory / f"slice-{index:03d}.dcm"), {}, file_meta=metadata)
        dataset.SOPClassUID = MRImageStorage
        dataset.SOPInstanceUID = metadata.MediaStorageSOPInstanceUID
        dataset.SeriesInstanceUID = series_uid
        dataset.Modality = modality
        dataset.SeriesDescription = description
        dataset.ProtocolName = description
        dataset.EchoTime = echo_time
        dataset.InstanceNumber = index + 1
        dataset.Rows = 64
        dataset.Columns = 64
        dataset.PixelSpacing = [1.5, 1.5]
        dataset.SliceThickness = 3.0
        dataset.ImageOrientationPatient = [1, 0, 0, 0, 1, 0]
        position = index * 3.0 + (1.0 if nonuniform and index == slices - 1 else 0.0)
        dataset.ImagePositionPatient = [0, 0, position]
        dataset.PatientName = "SHOULD^NEVER^BE^READ"
        dataset.PatientID = "SECRET"
        dataset.save_as(directory / f"slice-{index:03d}.dcm", enforce_file_format=True)


def test_audit_is_phi_safe_and_classifies_sequences(tmp_path: Path) -> None:
    positive = tmp_path / "positive"
    negative = tmp_path / "negative"
    _write_series(positive / "patient-visible-name", description="AX VIBE arterial post gad")
    _write_series(negative / "patient-negative", description="T2 SPIR")

    result = audit_dataset_roots({"positive": positive, "negative": negative})

    assert result["schema"] == AUDIT_SCHEMA
    assert result["contains_phi"] is False
    assert result["raw_paths_persisted"] is False
    assert result["raw_uids_persisted"] is False
    assert result["label_counts"] == {"positive": 1, "negative": 1}
    assert result["cases"][0]["case_ref"] == "pos-001"
    assert result["cases"][0]["series"][0]["sequence_class"] == "T1_ARTERIAL"
    assert result["cases"][1]["series"][0]["sequence_class"] == "T2"
    serialized = str(result)
    assert "SHOULD" not in serialized
    assert "SECRET" not in serialized
    assert "patient-visible-name" not in serialized


def test_audit_splits_shared_uid_by_echo_time(tmp_path: Path) -> None:
    positive = tmp_path / "positive"
    negative = tmp_path / "negative"
    case = positive / "case-a"
    _write_series(case / "echo-one", description="T1 dual", echo_time=2.3)
    # O helper gera outro UID; copiar o UID do primeiro arquivo simula dual-echo real.
    first = pydicom.dcmread(next((case / "echo-one").glob("*.dcm")), stop_before_pixels=True)
    _write_series(case / "echo-two", description="T1 dual", echo_time=4.6)
    for path in (case / "echo-two").glob("*.dcm"):
        dataset = pydicom.dcmread(path)
        dataset.SeriesInstanceUID = first.SeriesInstanceUID
        dataset.save_as(path, enforce_file_format=True)
    _write_series(negative / "case-b", description="T2")

    result = audit_dataset_roots({"positive": positive, "negative": negative})

    assert result["cases"][0]["series_count"] == 2
    assert {item["echo_time_ms"] for item in result["cases"][0]["series"]} == {2.3, 4.6}


def test_audit_flags_nonuniform_spacing_and_non_mr(tmp_path: Path) -> None:
    positive = tmp_path / "positive"
    negative = tmp_path / "negative"
    _write_series(positive / "case-a", description="T1 VIBE", nonuniform=True)
    _write_series(negative / "case-b", description="CT portal", modality="CT")

    result = audit_dataset_roots({"positive": positive, "negative": negative})

    positive_series = result["cases"][0]["series"][0]
    negative_series = result["cases"][1]["series"][0]
    assert positive_series["geometry"]["nonuniform_slice_spacing"] is True
    assert "nonuniform_slice_spacing" in positive_series["warnings"]
    assert negative_series["eligible_for_screening"] is False
    assert "modality_not_mr" in negative_series["warnings"]


def test_selector_prefers_clinically_useful_series_over_largest(tmp_path: Path) -> None:
    _write_series(tmp_path / "t1-unknown", description="T1 generic", slices=40)
    _write_series(tmp_path / "arterial", description="VIBE arterial post gad", slices=20)

    files, slices, metadata = select_best_mr_series(tmp_path, min_slices=3)

    assert len(files) == 20
    assert slices == 20
    assert metadata is not None
    assert metadata["selected"]["sequence_class"] == "T1_ARTERIAL"
    assert "arterial" not in str(metadata)
    assert metadata["raw_paths_persisted"] is False


def test_selector_rejects_ct_even_when_larger(tmp_path: Path) -> None:
    _write_series(tmp_path / "ct", description="CT portal", slices=40, modality="CT")
    _write_series(tmp_path / "mr", description="T2 SPIR", slices=10, modality="MR")

    files, slices, metadata = select_best_mr_series(tmp_path, min_slices=3)

    assert len(files) == 10
    assert slices == 10
    assert metadata is not None
    assert metadata["selected"]["modality"] == "MR"


def test_monophase_evidence_selector_preserves_complementary_real_sequences(tmp_path: Path) -> None:
    _write_series(tmp_path / "arterial", description="VIBE arterial post gad", slices=24)
    _write_series(tmp_path / "t2-low", description="T2 HASTE", slices=18)
    _write_series(tmp_path / "t2-high", description="T2 HASTE", slices=28)
    _write_series(tmp_path / "dwi", description="DWI b800", slices=22)
    _write_series(tmp_path / "adc", description="ADC map", slices=22)

    paths, metadata = select_monophase_evidence_series(tmp_path, min_slices=3)

    assert metadata is not None
    assert metadata["primary_sequence_class"] == "T1_ARTERIAL"
    assert metadata["complementary_sequence_classes"] == ["T2", "DWI", "ADC"]
    assert metadata["selected_sequence_classes"] == ["ADC", "DWI", "T1_ARTERIAL", "T2"]
    assert len(paths["T2"]) == 28  # one deterministic best series, not both T2 series
    assert metadata["synthetic_phases_created"] is False
    assert metadata["raw_paths_persisted"] is False
    assert "t2-high" not in str(metadata)


def test_monophase_evidence_selector_returns_no_series_for_ct_only(tmp_path: Path) -> None:
    _write_series(tmp_path / "ct", description="CT portal", slices=40, modality="CT")
    paths, metadata = select_monophase_evidence_series(tmp_path, min_slices=3)
    assert paths == {}
    assert metadata is None
