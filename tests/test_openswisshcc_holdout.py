import hashlib
import inspect
import json
from pathlib import Path
from zipfile import ZipFile

import pytest

from dtwin.benchmark import openswisshcc_holdout as module
from dtwin.core import PipelineError


def _write_archive(path: Path, subjects: set[str]) -> str:
    with ZipFile(path, "w") as zf:
        for subject in sorted(subjects):
            for phase in ["native", "arterial-TTC-1", "venous", "delayed"]:
                zf.writestr(
                    f"{subject}/dyn/{subject}_acq-water_phase-{phase}_T1w.nii.gz",
                    f"{subject}:{phase}".encode(),
                )
            zf.writestr(f"{subject}/anat/{subject}_acq-haste_T2w.nii.gz", b"t2")
            zf.writestr(f"{subject}/dwi/{subject}_desc-ADC_dwi.nii.gz", b"adc")
            zf.writestr(f"{subject}/metadata.json", b'{"diagnosis":"must not copy"}')
    return hashlib.md5(path.read_bytes(), usedforsecurity=False).hexdigest()


def _write_masks(root: Path, subjects: set[str]) -> None:
    for subject in subjects:
        folder = root / subject / "dyn"
        folder.mkdir(parents=True)
        for phase in ["native", "arterial-TTC-1", "venous", "delayed"]:
            (folder / f"{subject}_acq-water_phase-{phase}_T1w-liver_seg.nii.gz").write_bytes(
                f"mask:{subject}:{phase}".encode()
            )


def _configure(monkeypatch, archive: Path, subjects: set[str], md5: str) -> None:
    monkeypatch.setattr(module, "HOLDOUT_SUBJECTS", frozenset(subjects))
    monkeypatch.setattr(
        module,
        "HOLDOUT_ARCHIVE",
        {"name": archive.name, "md5": md5, "subjects": frozenset(subjects)},
    )


def test_holdout_api_cannot_accept_participants_or_labels():
    parameters = inspect.signature(module.prepare_holdout_dataset_label_blind).parameters
    assert set(parameters) == {"archive", "allowed_derivatives_dir", "output_dir"}
    source = inspect.getsource(module.prepare_holdout_dataset_label_blind).lower()
    assert "participants.tsv" not in source
    assert "load_subject_labels" not in source


def test_archive_rejects_subject_outside_holdout(tmp_path, monkeypatch):
    archive = tmp_path / "sub-044-sub-088.zip"
    md5 = _write_archive(archive, {"sub-044", "sub-045"})
    _configure(monkeypatch, archive, {"sub-045"}, md5)
    with pytest.raises(PipelineError, match="fora de 045–088"):
        module.inspect_holdout_archive(archive)


def test_archive_rejects_unsafe_member(tmp_path, monkeypatch):
    archive = tmp_path / "sub-044-sub-088.zip"
    with ZipFile(archive, "w") as zf:
        zf.writestr("../sub-045/dyn/x.nii.gz", b"bad")
    md5 = hashlib.md5(archive.read_bytes(), usedforsecurity=False).hexdigest()
    _configure(monkeypatch, archive, {"sub-045"}, md5)
    with pytest.raises(PipelineError, match="inseguro"):
        module.inspect_holdout_archive(archive)


