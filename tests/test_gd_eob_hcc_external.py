from __future__ import annotations

import json
import hashlib
import zipfile
from pathlib import Path

import nibabel as nib
import numpy as np
import pytest

from dtwin.benchmark import gd_eob_hcc_external as subject
from dtwin.core import PipelineError


def _metadata() -> dict:
    return {
        "id": subject.ZENODO_RECORD_ID,
        "doi": subject.DATASET_DOI,
        "status": "published",
        "revision": 3,
        "metadata": {"license": {"id": "cc-by-4.0"}},
        "files": [
            {
                "key": subject.ARCHIVE_NAME,
                "size": subject.ARCHIVE_BYTES,
                "checksum": f"md5:{subject.ARCHIVE_MD5}",
            }
        ],
    }


def test_public_metadata_is_pinned():
    result = subject.validate_zenodo_metadata(_metadata())
    assert result["record_id"] == 18622298
    assert result["archive_bytes"] == 1_345_046_539


def test_metadata_rejects_archive_change():
    payload = _metadata()
    payload["files"][0]["size"] += 1
    with pytest.raises(PipelineError, match="tamanho"):
        subject.validate_zenodo_metadata(payload)


def test_contract_constants_freeze_hcc_endpoint_without_claiming_healthy():
    assert subject.EXPECTED_CASE_COUNT == 220
    assert subject.EXPECTED_HCC_COUNT == 164
    assert subject.EXPECTED_NON_HCC_COUNT == 56
    assert subject.EXPECTED_CENTER_COUNTS == {
        "center-1": 88,
        "center-2": 94,
        "center-3": 38,
    }


def test_case_ids_are_deterministic_and_do_not_expose_source_id():
    first = subject._case_id(1, "17")
    assert first == subject._case_id(1, "17")
    assert first != subject._case_id(2, "17")
    assert "17" not in first


def _archive_members() -> list[zipfile.ZipInfo]:
    members: list[zipfile.ZipInfo] = []
    for center, count in ((1, 88), (2, 94), (3, 38)):
        members.append(zipfile.ZipInfo(f"PHLF/Center{center}/Image/"))
        for source_id in range(1, count + 1):
            members.append(
                zipfile.ZipInfo(
                    f"PHLF/Center{center}/Image/{source_id}.nii.gz"
                )
            )
        members.append(
            zipfile.ZipInfo(
                f"PHLF/Center{center}/Center_{center}_clinicopathological data.xlsx"
            )
        )
        members.append(
            zipfile.ZipInfo(
                f"PHLF/Center{center}/Annotation_Liver tumor/1.nii.gz"
            )
        )
    return members


def test_archive_classifier_selects_only_220_images():
    images, counts = subject._classify_archive_members(_archive_members())
    assert len(images) == 220
    assert counts["protected_member_count"] == 6
    assert all("/Image/" in info.filename for info, _, _ in images)


def test_archive_classifier_rejects_missing_image():
    members = _archive_members()
    members = [
        info
        for info in members
        if info.filename != "PHLF/Center2/Image/94.nii.gz"
    ]
    with pytest.raises(PipelineError, match="Center2"):
        subject._classify_archive_members(members)


def test_archive_classifier_rejects_unclassified_payload():
    members = _archive_members()
    members.append(zipfile.ZipInfo("PHLF/Center1/diagnosis.csv"))
    with pytest.raises(PipelineError, match="não classificado"):
        subject._classify_archive_members(members)


def test_archive_classifier_rejects_path_traversal():
    members = _archive_members()
    members.append(zipfile.ZipInfo("../escape.nii.gz"))
    with pytest.raises(PipelineError, match="inseguro"):
        subject._classify_archive_members(members)


def test_nifti_metadata_accepts_valid_3d_image(tmp_path):
    path = tmp_path / "image.nii.gz"
    nib.save(nib.Nifti1Image(np.zeros((4, 5, 6), dtype=np.float32), np.eye(4)), path)
    result = subject._nifti_metadata(path)
    assert result["shape"] == [4, 5, 6]
    assert result["spacing_mm"] == [1.0, 1.0, 1.0]


def test_nifti_metadata_rejects_non_3d_image(tmp_path):
    path = tmp_path / "image.nii.gz"
    nib.save(
        nib.Nifti1Image(np.zeros((4, 5, 6, 2), dtype=np.float32), np.eye(4)),
        path,
    )
    with pytest.raises(PipelineError, match="Geometria"):
        subject._nifti_metadata(path)


