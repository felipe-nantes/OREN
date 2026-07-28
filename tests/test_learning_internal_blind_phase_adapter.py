from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from pydicom.dataset import FileDataset, FileMetaDataset
from pydicom.uid import ExplicitVRLittleEndian, MRImageStorage, generate_uid

from dtwin.core import PipelineError
from dtwin.learning.internal_blind_phase_adapter import (
    resolve_authorized_blind_phase_folders,
    summarize_authorized_blind_phase_eligibility,
)
from dtwin.learning.multiphase_ingest import ARTERIAL, DELAYED, VENOUS


CASE_ID = "ARGOS-BLIND-0001"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_dicom(path: Path, *, case_id: str, series_number: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    file_meta = FileMetaDataset()
    file_meta.TransferSyntaxUID = ExplicitVRLittleEndian
    file_meta.MediaStorageSOPClassUID = MRImageStorage
    file_meta.MediaStorageSOPInstanceUID = generate_uid()
    dataset = FileDataset(str(path), {}, file_meta=file_meta, preamble=b"\0" * 128)
    dataset.SOPClassUID = MRImageStorage
    dataset.SOPInstanceUID = file_meta.MediaStorageSOPInstanceUID
    dataset.PatientID = case_id
    dataset.Modality = "MR"
    dataset.SeriesNumber = series_number
    dataset.save_as(str(path), enforce_file_format=True)


def _fixture(
    root: Path,
    *,
    include_delayed: bool = True,
    duplicate_arterial: bool = False,
) -> tuple[Path, Path]:
    case_dir = root / "upload" / CASE_ID
    rows = []
    definitions = [
        (1, "t1_arterial"),
        (2, "t1_venous"),
    ]
    if include_delayed:
        definitions.append((3, "t1_delayed"))
    if duplicate_arterial:
        definitions.append((4, "t1_arterial_ttc_1"))
    for number, role in definitions:
        dicom = case_dir / f"series_{number:03d}" / "volume.dcm"
        _write_dicom(dicom, case_id=CASE_ID, series_number=number)
        rows.append(
            {
                "blind_case_id": CASE_ID,
                "series_number": number,
                "role_private": role,
                "source_path_private": f"C:/private/patient/{role}.nii.gz",
                "source_sha256": "0" * 64,
                "output_sha256": _sha256(dicom),
                "conversion": "nifti_to_deidentified_enhanced_mr_multiframe",
            }
        )
    audit = root / "private_reference" / "conversion_audit.json"
    audit.parent.mkdir(parents=True)
    audit.write_text(json.dumps(rows), encoding="utf-8")
    return case_dir.parent, audit


def test_resolver_maps_opaque_series_and_returns_safe_provenance(tmp_path):
    # The extra CASE_ID wrapper reproduces the directory shape preserved by the
    # current webapp upload endpoint.
    upload_root, audit = _fixture(tmp_path)
    result = resolve_authorized_blind_phase_folders(
        case_id=CASE_ID,
        case_dir=upload_root,
        audit_path=audit,
    )

    assert set(result.phase_dirs) == {ARTERIAL, VENOUS, DELAYED}
    assert result.phase_dirs[ARTERIAL].name == "series_001"
    assert result.phase_dirs[VENOUS].name == "series_002"
    assert result.phase_dirs[DELAYED].name == "series_003"

    safe = result.safe_manifest()
    serialized = json.dumps(safe)
    assert safe["labels_read"] is False
    assert safe["lesion_masks_read"] == 0
    assert safe["private_paths_persisted"] is False
    assert "C:/private" not in serialized
    assert "source_path_private" not in serialized


def test_resolver_fails_closed_when_required_phase_is_missing(tmp_path):
    upload_root, audit = _fixture(tmp_path, include_delayed=False)
    with pytest.raises(PipelineError, match="sem fase obrigatória"):
        resolve_authorized_blind_phase_folders(
            case_id=CASE_ID,
            case_dir=upload_root,
            audit_path=audit,
        )


def test_resolver_fails_closed_on_ambiguous_arterial_phase(tmp_path):
    upload_root, audit = _fixture(tmp_path, duplicate_arterial=True)
    with pytest.raises(PipelineError, match="ambígua"):
        resolve_authorized_blind_phase_folders(
            case_id=CASE_ID,
            case_dir=upload_root,
            audit_path=audit,
        )


def test_resolver_rejects_hash_mismatch(tmp_path):
    upload_root, audit = _fixture(tmp_path)
    dicom = upload_root / CASE_ID / "series_001" / "volume.dcm"
    dicom.write_bytes(dicom.read_bytes() + b"tampered")
    with pytest.raises(PipelineError, match="Hash"):
        resolve_authorized_blind_phase_folders(
            case_id=CASE_ID,
            case_dir=upload_root,
            audit_path=audit,
        )


def test_resolver_rejects_additional_unauthenticated_dicom(tmp_path):
    upload_root, audit = _fixture(tmp_path)
    extra = upload_root / CASE_ID / "series_001" / "extra.dcm"
    _write_dicom(extra, case_id=CASE_ID, series_number=1)
    with pytest.raises(PipelineError, match="adicional não autenticado"):
        resolve_authorized_blind_phase_folders(
            case_id=CASE_ID,
            case_dir=upload_root,
            audit_path=audit,
        )


def test_resolver_rejects_dicom_identity_mismatch_even_with_matching_hash(tmp_path):
    upload_root, audit = _fixture(tmp_path)
    dicom = upload_root / CASE_ID / "series_002" / "volume.dcm"
    _write_dicom(dicom, case_id="ARGOS-BLIND-9999", series_number=2)
    rows = json.loads(audit.read_text(encoding="utf-8"))
    for row in rows:
        if row["series_number"] == 2:
            row["output_sha256"] = _sha256(dicom)
    audit.write_text(json.dumps(rows), encoding="utf-8")
    with pytest.raises(PipelineError, match="Identificador DICOM"):
        resolve_authorized_blind_phase_folders(
            case_id=CASE_ID,
            case_dir=upload_root,
            audit_path=audit,
        )


def test_resolver_rejects_non_authorized_case_identifier(tmp_path):
    _upload_root, audit = _fixture(tmp_path)
    with pytest.raises(PipelineError, match="não pertence"):
        resolve_authorized_blind_phase_folders(
            case_id="../../private",
            case_dir=tmp_path,
            audit_path=audit,
        )


def test_eligibility_preflight_is_label_free_and_separates_incomplete_cases(
    tmp_path
):
    _upload_root, audit = _fixture(tmp_path)
    rows = json.loads(audit.read_text(encoding="utf-8"))
    second = "ARGOS-BLIND-0002"
    rows.append(
        {
            "blind_case_id": second,
            "series_number": 1,
            "role_private": "t2_blade",
            "source_path_private": "C:/private/second/t2.nii.gz",
            "output_sha256": "1" * 64,
        }
    )
    audit.write_text(json.dumps(rows), encoding="utf-8")

    report = summarize_authorized_blind_phase_eligibility(audit)
    assert report["case_count"] == 2
    assert report["eligible_case_ids"] == [CASE_ID]
    assert report["ineligible_count"] == 1
    assert report["ineligible_cases"][0]["case_id"] == second
    assert report["labels_read"] is False
    assert "source_path_private" not in json.dumps(report)
