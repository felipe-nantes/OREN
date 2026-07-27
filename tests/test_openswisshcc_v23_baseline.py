from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from dtwin.benchmark.openswisshcc_v20_fusion import V11_WEIGHTS, _canonical_sha
from dtwin.benchmark.openswisshcc_v23_baseline import (
    LOCK_SCHEMA,
    verify_v23_baseline_lock,
)
from dtwin.benchmark.openswisshcc_v23_shape_fusion import CALIBRATOR_SCHEMA
from dtwin.core import PipelineError


def _write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _fixture(tmp_path: Path) -> Path:
    evaluation = {
        "case_count": 87,
        "weights": {"v11": 0.8, "candidate_weighted_linearity": 0.2},
        "primary_loocv_metrics": {
            "tp": 32, "tn": 38, "fp": 10, "fn": 7,
            "sensitivity": 32 / 39, "specificity": 38 / 48,
            "balanced_accuracy": ((32 / 39) + (38 / 48)) / 2,
            "passed_75_75": True,
        },
        "repeated_stratified_5fold": {
            "repeats": 50, "folds": 5, "seed": 20260720,
            "runs_passing_75_75": 49,
            "median_sensitivity": 32 / 39,
            "median_specificity": 38 / 48,
            "minimum_sensitivity": 28 / 39,
            "minimum_specificity": 0.75,
            "transform_and_threshold_fit_inside_each_training_fold": True,
        },
        "development_point_gate_passed": True,
        "development_robustness_gate_passed": False,
        "final_system_qualification_claimed": False,
        "lesion_masks_read": False,
        "holdout_opened": False,
        "qualified": False,
    }
    references = {
        **{name: [0.0, 1.0] for name in V11_WEIGHTS},
        "candidate_weighted_linearity": [0.0, 1.0],
    }
    calibrator_unsigned = {
        "schema": CALIBRATOR_SCHEMA,
        "status": "frozen_for_new_independent_external_validation",
        "development_reference_count": 2,
        "primary_shape_feature": "candidate_weighted_linearity",
        "weights": {"v11": 0.8, "candidate_weighted_linearity": 0.2},
        "decision_threshold": 0.5,
        "ecdf_references": references,
        "hypothesis_selected_after_development_labels": True,
        "independent_balanced_validation_required": True,
        "holdout_v21_reuse_forbidden": True,
        "qualified": False,
        "research_only": True,
        "clinical_use_allowed": False,
    }
    calibrator = {
        **calibrator_unsigned,
        "calibrator_signature": _canonical_sha(calibrator_unsigned),
    }
    timing = {
        "case_count": 87,
        "features_recomputed_exactly": True,
        "labels_read": False,
        "lesion_masks_read": False,
        "raw_dicom_end_to_end_180_seconds_proven": False,
        "conservative_precomputed_pipeline_seconds": {
            "sum": 107.0,
            "passed_180_seconds": True,
        },
    }
    paths = {
        "evaluation.json": evaluation,
        "calibrator.json": calibrator,
        "timing.json": timing,
    }
    for name, value in paths.items():
        _write_json(tmp_path / name, value)
    files = {
        name: {"sha256": _sha(tmp_path / name), "bytes": (tmp_path / name).stat().st_size}
        for name in paths
    }
    lock = {
        "schema": LOCK_SCHEMA,
        "status": "frozen_reproducible_development_baseline",
        "development_only": True,
        "qualified": False,
        "independent_balanced_validation_required": True,
        "holdout_v21_reuse_forbidden": True,
        "files": files,
        "artifact_roles": {
            "evaluation": "evaluation.json",
            "calibrator": "calibrator.json",
            "timing": "timing.json",
        },
        "expected_primary_loocv_metrics": evaluation["primary_loocv_metrics"],
        "expected_repeated_stratified_5fold": evaluation["repeated_stratified_5fold"],
        "expected_calibrator": {
            "decision_threshold": 0.5,
            "calibrator_signature": calibrator["calibrator_signature"],
        },
        "expected_timing": {
            "case_count": 87,
            "prepared_upper_bound_seconds": 107.0,
            "raw_dicom_end_to_end_180_seconds_proven": False,
        },
    }
    lock_path = tmp_path / "lock.json"
    _write_json(lock_path, lock)
    return lock_path


def test_verifies_complete_frozen_baseline(tmp_path):
    lock = _fixture(tmp_path)
    result = verify_v23_baseline_lock(lock_path=lock, workspace_root=tmp_path)
    assert result["status"] == "verified_frozen_reproducible_development_baseline"
    assert result["primary_loocv_metrics"]["sensitivity"] == 32 / 39
    assert result["qualified"] is False
    assert result["raw_dicom_end_to_end_180_seconds_proven"] is False


def test_rejects_tampered_artifact(tmp_path):
    lock = _fixture(tmp_path)
    (tmp_path / "evaluation.json").write_text("{}\n", encoding="utf-8")
    with pytest.raises(PipelineError, match="alterado ou truncado"):
        verify_v23_baseline_lock(lock_path=lock, workspace_root=tmp_path)


def test_rejects_path_outside_workspace(tmp_path):
    lock = _fixture(tmp_path)
    value = json.loads(lock.read_text(encoding="utf-8"))
    value["files"]["../escape.json"] = value["files"].pop("evaluation.json")
    value["artifact_roles"]["evaluation"] = "../escape.json"
    _write_json(lock, value)
    with pytest.raises(PipelineError, match="caminho inseguro"):
        verify_v23_baseline_lock(lock_path=lock, workspace_root=tmp_path)
