import json
from pathlib import Path

import pytest
from PIL import Image

from dtwin.benchmark.openswisshcc_alignment import _sha256
from dtwin.benchmark.openswisshcc_localizer_enhancement_roi import CASE_SCHEMA as ECASE
from dtwin.benchmark.openswisshcc_localizer_enhancement_roi import (
    COHORT_SCHEMA as ECOHORT,
)
from dtwin.benchmark.openswisshcc_localizer_roi import CASE_SCHEMA as MCASE
from dtwin.benchmark.openswisshcc_localizer_roi import COHORT_SCHEMA as MCOHORT
from dtwin.benchmark.openswisshcc_localizer_roi_freeze import (
    create_roi_freeze,
    verify_roi_freeze,
)
from dtwin.benchmark.openswisshcc_localizer_roi_gate import (
    REQUIRED_CONFIRMATIONS,
    _canonical,
    create_paired_review,
    verify_paired_review,
)
from dtwin.core import PipelineError


def _write_gallery(root: Path, kind: str, center=None):
    case_id = "anon-a"
    center = [1.0, 2.0, 3.0] if center is None else center
    case_dir = root / case_id
    case_dir.mkdir(parents=True)
    image_name = "panel.png"
    image_path = case_dir / image_name
    Image.new("RGB", (64, 64), (30, 40, 50)).save(image_path, "PNG")
    if kind == "morphology":
        roles = ["t1_venous", "t2_blade", "dwi_trace_run_03", "dwi_adc"]
        case_schema, cohort_schema, manifest_name = MCASE, MCOHORT, "roi_manifest.json"
        representation = "model_localizer_high_resolution_multisequence_roi_2x2"
    else:
        roles = ["t1_native", "t1_arterial_registered", "t1_venous", "t1_delayed_registered"]
        case_schema, cohort_schema, manifest_name = ECASE, ECOHORT, "enhancement_roi_manifest.json"
        representation = "model_localizer_dynamic_enhancement_roi_2x2"
    tiles = [{
        "tile_number": number,
        "role": role,
        "available_in_fov": True,
        "geometry_in_fov": True,
        "unavailable_reason": None,
        "candidate_contour_shown": role == "t1_venous",
    } for number, role in enumerate(roles, 1)]
    panel = {
        "panel_number": 1,
        "panel_total": 1,
        "image": image_name,
        "bytes": image_path.stat().st_size,
        "sha256": _sha256(image_path),
        "component_rank": 1,
        "component_voxels": 12,
        "physical_center_lps_xyz": center,
        "fallback_no_candidate": False,
        "fallback_reason": None,
        "tiles": tiles,
    }
    if kind == "enhancement":
        panel["usable_phase_count"] = 4
    manifest = {
        "schema": case_schema,
        "case_id": case_id,
        "representation": representation,
        "panel_count": 1,
        "panels": [panel],
        "candidate_mask_is_model_derived": True,
        "ground_truth_lesion_mask_used": False,
        "ground_truth_read": False,
        "inference_executed": False,
        "research_only": True,
        "clinical_use_allowed": False,
        "requires_human_review": True,
    }
    manifest_path = case_dir / manifest_name
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    record = {"case_id": case_id, "panel_count": 1, "manifest_sha256": _sha256(manifest_path), "panels": [{"image": image_name, "sha256": panel["sha256"]}]}
    cohort = {
        "schema": cohort_schema,
        "case_count": 1,
        "panel_count": 1,
        "cases": [record],
        "source_localizer_summary_sha256": "a" * 64,
        "gallery_signature": _canonical([record]),
        "ground_truth_lesion_mask_used": False,
        "ground_truth_read": False,
        "inference_executed": False,
        "research_only": True,
        "clinical_use_allowed": False,
        "requires_human_review": True,
    }
    (root / "cohort_manifest.json").write_text(json.dumps(cohort), encoding="utf-8")


