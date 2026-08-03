import json

import numpy as np
import pytest

from dtwin.candidate_region import validate_and_store_candidate
from dtwin.core import PipelineError, array_from, array_to_image, read_image, save_image, sha256_of
from dtwin.engine import Engine
from dtwin import stages
from .conftest import make_sphere_mask


def _candidate(synthetic_case, tmp_path):
    liver_image = read_image(synthetic_case.mask_organ)
    liver = array_from(liver_image) > 0
    inside = np.rint(np.argwhere(liver).mean(axis=0)).astype(int)
    outside = np.argwhere(~liver)[0]
    raw = np.zeros_like(liver, dtype=np.uint8)
    raw |= make_sphere_mask(raw.shape, tuple(inside), 3)
    raw[tuple(outside)] = 1
    path = tmp_path / "raw_candidate.nii.gz"
    save_image(array_to_image(raw, liver_image, np.uint8), path)
    receipt = validate_and_store_candidate(
        synthetic_case,
        path,
        request={
            "schema": "argos-candidate-request-v1",
            "screening_decision_frozen": True,
            "ground_truth_included": False,
        },
        model_version="fake-test-model",
        elapsed_seconds=1.25,
    )
    return receipt


def test_candidate_is_clipped_to_liver_and_is_never_diagnostic(synthetic_case, tmp_path):
    receipt = _candidate(synthetic_case, tmp_path)
    candidate = array_from(read_image(synthetic_case.mask_candidate)) > 0
    liver = array_from(read_image(synthetic_case.mask_organ)) > 0

    assert candidate.sum() > 30
    assert np.all(candidate <= liver)
    assert receipt["outside_liver_voxels_removed"] == 1
    assert receipt["used_by_screening_inference"] is False
    assert receipt["ground_truth_lesion_mask_used"] is False
    assert receipt["candidate_is_diagnosis"] is False
    assert receipt["mask_sha256"] == sha256_of(synthetic_case.mask_candidate)


def test_candidate_rejects_geometry_mismatch(synthetic_case, tmp_path):
    reference = read_image(synthetic_case.mask_organ)
    shape = tuple(reversed(reference.GetSize()))
    raw = make_sphere_mask(shape, tuple(value // 2 for value in shape), 2)
    wrong = array_to_image(raw, reference, np.uint8)
    wrong.SetOrigin((999.0, 0.0, 0.0))
    path = tmp_path / "wrong.nii.gz"
    save_image(wrong, path)
    with pytest.raises(PipelineError, match="geometria"):
        validate_and_store_candidate(
            synthetic_case, path, request={}, model_version="fake", elapsed_seconds=0
        )


def test_finalize_publishes_unconfirmed_candidate_separately(synthetic_case, tmp_path):
    receipt = _candidate(synthetic_case, tmp_path)
    case = Engine("profiles/figado.yaml").finalize(synthetic_case.root, no_lesion=False)
    manifest = json.loads((case.outputs / "viewer_manifest.json").read_text("utf-8"))
    roles = {item["role"]: item for item in manifest["meshes"]}

    assert "lesao" in roles
    assert roles["lesao"]["material"] == "lesion"
    assert "candidato" in roles
    assert roles["candidato"]["material"] == "candidate"
    assert "não confirmada" in roles["candidato"]["label"]
    assert manifest["candidate_region"]["mask_sha256"] == receipt["mask_sha256"]
    assert manifest["review_requirements"]["inspect_candidate_against_mr"] is True
    assert manifest["reference_images"]["overlay"].endswith("candidate_amber")


def test_tampered_candidate_aborts_viewer_publication(synthetic_case, tmp_path):
    _candidate(synthetic_case, tmp_path)
    image = read_image(synthetic_case.mask_candidate)
    save_image(array_to_image(np.zeros_like(array_from(image)), image, np.uint8), synthetic_case.mask_candidate)
    with pytest.raises(PipelineError, match="Integridade"):
        stages.stage5_refine(synthetic_case, Engine("profiles/figado.yaml").profile)
