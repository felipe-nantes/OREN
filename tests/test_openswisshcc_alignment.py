from __future__ import annotations

import json

import numpy as np
import pytest

import dtwin.benchmark.openswisshcc_alignment as module
from dtwin.benchmark.openswisshcc_alignment import (
    AlignmentGateError,
    dice_coefficient,
    select_alignment_method,
    select_arterial_roles,
)
from dtwin.core import PipelineError


def test_dice_coefficient_exact_and_partial():
    mask = np.array([[1, 1], [0, 0]], dtype=bool)
    assert dice_coefficient(mask, mask) == 1.0
    other = np.array([[1, 0], [1, 0]], dtype=bool)
    assert dice_coefficient(mask, other) == 0.5


def test_dice_rejects_empty_or_incompatible_masks():
    with pytest.raises(PipelineError, match="vazias"):
        dice_coefficient(np.zeros((2, 2)), np.zeros((2, 2)))
    with pytest.raises(PipelineError, match="shapes"):
        dice_coefficient(np.zeros((2, 2)), np.zeros((3, 2)))


def test_selection_uses_best_method_and_identity_on_tie():
    assert select_alignment_method(
        identity_dice=0.91, pairwise_dice=0.95, minimum_dice=0.80
    )["method"] == "pairwise"
    assert select_alignment_method(
        identity_dice=0.95, pairwise_dice=0.90, minimum_dice=0.80
    )["method"] == "identity"
    assert select_alignment_method(
        identity_dice=0.90, pairwise_dice=0.90, minimum_dice=0.80
    )["method"] == "identity"


def test_selection_fails_closed_below_gate():
    with pytest.raises(AlignmentGateError, match="Gate"):
        select_alignment_method(
            identity_dice=0.79, pairwise_dice=0.75, minimum_dice=0.80
        )


def test_selection_rejects_invalid_dice_and_threshold():
    with pytest.raises(PipelineError):
        select_alignment_method(
            identity_dice=float("nan"), pairwise_dice=0.9, minimum_dice=0.8
        )
    with pytest.raises(PipelineError):
        select_alignment_method(identity_dice=0.9, pairwise_dice=0.9, minimum_dice=1.1)


def test_arterial_role_selection_covers_three_protocols():
    triple = {"t1_arterial_ttc_3", "liver_mask_arterial_ttc_3"}
    assert select_arterial_roles(triple, "arterial_ttc_3") == (
        "t1_arterial_ttc_3", "liver_mask_arterial_ttc_3"
    )
    simple = {"t1_arterial", "liver_mask_arterial"}
    assert select_arterial_roles(simple, "arterial") == (
        "t1_arterial", "liver_mask_arterial"
    )
    ttc1 = {"t1_arterial_ttc_1", "liver_mask_arterial_ttc_1"}
    assert select_arterial_roles(ttc1, "arterial") == (
        "t1_arterial_ttc_1", "liver_mask_arterial_ttc_1"
    )


def test_arterial_role_selection_rejects_missing_or_unknown():
    with pytest.raises(PipelineError, match="sem arterial"):
        select_arterial_roles({"t1_arterial"}, "arterial")
    with pytest.raises(PipelineError, match="não autorizada"):
        select_arterial_roles(set(), "arterial_ttc_2")




def test_cache_reuse_rejects_path_traversal(tmp_path):
    case_dir = tmp_path / "case"
    case_dir.mkdir()
    (case_dir / "alignment_manifest.json").write_text(
        json.dumps(
            {
                "cache_signature": "expected",
                "outputs": [{"filename": "../escape.nii.gz", "sha256": "x"}],
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(PipelineError, match="inseguro"):
        module._reuse_cache(case_dir, "expected")




def test_publish_directory_retries_transient_permission_error(tmp_path, monkeypatch):
    staging = tmp_path / "staging"
    destination = tmp_path / "published"
    staging.mkdir()
    (staging / "file.txt").write_text("ok", encoding="utf-8")
    original_replace = module.os.replace
    attempts = {"count": 0}

    def flaky_replace(source, target):
        attempts["count"] += 1
        if attempts["count"] < 3:
            raise PermissionError("lock transitório")
        return original_replace(source, target)

    monkeypatch.setattr(module.os, "replace", flaky_replace)
    monkeypatch.setattr(module.time, "sleep", lambda _seconds: None)
    module._publish_directory(staging, destination)
    assert attempts["count"] == 3
    assert (destination / "file.txt").read_text(encoding="utf-8") == "ok"


def test_input_manifest_loader_allows_only_fixed_development_or_holdout_names(tmp_path):
    manifests = tmp_path / "manifests"
    manifests.mkdir()
    (manifests / "holdout_inputs.jsonl").write_text(
        '{"case_id":"anon-case","files":[]}\n', encoding="utf-8"
    )
    assert set(
        module._load_input_records(
            tmp_path, manifest_filename="holdout_inputs.jsonl"
        )
    ) == {"anon-case"}
    with pytest.raises(PipelineError, match="não autorizado"):
        module._load_input_records(tmp_path, manifest_filename="../labels.jsonl")
