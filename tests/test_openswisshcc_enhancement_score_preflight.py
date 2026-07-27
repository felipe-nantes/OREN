from __future__ import annotations

import json
from pathlib import Path

import pytest

import dtwin.benchmark.openswisshcc_enhancement_score_preflight as module
from dtwin.benchmark.openswisshcc_alignment import _sha256
from dtwin.benchmark.openswisshcc_enhancement_proposal_selection import ALGORITHM_VERSION
from dtwin.benchmark.openswisshcc_lesion_localizer import CASE_SCHEMA, RUN_SCHEMA
from dtwin.core import PipelineError


def _write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def _fixture(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path, Path, dict]:
    bundle_root = tmp_path / "development_bundle"
    localizer_root = tmp_path / "development_localizer"
    audit_path = tmp_path / "development_audit.json"
    case_ids = [f"anon-openswiss-{index:02d}" for index in range(10)]
    summary = {
        "schema": RUN_SCHEMA,
        "status": "complete_scores_only_no_decision",
        "algorithm_version": ALGORITHM_VERSION,
        "case_ids": case_ids,
        "ground_truth_read": False,
        "ground_truth_lesion_mask_used": False,
        "metrics_calculated": False,
        "final_decision": None,
    }
    _write(localizer_root / "summary.json", summary)
    cases = []
    for case_id in case_ids:
        localizer = {
            "schema": CASE_SCHEMA,
            "case_id": case_id,
            "status": "candidate_scores_only_no_decision",
            "algorithm_version": ALGORITHM_VERSION,
            "candidate_mask_is_model_derived": False,
            "candidate_mask_is_deterministic_enhancement": True,
            "ground_truth_read": False,
            "ground_truth_lesion_mask_used": False,
            "metrics_calculated": False,
            "final_decision": None,
        }
        localizer_path = localizer_root / case_id / "localizer_manifest.json"
        _write(localizer_path, localizer)
        visual = {
            "selection": {
                "rule": "largest_until_minimum_and_target_fraction_with_maximum",
                "component_count": 5,
                "selected_component_count": 5,
                "selected_component_ranks": [1, 2, 3, 4, 5],
                "candidate_volume_coverage_fraction": 1.0,
                "target_fraction": 1.0,
                "minimum_candidates": 5,
                "maximum_candidates": 5,
            },
            "candidate_stack_count": 5,
            "source_localizer_manifest_sha256": _sha256(localizer_path),
            "gate": {"candidate_coverage_passed": True},
        }
        visual_path = bundle_root / case_id / "case_manifest.json"
        _write(visual_path, visual)
        cases.append({"case_id": case_id, "candidate_stack_count": 5})
    cohort = {
        "protocol": {
            "candidate_target_fraction": 1.0,
            "minimum_base_candidates": 5,
            "maximum_candidates": 5,
        },
        "source_localizer_summary_sha256": _sha256(localizer_root / "summary.json"),
        "gallery_signature": "g" * 64,
        "ground_truth_read": False,
        "dataset_lesion_mask_used": False,
        "holdout_opened": False,
        "inference_executed": False,
    }
    bundle = {
        "root": bundle_root,
        "cohort": cohort,
        "cohort_sha256": "c" * 64,
        "case_ids": case_ids,
        "case_count": 10,
        "candidate_stack_count": 50,
        "cases": cases,
    }
    monkeypatch.setattr(module, "validate_candidate_volume_bundle", lambda _: bundle)
    _write(
        audit_path,
        {
            "schema": module.AUDIT_SCHEMA,
            "status": "retrospective_development_audit_complete",
            "development_only": True,
            "holdout_used": False,
            "inference_executed": False,
            "medgemma_called": False,
            "lesion_masks_used_for_inference": False,
            "lesion_masks_sent_to_medgemma": False,
            "qualified": False,
        },
    )
    return bundle_root, localizer_root, audit_path, bundle


def test_preflight_records_exact_top5_and_stays_non_authorizing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    bundle, localizer, audit, _ = _fixture(tmp_path, monkeypatch)
    output = tmp_path / "new" / "nested" / "preflight.json"
    result = module.write_enhancement_top5_preflight(
        bundle_root=bundle,
        localizer_root=localizer,
        audit_path=audit,
        output_path=output,
    )
    assert result["schema"] == module.PREFLIGHT_SCHEMA
    assert result["candidate_stack_count"] == 50
    assert result["human_review_signed"] is False
    assert result["inference_authorized"] is False
    assert result["labels_read"] is False
    assert output.is_file()


def test_preflight_rejects_legacy_75_percent_selection(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    bundle, localizer, audit, fake = _fixture(tmp_path, monkeypatch)
    fake["cohort"]["protocol"]["candidate_target_fraction"] = 0.75
    with pytest.raises(PipelineError, match="exact-top5"):
        module.validate_enhancement_top5_bundle(
            bundle_root=bundle, localizer_root=localizer, audit_path=audit
        )


def test_preflight_rejects_tampered_localizer_provenance(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    bundle, localizer, audit, _ = _fixture(tmp_path, monkeypatch)
    path = localizer / "anon-openswiss-00" / "localizer_manifest.json"
    path.write_text(path.read_text(encoding="utf-8") + " ", encoding="utf-8")
    with pytest.raises(PipelineError, match="Proveniencia"):
        module.validate_enhancement_top5_bundle(
            bundle_root=bundle, localizer_root=localizer, audit_path=audit
        )


def test_preflight_rejects_holdout_path_before_validation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    bundle, localizer, audit, _ = _fixture(tmp_path, monkeypatch)
    with pytest.raises(PipelineError, match="holdout"):
        module.write_enhancement_top5_preflight(
            bundle_root=bundle,
            localizer_root=localizer,
            audit_path=audit,
            output_path=tmp_path / "holdout" / "preflight.json",
        )
