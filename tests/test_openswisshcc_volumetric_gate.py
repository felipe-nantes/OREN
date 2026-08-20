from __future__ import annotations

import json
from pathlib import Path

import pytest

from dtwin.benchmark.openswisshcc_alignment import _sha256
from dtwin.benchmark.openswisshcc_volumetric_gate import (
    AGGREGATION_RULE,
    _canonical_sha256,
    create_volumetric_freeze,
    create_volumetric_review,
    validate_volumetric_candidate,
    verify_volumetric_freeze,
    verify_volumetric_review,
)
from dtwin.core import PipelineError

CONFIGS = {
    "multiphase": Path("configs/medgemma_local_4b_multiphase_volumetric_choice_pathology.yaml"),
    "venous": Path("configs/medgemma_local_4b_venous_volumetric_choice_pathology.yaml"),
    "venous_high_contrast": Path(
        "configs/medgemma_local_4b_venous_volumetric_high_contrast_choice_pathology.yaml"
    ),
}


def _write(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True), encoding="utf-8")


def _foundation(tmp_path: Path) -> tuple[Path, str]:
    root = tmp_path / "panels"
    case_id = "anon-openswiss-unit"
    case = root / case_id
    case.mkdir(parents=True)
    paths = []
    for number in (1, 2):
        path = case / f"panel_{number:03d}.png"
        path.write_bytes(f"safe-panel-{number}".encode())
        paths.append(path)
    panels = [
        {
            "panel_number": number,
            "panel_total": 2,
            "image": path.name,
            "sha256": _sha256(path),
            "bytes": path.stat().st_size,
            "axial_interval": [number * 2, number * 2 + 1],
        }
        for number, path in enumerate(paths, start=1)
    ]
    coverage = {
        "expected_axial_indices": [2, 3, 4, 5],
        "first_liver_slice": 2,
        "last_liver_slice": 5,
        "missing_axial_indices": [],
        "duplicate_axial_indices": [],
        "total_liver_voxels": 100,
        "covered_liver_voxels": 100,
        "coverage_percent": 100.0,
        "gate_passed": True,
        "gate_rule": "covered_liver_voxels == total_liver_voxels",
    }
    panel_manifest = {
        "case_id": case_id,
        "panel_strategy": "volumetric_blocks",
        "lesion_pre_marked": False,
        "coverage": coverage,
        "panels": [{key: item[key] for key in (
            "panel_number", "panel_total", "image", "sha256", "axial_interval"
        )} for item in panels],
    }
    panel_manifest_path = case / "medgemma_liver_screening_manifest.json"
    _write(panel_manifest_path, panel_manifest)
    candidate = {
        "schema": "argos-public-liver-mri-volumetric-candidate-v1",
        "case_id": case_id,
        "candidate_kind": "multiphase_rgb",
        "candidate_version": "unit-vol-v1",
        "candidate_signature": "a" * 64,
        "panel_strategy": "volumetric_blocks",
        "panel_filename": panels[0]["image"],
        "panel_sha256": panels[0]["sha256"],
        "panel_bytes": panels[0]["bytes"],
        "panel_manifest_filename": panel_manifest_path.name,
        "panel_image_count": 2,
        "panels": panels,
        "panel_set_sha256": _canonical_sha256(panels),
        "coverage": coverage,
        "config_sha256": _sha256(CONFIGS["multiphase"]),
        "visible_phi_confirmed": False,
        "research_only": True,
        "clinical_use_allowed": False,
        "ground_truth_read": False,
    }
    _write(case / "candidate_manifest.json", candidate)
    summary = {
        "case_id": case_id,
        "candidate_kind": "multiphase_rgb",
        "candidate_signature": "a" * 64,
        "panel_image_count": 2,
        "panel_set_sha256": candidate["panel_set_sha256"],
        "total_liver_voxels": 100,
        "covered_liver_voxels": 100,
    }
    cohort = {
        "schema": "argos-openswisshcc-volumetric-candidate-cohort-v1",
        "case_count": 1,
        "panel_image_count": 2,
        "cases": [summary],
        "cohort_signature": _canonical_sha256([summary]),
        "research_only": True,
        "clinical_use_allowed": False,
        "ground_truth_read": False,
        "inference_executed": False,
    }
    _write(root / "cohort_manifest.json", cohort)
    return root, case_id


