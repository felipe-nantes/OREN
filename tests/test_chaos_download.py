import hashlib
import io
import json
import zipfile
from contextlib import contextmanager
from pathlib import Path

import pytest

from dtwin.core import PipelineError
from dtwin.datasets.chaos_download import (
    EXTRACTION_SCHEMA,
    MANIFEST_SCHEMA,
    ChaosDownloadSpec,
    download_chaos_train,
    extract_chaos_mri_train,
    verify_chaos_train_archive,
    verify_chaos_mri_extraction,
)


def _archive_bytes() -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr("Train_Sets/MR/1/T1DUAL/DICOM_anon/InPhase/1.dcm", b"t1")
        archive.writestr("Train_Sets/MR/1/T2SPIR/DICOM_anon/1.dcm", b"t2")
    return output.getvalue()


def _spec(payload: bytes) -> ChaosDownloadSpec:
    return ChaosDownloadSpec(
        filename="CHAOS_Train_Sets.zip",
        url="https://example.invalid/train.zip",
        size_bytes=len(payload),
        md5=hashlib.md5(payload).hexdigest(),  # noqa: S324 - publisher checksum contract
        record_id="test",
        version="test",
    )


def test_download_refuses_before_network_without_explicit_license(tmp_path: Path):
    called = False

    @contextmanager
    def opener(_url):
        nonlocal called
        called = True
        yield io.BytesIO(b"forbidden")

    with pytest.raises(PipelineError, match="nao foram aceitos"):
        download_chaos_train(
            output_dir=tmp_path / "chaos", accept_license=False,
            accepted_by="jm", spec=_spec(_archive_bytes()), opener=opener,
        )
    assert called is False
    assert not (tmp_path / "chaos").exists()


def test_download_is_atomic_verified_and_records_license(tmp_path: Path):
    payload = _archive_bytes()

    @contextmanager
    def opener(url):
        assert url == "https://example.invalid/train.zip"
        yield io.BytesIO(payload)

    result = download_chaos_train(
        output_dir=tmp_path / "chaos", accept_license=True,
        accepted_by="jm", spec=_spec(payload), opener=opener,
    )
    assert result["schema"] == MANIFEST_SCHEMA
    assert result["license_accepted"] is True
    assert result["test_set_downloaded"] is False
    assert result["contains_t1dual"] is True
    assert result["contains_t2spir"] is True
    manifest = json.loads((tmp_path / "chaos/download_manifest.json").read_text())
    assert manifest["sha256"] == hashlib.sha256(payload).hexdigest()
    assert (tmp_path / "chaos/CHAOS_Train_Sets.zip").read_bytes() == payload
    assert not list(tmp_path.glob("._chaos_*"))


def test_verifier_rejects_checksum_and_unsafe_layout(tmp_path: Path):
    payload = _archive_bytes()
    archive = tmp_path / "CHAOS_Train_Sets.zip"
    archive.write_bytes(payload)
    bad_checksum = ChaosDownloadSpec(
        filename=archive.name, url="x", size_bytes=len(payload), md5="0" * 32,
    )
    with pytest.raises(PipelineError, match="MD5"):
        verify_chaos_train_archive(archive, spec=bad_checksum)

    unsafe = io.BytesIO()
    with zipfile.ZipFile(unsafe, "w") as package:
        package.writestr("../MR/T1DUAL/T2SPIR/file.dcm", b"x")
    unsafe_payload = unsafe.getvalue()
    archive.write_bytes(unsafe_payload)
    with pytest.raises(PipelineError, match="caminho inseguro"):
        verify_chaos_train_archive(archive, spec=_spec(unsafe_payload))


def test_download_failure_cleans_staging(tmp_path: Path):
    payload = _archive_bytes()

    @contextmanager
    def opener(_url):
        yield io.BytesIO(payload[:-1])

    with pytest.raises(PipelineError, match="Tamanho"):
        download_chaos_train(
            output_dir=tmp_path / "chaos", accept_license=True,
            accepted_by="jm", spec=_spec(payload), opener=opener,
        )
    assert not (tmp_path / "chaos").exists()
    assert not list(tmp_path.glob("._chaos_*"))


def test_extracts_only_mri_and_publishes_tree_manifest(tmp_path: Path):
    payload = _archive_bytes()

    @contextmanager
    def opener(_url):
        yield io.BytesIO(payload)

    download_chaos_train(
        output_dir=tmp_path / "download", accept_license=True,
        accepted_by="jm", spec=_spec(payload), opener=opener,
    )
    result = extract_chaos_mri_train(
        download_root=tmp_path / "download", output_dir=tmp_path / "raw",
        spec=_spec(payload), expected_subject_count=1,
    )
    assert result["schema"] == EXTRACTION_SCHEMA
    assert result["subject_ids"] == ["1"]
    assert result["ct_extracted"] is False
    assert result["lesion_masks_present"] is False
    assert (tmp_path / "raw/Train_Sets/MR/1/T1DUAL/DICOM_anon/InPhase/1.dcm").is_file()
    assert not (tmp_path / "raw/Train_Sets/CT").exists()
    assert not list(tmp_path.glob("._chaos_mri_*"))


def test_extraction_rejects_tampered_download_manifest(tmp_path: Path):
    payload = _archive_bytes()

    @contextmanager
    def opener(_url):
        yield io.BytesIO(payload)

    download_chaos_train(
        output_dir=tmp_path / "download", accept_license=True,
        accepted_by="jm", spec=_spec(payload), opener=opener,
    )
    manifest_path = tmp_path / "download/download_manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["test_set_downloaded"] = True
    manifest_path.write_text(json.dumps(manifest))
    with pytest.raises(PipelineError, match="diverge"):
        extract_chaos_mri_train(
            download_root=tmp_path / "download", output_dir=tmp_path / "raw",
            spec=_spec(payload), expected_subject_count=1,
        )
    assert not (tmp_path / "raw").exists()


def test_extraction_preflight_rehashes_masks_and_dicoms(tmp_path: Path):
    payload = _archive_bytes()

    @contextmanager
    def opener(_url):
        yield io.BytesIO(payload)

    download_chaos_train(
        output_dir=tmp_path / "download", accept_license=True,
        accepted_by="jm", spec=_spec(payload), opener=opener,
    )
    extract_chaos_mri_train(
        download_root=tmp_path / "download", output_dir=tmp_path / "raw",
        spec=_spec(payload), expected_subject_count=1,
    )
    result = verify_chaos_mri_extraction(extracted_root=tmp_path / "raw", expected_subject_count=1)
    assert result["status"] == "verified_for_blind_preparation"

    target = tmp_path / "raw/Train_Sets/MR/1/T1DUAL/DICOM_anon/InPhase/1.dcm"
    target.write_bytes(b"changed")
    with pytest.raises(PipelineError, match="alterada"):
        verify_chaos_mri_extraction(extracted_root=tmp_path / "raw", expected_subject_count=1)
