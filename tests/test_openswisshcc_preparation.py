import csv
import hashlib
import json
from pathlib import Path
from zipfile import ZipFile

import pytest

from dtwin.benchmark import openswisshcc as module
from dtwin.core import PipelineError


def _write_participants(path: Path) -> None:
    with path.open("w", encoding="utf-8", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=["ID", "HCC"], delimiter="\t")
        writer.writeheader()
        for number in range(1, 133):
            writer.writerow({"ID": f"sub-{number:03d}", "HCC": "1" if number <= 63 else ""})


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
            zf.writestr(f"{subject}/dyn/{subject}_acq-inphase_phase-native_T1w.nii.gz", b"skip")
    return hashlib.md5(path.read_bytes(), usedforsecurity=False).hexdigest()


def _write_masks(root: Path, subjects: set[str]) -> None:
    for subject in subjects:
        folder = root / subject / "dyn"
        folder.mkdir(parents=True)
        for phase in ["native", "arterial-TTC-1", "venous", "delayed"]:
            (folder / f"{subject}_acq-water_phase-{phase}_T1w-liver_seg.nii.gz").write_bytes(
                f"mask:{subject}:{phase}".encode()
            )


def test_split_is_disjoint_complete_and_balanced_as_expected():
    module.validate_splits()
    assert len(module.DEVELOPMENT_SUBJECTS) == 88
    assert len(module.HOLDOUT_SUBJECTS) == 44
    assert not (module.DEVELOPMENT_SUBJECTS & module.HOLDOUT_SUBJECTS)


def test_labels_are_loaded_with_expected_dataset_distribution(tmp_path):
    participants = tmp_path / "participants.tsv"
    _write_participants(participants)
    labels = module.load_subject_labels(participants)
    assert sum(item.label == "POSITIVE" for item in labels.values()) == 63
    assert sum(item.label == "NEGATIVE" for item in labels.values()) == 69


def test_member_selection_excludes_inphase_and_rejects_holdout(tmp_path, monkeypatch):
    archive = tmp_path / "sub-001-sub-044.zip"
    md5 = _write_archive(archive, {"sub-001", "sub-045"})
    monkeypatch.setitem(
        module.DEVELOPMENT_ARCHIVES,
        archive.name,
        {"md5": md5, "subjects": frozenset({"sub-001", "sub-045"})},
    )
    with pytest.raises(PipelineError, match="holdout"):
        module.inspect_development_archive(archive)


def test_unsafe_zip_member_is_rejected(tmp_path, monkeypatch):
    archive = tmp_path / "sub-001-sub-044.zip"
    with ZipFile(archive, "w") as zf:
        zf.writestr("../sub-001/dyn/x.nii.gz", b"bad")
    md5 = hashlib.md5(archive.read_bytes(), usedforsecurity=False).hexdigest()
    monkeypatch.setitem(
        module.DEVELOPMENT_ARCHIVES,
        archive.name,
        {"md5": md5, "subjects": frozenset({"sub-001"})},
    )
    with pytest.raises(PipelineError, match="inseguro"):
        module.inspect_development_archive(archive)


def test_full_preparation_separates_inputs_and_ground_truth(tmp_path, monkeypatch):
    participants = tmp_path / "participants.tsv"
    _write_participants(participants)
    subjects_a = {"sub-001"}
    subjects_b = {"sub-089"}
    archive_a = tmp_path / "sub-001-sub-044.zip"
    archive_b = tmp_path / "sub-088-sub-132.zip"
    md5_a = _write_archive(archive_a, subjects_a)
    md5_b = _write_archive(archive_b, subjects_b)
    monkeypatch.setattr(module, "DEVELOPMENT_SUBJECTS", frozenset(subjects_a | subjects_b))
    monkeypatch.setattr(module, "HOLDOUT_SUBJECTS", frozenset())
    monkeypatch.setattr(
        module,
        "DEVELOPMENT_ARCHIVES",
        {
            archive_a.name: {"md5": md5_a, "subjects": frozenset(subjects_a)},
            archive_b.name: {"md5": md5_b, "subjects": frozenset(subjects_b)},
        },
    )
    monkeypatch.setattr(module, "validate_splits", lambda: None)
    monkeypatch.setattr(
        module,
        "load_subject_labels",
        lambda _path: {
            "sub-001": module.SubjectLabel("sub-001", True),
            "sub-089": module.SubjectLabel("sub-089", False),
        },
    )
    masks = tmp_path / "allowed"
    _write_masks(masks, subjects_a | subjects_b)
    output = tmp_path / "prepared"
    protocol = module.prepare_development_dataset(
        participants_path=participants,
        archives=[archive_a, archive_b],
        allowed_derivatives_dir=masks,
        output_dir=output,
    )
    assert protocol["case_count"] == 2
    assert protocol["manual_lesion_masks_copied"] == 0
    input_text = (output / "manifests" / "development_inputs.jsonl").read_text(encoding="utf-8")
    assert "sub-" not in input_text
    assert "label" not in input_text.lower()
    assert "hcc" not in input_text.lower()
    copied_files = [path for path in (output / "inputs").rglob("*.nii.gz")]
    assert copied_files
    assert any("masks" in path.parts for path in copied_files)
    protected = [
        json.loads(line)
        for line in (output / "protected_ground_truth" / "development_labels.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    assert {row["public_subject_id"] for row in protected} == subjects_a | subjects_b
    assert all("sub-" not in path.name for path in (output / "inputs").iterdir())


def test_existing_destination_is_never_overwritten(tmp_path):
    destination = tmp_path / "prepared"
    destination.mkdir()
    with pytest.raises(PipelineError, match="não sobrescreve"):
        module.prepare_development_dataset(
            participants_path=tmp_path / "missing.tsv",
            archives=[],
            allowed_derivatives_dir=tmp_path,
            output_dir=destination,
        )