def _review(root: Path, path: Path) -> dict:
    return create_volumetric_review(
        panel_root=root,
        output_path=path,
        reviewer="human-unit-test",
        expected_case_count=1,
        confirmations={
            "no_visible_phi": True,
            "all_panels_open_and_uncorrupted": True,
            "liver_framing_acceptable": True,
            "multiphase_alignment_acceptable": True,
            "volumetric_sequence_acceptable": True,
        },
    )


def test_review_binds_every_panel_manifest_and_exact_coverage(tmp_path: Path):
    root, _ = _foundation(tmp_path)
    review_path = tmp_path / "review.json"
    review = _review(root, review_path)
    assert review["case_count"] == 1
    assert review["panel_image_count"] == 2
    assert len(review["cases"][0]["panels"]) == 2
    assert review["cases"][0]["covered_liver_voxels"] == 100
    assert verify_volumetric_review(
        review_path=review_path, panel_root=root, expected_case_count=1
    ) == review


def test_review_fails_closed_if_non_preview_panel_changes(tmp_path: Path):
    root, case_id = _foundation(tmp_path)
    review_path = tmp_path / "review.json"
    _review(root, review_path)
    (root / case_id / "panel_002.png").write_bytes(b"tampered")
    with pytest.raises(PipelineError, match="Hash ou tamanho"):
        verify_volumetric_review(
            review_path=review_path, panel_root=root, expected_case_count=1
        )


def test_candidate_rejects_incomplete_coverage(tmp_path: Path):
    root, case_id = _foundation(tmp_path)
    path = root / case_id / "candidate_manifest.json"
    candidate = json.loads(path.read_text(encoding="utf-8"))
    candidate["coverage"]["covered_liver_voxels"] = 99
    _write(path, candidate)
    with pytest.raises(PipelineError, match="igualdade exata"):
        validate_volumetric_candidate(root, case_id)


def test_candidate_rejects_missing_panel(tmp_path: Path):
    root, case_id = _foundation(tmp_path)
    (root / case_id / "panel_002.png").unlink()
    with pytest.raises(PipelineError, match="ausente"):
        validate_volumetric_candidate(root, case_id)


def test_review_requires_all_explicit_human_confirmations(tmp_path: Path):
    root, _ = _foundation(tmp_path)
    with pytest.raises(PipelineError, match="confirmacoes"):
        create_volumetric_review(
            panel_root=root,
            output_path=tmp_path / "review.json",
            reviewer="human",
            expected_case_count=1,
            confirmations={"no_visible_phi": True},
        )


def test_freeze_binds_configs_collection_and_aggregation_rule(tmp_path: Path):
    root, _ = _foundation(tmp_path)
    review_path = tmp_path / "review.json"
    review = _review(root, review_path)
    freeze_path = tmp_path / "freeze.json"
    freeze = create_volumetric_freeze(
        panel_root=root,
        review_path=review_path,
        config_paths=CONFIGS,
        output_path=freeze_path,
        experiment_version="unit-volumetric-v1",
        expected_case_count=1,
        max_case_seconds=180,
    )
    assert freeze["review_signature"] == review["review_signature"]
    assert freeze["panel_image_count"] == 2
    assert freeze["aggregation_rule"] == AGGREGATION_RULE
    assert freeze["candidates"][0]["config_key"] == "multiphase"
    assert verify_volumetric_freeze(
        freeze_path=freeze_path,
        panel_root=root,
        review_path=review_path,
        config_paths=CONFIGS,
        expected_case_count=1,
    ) == freeze


def test_freeze_detects_config_change_by_hash(tmp_path: Path):
    root, _ = _foundation(tmp_path)
    review_path = tmp_path / "review.json"
    _review(root, review_path)
    freeze_path = tmp_path / "freeze.json"
    create_volumetric_freeze(
        panel_root=root,
        review_path=review_path,
        config_paths=CONFIGS,
        output_path=freeze_path,
        experiment_version="unit-volumetric-v1",
        expected_case_count=1,
    )
    altered = tmp_path / "altered.yaml"
    altered.write_text(CONFIGS["multiphase"].read_text(encoding="utf-8") + "\n# changed\n", encoding="utf-8")
    configs = {**CONFIGS, "multiphase": altered}
    with pytest.raises(PipelineError):
        verify_volumetric_freeze(
            freeze_path=freeze_path,
            panel_root=root,
            review_path=review_path,
            config_paths=configs,
            expected_case_count=1,
        )