def test_label_blind_preparation_copies_only_images_and_automatic_liver_masks(
    tmp_path, monkeypatch
):
    subjects = {"sub-045", "sub-088"}
    archive = tmp_path / "sub-044-sub-088.zip"
    md5 = _write_archive(archive, subjects)
    _configure(monkeypatch, archive, subjects, md5)
    masks = tmp_path / "allowed"
    _write_masks(masks, subjects)
    output = tmp_path / "prepared_holdout"

    protocol = module.prepare_holdout_dataset_label_blind(
        archive=archive,
        allowed_derivatives_dir=masks,
        output_dir=output,
    )

    assert protocol["case_count"] == 2
    assert protocol["labels_read"] is False
    assert protocol["participants_tsv_read"] is False
    assert protocol["ground_truth_created"] is False
    assert protocol["lesion_masks_read"] == 0
    assert protocol["manual_lesion_masks_copied"] == 0
    assert not (output / "protected_ground_truth").exists()
    input_text = (output / "manifests" / "holdout_inputs.jsonl").read_text(encoding="utf-8")
    lowered = input_text.lower()
    assert "sub-" not in lowered
    assert "hcc" not in lowered
    assert "label" not in lowered
    assert "lesion" not in lowered
    assert "diagnosis" not in lowered
    rows = [json.loads(line) for line in input_text.splitlines()]
    assert len(rows) == 2
    assert all(row["split"] == "holdout_blind" for row in rows)
    assert all("sub-" not in path.name for path in (output / "inputs").iterdir())
    assert len(list((output / "inputs").rglob("*.nii.gz"))) == 20
    assert not list((output / "inputs").rglob("*.json"))


def test_missing_automatic_liver_masks_aborts_atomically(tmp_path, monkeypatch):
    subjects = {"sub-045"}
    archive = tmp_path / "sub-044-sub-088.zip"
    md5 = _write_archive(archive, subjects)
    _configure(monkeypatch, archive, subjects, md5)
    output = tmp_path / "prepared_holdout"
    with pytest.raises(PipelineError, match="Máscaras hepáticas automáticas ausentes"):
        module.prepare_holdout_dataset_label_blind(
            archive=archive,
            allowed_derivatives_dir=tmp_path / "missing",
            output_dir=output,
        )
    assert not output.exists()
    assert not list(tmp_path.glob(".prepared_holdout.staging.*"))


def test_existing_destination_is_never_overwritten(tmp_path):
    output = tmp_path / "prepared_holdout"
    output.mkdir()
    with pytest.raises(PipelineError, match="não sobrescreve"):
        module.prepare_holdout_dataset_label_blind(
            archive=tmp_path / "missing.zip",
            allowed_derivatives_dir=tmp_path,
            output_dir=output,
        )


def _prepared_fixture(tmp_path, monkeypatch) -> Path:
    subjects = {"sub-045", "sub-088"}
    archive = tmp_path / "sub-044-sub-088.zip"
    md5 = _write_archive(archive, subjects)
    _configure(monkeypatch, archive, subjects, md5)
    masks = tmp_path / "allowed"
    _write_masks(masks, subjects)
    output = tmp_path / "prepared_holdout"
    module.prepare_holdout_dataset_label_blind(
        archive=archive,
        allowed_derivatives_dir=masks,
        output_dir=output,
    )
    return output


def test_audit_proves_complete_label_blind_tree(tmp_path, monkeypatch):
    output = _prepared_fixture(tmp_path, monkeypatch)
    audit = module.audit_prepared_holdout_label_blind(output)
    assert audit["schema"] == module.HOLDOUT_AUDIT_SCHEMA
    assert audit["case_count"] == 2
    assert audit["input_file_count"] == 20
    assert audit["image_volume_count"] == 12
    assert audit["automatic_liver_mask_count"] == 8
    assert audit["labels_read"] is False
    assert audit["lesion_masks_read"] == 0
    assert audit["public_subject_ids_in_inference_inputs"] is False


def test_audit_rejects_tampered_input(tmp_path, monkeypatch):
    output = _prepared_fixture(tmp_path, monkeypatch)
    target = next((output / "inputs").rglob("*.nii.gz"))
    target.write_bytes(target.read_bytes() + b"tampered")
    with pytest.raises(PipelineError, match="Hash ou tamanho incompatível"):
        module.audit_prepared_holdout_label_blind(output)


def test_audit_rejects_unmanifested_input(tmp_path, monkeypatch):
    output = _prepared_fixture(tmp_path, monkeypatch)
    extra = next((output / "inputs").iterdir()) / "extra.nii.gz"
    extra.write_bytes(b"extra")
    with pytest.raises(PipelineError, match="Árvore de inputs diverge"):
        module.audit_prepared_holdout_label_blind(output)
