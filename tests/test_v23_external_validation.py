from __future__ import annotations

import pytest

from dtwin.benchmark.v23_external_validation import (
    CONSUMED_DATASET_IDS,
    MINIMUM_CASES_PER_CLASS,
    _validate_images,
    _validate_labels,
)
from dtwin.core import PipelineError


def _label(case_id: str, label: str) -> dict:
    return {
        "schema": "argos-v23-external-protected-label-v1",
        "case_id": case_id,
        "label": label,
        "target_condition": "focal_liver_lesion_suspicion",
        "reference_standard": "public_expert_annotation",
        "research_only": True,
        "clinical_use_allowed": False,
    }


def test_minimum_class_size_is_predeclared():
    assert MINIMUM_CASES_PER_CLASS == 40


def test_every_consumed_dataset_is_forbidden():
    assert set(CONSUMED_DATASET_IDS) == {
        "openswisshcc",
        "lld_mmri",
        "liverhccseg",
        "chaos_mri",
        "tcga_lihc",
    }


def test_labels_require_exact_balanced_inventory():
    ids = [f"anon-fresh-{index:03d}" for index in range(80)]
    rows = [
        _label(case_id, "POSITIVE" if index < 40 else "NEGATIVE")
        for index, case_id in enumerate(ids)
    ]
    assert _validate_labels(rows, ids) == (40, 40)


def test_labels_reject_underpowered_class():
    ids = [f"anon-fresh-{index:03d}" for index in range(79)]
    rows = [
        _label(case_id, "POSITIVE" if index < 39 else "NEGATIVE")
        for index, case_id in enumerate(ids)
    ]
    with pytest.raises(PipelineError, match="40 positivos"):
        _validate_labels(rows, ids)


def test_labels_reject_case_mismatch():
    ids = [f"anon-fresh-{index:03d}" for index in range(80)]
    rows = [
        _label(case_id, "POSITIVE" if index < 40 else "NEGATIVE")
        for index, case_id in enumerate(ids)
    ]
    with pytest.raises(PipelineError, match="não correspondem"):
        _validate_labels(rows, ids[:-1])


def test_images_reject_consumed_dataset_before_reading_files(tmp_path):
    rows = [
        {
            "schema": "argos-v23-external-image-case-v1",
            "case_id": "anon-fresh-000",
            "source_dataset_id": "openswisshcc",
            "study_fingerprint_sha256": "a" * 64,
            "files": [{"role": "t1", "relative_path": "missing.nii.gz"}],
            "ground_truth_read": False,
            "lesion_masks_used": False,
            "research_only": True,
            "clinical_use_allowed": False,
        }
    ]
    with pytest.raises(PipelineError, match="Registro de imagem"):
        _validate_images(
            rows=rows,
            workspace_root=tmp_path,
            forbidden_fingerprints=set(),
        )


def test_images_reject_known_study_fingerprint_before_reading_files(tmp_path):
    rows = [
        {
            "schema": "argos-v23-external-image-case-v1",
            "case_id": "anon-fresh-000",
            "source_dataset_id": "fresh_dataset",
            "study_fingerprint_sha256": "b" * 64,
            "files": [{"role": "t1", "relative_path": "missing.nii.gz"}],
            "ground_truth_read": False,
            "lesion_masks_used": False,
            "research_only": True,
            "clinical_use_allowed": False,
        }
    ]
    with pytest.raises(PipelineError, match="Registro de imagem"):
        _validate_images(
            rows=rows,
            workspace_root=tmp_path,
            forbidden_fingerprints={"b" * 64},
        )


def test_images_reject_lesion_mask_role(tmp_path):
    image = tmp_path / "image.bin"
    image.write_bytes(b"image")
    rows = [
        {
            "schema": "argos-v23-external-image-case-v1",
            "case_id": "anon-fresh-000",
            "source_dataset_id": "fresh_dataset",
            "study_fingerprint_sha256": "c" * 64,
            "files": [
                {
                    "role": "lesion_mask",
                    "relative_path": "image.bin",
                    "bytes": 5,
                    "sha256": (
                        "6105d6cc76af4003d6f4bbf3f8c333b990a20f0b26d0245d7cbe6ddf33e7d1a3"
                    ),
                }
            ],
            "ground_truth_read": False,
            "lesion_masks_used": False,
            "research_only": True,
            "clinical_use_allowed": False,
        }
    ]
    with pytest.raises(PipelineError, match="Arquivo externo inválido"):
        _validate_images(
            rows=rows,
            workspace_root=tmp_path,
            forbidden_fingerprints=set(),
        )
