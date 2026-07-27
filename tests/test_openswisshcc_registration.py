from __future__ import annotations

import hashlib
import json
from zipfile import ZipFile

import pytest

import dtwin.benchmark.openswisshcc_registration as module
from dtwin.core import PipelineError


def _zip(path, subjects, *, unsafe=False):
    prefix = "derivatives/T1_registration_transforms"
    with ZipFile(path, "w") as archive:
        for subject, triple in subjects.items():
            folder = f"{prefix}/{subject}/dyn"
            arterial = "arterial_TTC_3_to_venous" if triple else "arterial_to_venous"
            for stage in (0, 1):
                archive.writestr(
                    f"{folder}/pairwise_registration_transform_parameters_{stage}_{arterial}.txt",
                    f"art:{subject}:{stage}".encode(),
                )
                archive.writestr(
                    f"{folder}/pairwise_registration_transform_parameters_{stage}_delayed_to_venous.txt",
                    f"del:{subject}:{stage}".encode(),
                )
            archive.writestr(
                f"{folder}/groupwise_registration_transform_parameters_0.txt",
                f"group:{subject}".encode(),
            )
        if unsafe:
            archive.writestr("../escape.txt", b"x")
    return hashlib.md5(path.read_bytes()).hexdigest()  # noqa: S324 - checksum oficial é MD5


def _patch_split(monkeypatch):
    development = frozenset({"sub-001", "sub-089"})
    monkeypatch.setattr(module, "DEVELOPMENT_SUBJECTS", development)
    monkeypatch.setattr(module, "HOLDOUT_SUBJECTS", frozenset({"sub-050"}))
    return development


def test_extracts_exact_whitelist_with_neutral_ids(tmp_path, monkeypatch):
    _patch_split(monkeypatch)
    source = tmp_path / "derivatives.zip"
    digest = _zip(source, {"sub-001": True, "sub-089": False, "sub-050": False})
    monkeypatch.setattr(module, "DERIVATIVES_MD5", digest)
    output = tmp_path / "out"
    manifest = module.extract_development_registration_transforms(source, output)
    assert manifest["case_count"] == 2
    assert manifest["holdout_subjects_extracted"] == 0
    assert sum(len(row["files"]) for row in manifest["records"]) == 10
    payload = json.loads((output / "registration_manifest.json").read_text(encoding="utf-8"))
    assert payload["manual_or_lesion_files_extracted"] == 0
    records_text = json.dumps(payload["records"]).lower()
    assert "sub-" not in records_text
    assert "lesion" not in records_text
    assert not any("sub-" in path.name for path in (output / "transforms").iterdir())


def test_missing_required_transform_aborts_atomically(tmp_path, monkeypatch):
    _patch_split(monkeypatch)
    source = tmp_path / "derivatives.zip"
    digest = _zip(source, {"sub-001": True, "sub-089": False})
    monkeypatch.setattr(module, "DERIVATIVES_MD5", digest)
    with ZipFile(source, "a") as archive:
        # Um sujeito adicional não satisfaz a whitelist e nunca deve ser aceito.
        archive.writestr(
            "derivatives/T1_registration_transforms/sub-001/dyn/unrelated.txt", b"x"
        )
    monkeypatch.setattr(module, "DERIVATIVES_MD5", hashlib.md5(source.read_bytes()).hexdigest())
    # Remova logicamente um nome obrigatório na seleção para provar fail-closed.
    original = module._selected_source_names
    monkeypatch.setattr(
        module,
        "_selected_source_names",
        lambda names: original(names - {"groupwise_registration_transform_parameters_0.txt"}),
    )
    output = tmp_path / "out"
    with pytest.raises(PipelineError, match="obrigatório"):
        module.extract_development_registration_transforms(source, output)
    assert not output.exists()


def test_path_traversal_is_rejected(tmp_path, monkeypatch):
    _patch_split(monkeypatch)
    source = tmp_path / "derivatives.zip"
    digest = _zip(source, {"sub-001": True, "sub-089": False}, unsafe=True)
    monkeypatch.setattr(module, "DERIVATIVES_MD5", digest)
    with pytest.raises(PipelineError, match="inseguro"):
        module.extract_development_registration_transforms(source, tmp_path / "out")


def test_existing_destination_is_not_overwritten(tmp_path):
    output = tmp_path / "out"
    output.mkdir()
    with pytest.raises(PipelineError, match="não sobrescreve"):
        module.extract_development_registration_transforms(tmp_path / "missing.zip", output)


def test_extracts_holdout_transforms_without_development_or_ground_truth(
    tmp_path, monkeypatch
):
    holdout = frozenset({"sub-045", "sub-088"})
    monkeypatch.setattr(module, "HOLDOUT_SUBJECTS", holdout)
    monkeypatch.setattr(module, "DEVELOPMENT_SUBJECTS", frozenset({"sub-001"}))
    source = tmp_path / "derivatives.zip"
    digest = _zip(source, {"sub-001": True, "sub-045": False, "sub-088": True})
    monkeypatch.setattr(module, "DERIVATIVES_MD5", digest)
    output = tmp_path / "holdout"

    manifest = module.extract_holdout_registration_transforms_label_blind(source, output)

    assert manifest["case_count"] == 2
    assert manifest["holdout_subjects_extracted"] == 2
    assert manifest["development_subjects_extracted"] == 0
    assert manifest["manual_or_lesion_files_extracted"] == 0
    assert manifest["ground_truth_read"] is False
    serialized = json.dumps(manifest["records"]).lower()
    assert "sub-" not in serialized
    assert "hcc" not in serialized
    assert "label" not in serialized
    assert "lesion" not in serialized
    assert len(list((output / "transforms").rglob("*.txt"))) == 10