def test_extract_publishes_only_images_and_keeps_protected_payloads_closed(
    monkeypatch, tmp_path
):
    source_image = tmp_path / "source.nii.gz"
    nib.save(
        nib.Nifti1Image(np.zeros((2, 2, 2), dtype=np.float32), np.eye(4)),
        source_image,
    )
    archive = tmp_path / "PHLF.zip"
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        for center, count in ((1, 88), (2, 94), (3, 38)):
            for source_id in range(1, count + 1):
                bundle.write(
                    source_image,
                    f"PHLF/Center{center}/Image/{source_id}.nii.gz",
                )
            bundle.writestr(
                f"PHLF/Center{center}/Annotation_Liver tumor/1.nii.gz",
                b"SECRET-MASK",
            )
            bundle.writestr(
                f"PHLF/Center{center}/Center_{center}_clinicopathological data.xlsx",
                b"SECRET-LABELS",
            )
    monkeypatch.setattr(subject, "ARCHIVE_BYTES", archive.stat().st_size)
    monkeypatch.setattr(
        subject,
        "ARCHIVE_MD5",
        hashlib.md5(archive.read_bytes(), usedforsecurity=False).hexdigest(),
    )
    monkeypatch.setattr(
        subject,
        "verify_hcc_hbp_contract",
        lambda **kwargs: {"contract_signature": "contract"},
    )
    output = tmp_path / "published"
    result = subject.extract_label_blind_images(
        archive_path=archive,
        contract_path=tmp_path / "contract.json",
        baseline_lock_path=tmp_path / "lock.json",
        workspace_root=tmp_path,
        output_root=output,
    )
    assert result["case_count"] == 220
    assert len(list((output / "image_only" / "images").glob("*.nii.gz"))) == 220
    assert not list(output.rglob("*tumor*"))
    assert not list(output.rglob("*.xlsx"))
    assert b"SECRET-MASK" not in (output / "protected_source" / "source_mapping.jsonl").read_bytes()
    assert b"SECRET-LABELS" not in (output / "protected_source" / "source_mapping.jsonl").read_bytes()


def test_verify_image_collection_rejects_protected_path(monkeypatch, tmp_path):
    monkeypatch.setattr(subject, "EXPECTED_CASE_COUNT", 1)
    monkeypatch.setattr(subject, "EXPECTED_CENTER_COUNTS", {"center-1": 1})
    image_root = tmp_path / "image_only"
    image_root.mkdir()
    rows = [
        {
            "schema": subject.IMAGE_CASE_SCHEMA,
            "case_id": "anon-gdeob-" + "a" * 20,
            "source_dataset_id": subject.DATASET_ID,
            "center_pseudonym": "center-1",
            "phase": "hepatobiliary_phase_gd_eob_dtpa",
            "image": {
                "relative_path": "lesion_mask.nii.gz",
                "bytes": 1,
                "sha256": "b" * 64,
            },
            "study_fingerprint_sha256": "b" * 64,
            "ground_truth_read": False,
            "lesion_masks_read": False,
            "anatomical_annotations_used": False,
        }
    ]
    (image_root / "image_cases.jsonl").write_text(
        json.dumps(rows[0]) + "\n", encoding="utf-8"
    )
    base = {
        "schema": subject.IMAGE_COLLECTION_SCHEMA,
        "contract_signature": "contract",
        "case_count": 1,
        "image_manifest_sha256": subject._sha256(image_root / "image_cases.jsonl"),
        "labels_read": False,
        "lesion_masks_read": False,
        "anatomical_annotations_used": False,
        "protected_payloads_read": False,
    }
    manifest = {**base, "collection_signature": subject._canonical_sha(base)}
    (image_root / "collection.json").write_text(
        json.dumps(manifest), encoding="utf-8"
    )
    monkeypatch.setattr(
        subject,
        "verify_hcc_hbp_contract",
        lambda **kwargs: {"contract_signature": "contract"},
    )
    with pytest.raises(PipelineError, match="inválido|inseguro"):
        subject.verify_label_blind_images(
            image_root=image_root,
            contract_path=tmp_path / "contract.json",
            baseline_lock_path=tmp_path / "lock.json",
            workspace_root=tmp_path,
        )