def _foundation(tmp_path):
    morphology = tmp_path / "morphology"
    enhancement = tmp_path / "enhancement"
    _write_gallery(morphology, "morphology")
    _write_gallery(enhancement, "enhancement")
    review_path = tmp_path / "review.json"
    review = create_paired_review(morphology_root=morphology, enhancement_root=enhancement, output_path=review_path, reviewer="jm", confirmations={key: True for key in REQUIRED_CONFIRMATIONS}, expected_case_count=1)
    return morphology, enhancement, review_path, review


def test_paired_review_binds_both_galleries_and_reviewer(tmp_path):
    morphology, enhancement, review_path, review = _foundation(tmp_path)
    verified = verify_paired_review(morphology_root=morphology, enhancement_root=enhancement, review_path=review_path, expected_case_count=1)
    assert verified["review_signature"] == review["review_signature"]
    assert verified["reviewer"] == "jm"
    assert verified["panel_pairs"] == 1
    assert verified["ground_truth_read"] is False


def test_review_detects_png_tampering_after_approval(tmp_path):
    morphology, enhancement, review_path, _ = _foundation(tmp_path)
    Image.new("RGB", (64, 64), (255, 0, 0)).save(morphology / "anon-a" / "panel.png", "PNG")
    with pytest.raises(PipelineError, match="Hash ou bytes"):
        verify_paired_review(morphology_root=morphology, enhancement_root=enhancement, review_path=review_path, expected_case_count=1)


def test_review_rejects_different_candidate_center_even_with_valid_hashes(tmp_path):
    morphology = tmp_path / "morphology"
    enhancement = tmp_path / "enhancement"
    _write_gallery(morphology, "morphology")
    _write_gallery(enhancement, "enhancement", center=[9.0, 2.0, 3.0])
    with pytest.raises(PipelineError, match="mesmos candidatos"):
        create_paired_review(morphology_root=morphology, enhancement_root=enhancement, output_path=tmp_path / "review.json", reviewer="jm", confirmations={key: True for key in REQUIRED_CONFIRMATIONS}, expected_case_count=1)


def test_freeze_binds_exact_4b_config_review_and_mirrored_protocol(tmp_path):
    morphology, enhancement, review_path, review = _foundation(tmp_path)
    freeze_path = tmp_path / "freeze.json"
    config = Path("configs/medgemma_local_4b_localizer_roi_v10_ab.yaml")
    freeze = create_roi_freeze(morphology_root=morphology, enhancement_root=enhancement, review_path=review_path, config_path=config, output_path=freeze_path, experiment_version="dev-v10-pilot10", expected_case_count=1)
    verified = verify_roi_freeze(morphology_root=morphology, enhancement_root=enhancement, review_path=review_path, config_path=config, freeze_path=freeze_path, expected_case_count=1)
    assert verified["experiment_signature"] == freeze["experiment_signature"]
    assert verified["review_signature"] == review["review_signature"]
    assert verified["config"]["model_id"] == "google/medgemma-1.5-4b-it"
    assert verified["scoring_protocol"]["authorized_tokens"] == ["A", "B"]
    assert verified["max_upstream_seconds"] + verified["max_scoring_seconds"] == 180


def test_freeze_rejects_tampering(tmp_path):
    morphology, enhancement, review_path, _ = _foundation(tmp_path)
    freeze_path = tmp_path / "freeze.json"
    config = Path("configs/medgemma_local_4b_localizer_roi_v10_ab.yaml")
    create_roi_freeze(morphology_root=morphology, enhancement_root=enhancement, review_path=review_path, config_path=config, output_path=freeze_path, experiment_version="dev-v10-pilot10", expected_case_count=1)
    payload = json.loads(freeze_path.read_text())
    payload["max_scoring_seconds"] = 89.0
    freeze_path.write_text(json.dumps(payload))
    with pytest.raises(PipelineError, match="assinatura"):
        verify_roi_freeze(morphology_root=morphology, enhancement_root=enhancement, review_path=review_path, config_path=config, freeze_path=freeze_path, expected_case_count=1)
