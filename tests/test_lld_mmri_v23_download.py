import json
from pathlib import Path

import pytest

from dtwin.benchmark.lld_mmri_v23_download import (
    download_lld_mmri_v23_images,
    select_subject_image_files,
    validate_lld_mmri_v23_download,
)
from dtwin.benchmark.lld_mmri_v23_external import (
    MAPPING_SCHEMA,
    PROTOCOL_SCHEMA,
    REPO_ID,
    REPO_REVISION,
)
from dtwin.benchmark.openswisshcc_v20_fusion import _canonical_sha
from dtwin.core import PipelineError, sha256_of


def _files(subject="MR-123"):
    suffixes = ["C+A", "C+Delay", "C+V", "C-pre", "DWI", "InPhase", "OutPhase", "T2WI"]
    return [f"images/{subject}_1_{suffix}_0000.nii.gz" for suffix in suffixes]


def test_selects_exactly_eight_images_and_no_labels():
    files = _files() + ["labels/MR-123_1_C+A.nii.gz"]
    selected = select_subject_image_files("MR-123", files)
    assert len(selected) == 8
    assert all(path.startswith("images/") for path in selected.values())


def test_missing_phase_fails_closed():
    with pytest.raises(PipelineError, match="imagem unica"):
        select_subject_image_files("MR-123", _files()[:-1])


def test_duplicate_phase_fails_closed():
    files = _files() + ["images/MR-123_2_C+A_0000.nii.gz"]
    with pytest.raises(PipelineError, match="imagem unica"):
        select_subject_image_files("MR-123", files)


def _protocol(tmp_path: Path, *, cases: int = 2) -> Path:
    root = tmp_path / "protocol"
    mapping_path = root / "protected_source" / "mapping.jsonl"
    mapping_path.parent.mkdir(parents=True)
    case_ids = [f"anon-lld-{index:016d}" for index in range(cases)]
    mappings = [
        {
            "schema": MAPPING_SCHEMA,
            "case_id": case_id,
            "source_subject_id": f"MR-{index:03d}",
            "lesion_masks_allowed_in_inference": False,
            "raw_uids_persisted": False,
        }
        for index, case_id in enumerate(case_ids)
    ]
    mapping_path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in mappings),
        encoding="utf-8",
    )
    base = {
        "schema": PROTOCOL_SCHEMA,
        "status": "frozen_before_external_images_and_predictions",
        "dataset_repo_id": REPO_ID,
        "dataset_revision": REPO_REVISION,
        "case_count": cases,
        "case_ids": case_ids,
        "protected_mapping_sha256": sha256_of(mapping_path),
        "lesion_masks_allowed_in_inference": False,
    }
    protocol = dict(base)
    protocol["protocol_signature"] = _canonical_sha(base)
    (root / "protocol.json").write_text(json.dumps(protocol), encoding="utf-8")
    return root


def test_download_requires_explicit_license_acceptance(tmp_path: Path):
    root = _protocol(tmp_path, cases=1)
    with pytest.raises(PipelineError, match="aceite explicito"):
        download_lld_mmri_v23_images(
            protocol_root=root,
            destination=tmp_path / "download",
            accept_license=False,
            repo_files=_files("MR-000"),
            downloader=lambda **_: "unused",
        )


def test_download_and_verify_complete_image_only_manifest(tmp_path: Path):
    root = _protocol(tmp_path)
    destination = tmp_path / "download"
    repo_files = _files("MR-000") + _files("MR-001")

    def downloader(**kwargs):
        path = destination / kwargs["filename"]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes((kwargs["filename"] + "\n").encode())
        return str(path)

    result = download_lld_mmri_v23_images(
        protocol_root=root,
        destination=destination,
        accept_license=True,
        repo_files=repo_files + ["labels/MR-000_1_C+A.nii.gz"],
        downloader=downloader,
        workers=2,
    )
    assert result["case_count"] == 2
    assert result["image_count"] == 16
    assert result["labels_downloaded"] is False
    assert result["download_workers"] == 2
    assert not (destination / "labels").exists()
    assert validate_lld_mmri_v23_download(
        protocol_root=root, destination=destination
    ) == result


def test_verifier_rejects_tampered_image(tmp_path: Path):
    root = _protocol(tmp_path, cases=1)
    destination = tmp_path / "download"

    def downloader(**kwargs):
        path = destination / kwargs["filename"]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"image")
        return str(path)

    result = download_lld_mmri_v23_images(
        protocol_root=root,
        destination=destination,
        accept_license=True,
        repo_files=_files("MR-000"),
        downloader=downloader,
    )
    first = next(iter(result["cases"][0]["images"].values()))
    (destination / first["relative_path"]).write_bytes(b"tampered")
    with pytest.raises(PipelineError, match="adulterada"):
        validate_lld_mmri_v23_download(protocol_root=root, destination=destination)


def test_parallel_download_preserves_frozen_case_order(tmp_path: Path):
    root = _protocol(tmp_path, cases=3)
    destination = tmp_path / "download"
    repo_files = _files("MR-000") + _files("MR-001") + _files("MR-002")

    def downloader(**kwargs):
        path = destination / kwargs["filename"]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(kwargs["filename"].encode())
        return str(path)

    result = download_lld_mmri_v23_images(
        protocol_root=root,
        destination=destination,
        accept_license=True,
        repo_files=repo_files,
        downloader=downloader,
        workers=3,
    )
    assert [case["case_id"] for case in result["cases"]] == [
        f"anon-lld-{index:016d}" for index in range(3)
    ]


@pytest.mark.parametrize("workers", [0, 17, True])
def test_download_rejects_unsafe_worker_count(tmp_path: Path, workers):
    root = _protocol(tmp_path, cases=1)
    with pytest.raises(PipelineError, match="workers"):
        download_lld_mmri_v23_images(
            protocol_root=root,
            destination=tmp_path / "download",
            accept_license=True,
            repo_files=_files("MR-000"),
            downloader=lambda **_: "unused",
            workers=workers,
        )
