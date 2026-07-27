from __future__ import annotations

import pytest

from dtwin.core import PipelineError
from dtwin.learning.schemas import (
    ProtectedTrainingCase,
    assert_label_blind_record,
)


def test_protected_case_validates_target_taxonomy():
    case = ProtectedTrainingCase(
        case_id="case-1",
        patient_group_id="patient-1",
        dataset_id="dataset",
        label="NEGATIVE",
        negative_subtype="benign_anatomic_variant",
        phenotype_tags=("vascular_structure",),
    )
    case.validate()


def test_positive_rejects_negative_subtype():
    case = ProtectedTrainingCase(
        case_id="case-1",
        patient_group_id="patient-1",
        dataset_id="dataset",
        label="POSITIVE",
        negative_subtype="normal",
    )
    with pytest.raises(PipelineError, match="negative_subtype"):
        case.validate()


@pytest.mark.parametrize(
    "record",
    [
        {"label": "POSITIVE"},
        {"metadata": {"phenotype_tags": ["vascular_structure"]}},
        {"items": [{"lesion_mask_path": "secret.nii.gz"}]},
        {"ground_truth": {"label": "NEGATIVE"}},
    ],
)
def test_label_blind_guard_rejects_protected_fields(record):
    with pytest.raises(PipelineError, match="campos protegidos"):
        assert_label_blind_record(record)


def test_label_blind_guard_accepts_image_provenance():
    assert_label_blind_record(
        {
            "case_id": "anon-1",
            "candidate_id": "candidate-1",
            "phase": "arterial",
            "image_sha256": "a" * 64,
        }
    )
