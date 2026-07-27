from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
import SimpleITK as sitk

from dtwin.benchmark.openswisshcc_alignment import _sha256
from dtwin.benchmark.openswisshcc_enhancement_localizer import (
    ALGORITHM_VERSION,
    CASE_SCHEMA,
    COHORT_SCHEMA,
    THRESHOLDS,
)
from dtwin.benchmark.openswisshcc_enhancement_localizer_audit import (
    AUDIT_SCHEMA,
    audit_enhancement_localizer,
)
from dtwin.core import PipelineError


def _json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def _mask(path: Path, array: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    image = sitk.GetImageFromArray(array.astype(np.uint8))
    image.SetSpacing((1.0, 1.0, 1.0))
    sitk.WriteImage(image, str(path), True)


def _proposal_array() -> np.ndarray:
    value = np.zeros((12, 12, 20), dtype=np.uint8)
    # Six 2x2x2 components, ordered by their connected-component identifier.
    for x in (1, 4, 7, 10, 13, 16):
        value[1:3, 1:3, x : x + 2] = 1
    return value


def _fixture(tmp_path: Path) -> tuple[Path, Path, Path]:
    proposal_root = tmp_path / "development_proposals"
    extraction_root = tmp_path / "development_masks"
    labels_path = tmp_path / "development_labels.jsonl"
    case_ids = ["anon-openswiss-a", "anon-openswiss-b", "anon-openswiss-c", "anon-openswiss-d"]
    labels = ["POSITIVE", "POSITIVE", "NEGATIVE", "NEGATIVE"]
    labels_path.write_text(
        "".join(
            json.dumps({"schema": "argos-openswisshcc-ground-truth-v1", "case_id": case_id, "label": label})
            + "\n"
            for case_id, label in zip(case_ids, labels, strict=True)
        ),
        encoding="utf-8",
    )

    proposal = _proposal_array()
    manifest_hashes: dict[str, str] = {}
    for case_id in case_ids[:3]:
        case_root = proposal_root / case_id
        records = []
        for threshold in THRESHOLDS:
            key = f"t{int(threshold)}"
            path = case_root / f"joint_enhancement_proposals_{key}.nii.gz"
            _mask(path, proposal)
            records.append(
                {
                    "threshold_key": key,
                    "threshold": float(threshold),
                    "filename": path.name,
                    "bytes": path.stat().st_size,
                    "sha256": _sha256(path),
                    "raw_voxels": int(proposal.sum()),
                    "proposal_voxels": int(proposal.sum()),
                    "proposal_volume_mm3": float(proposal.sum()),
                    "component_count": 6,
                    "largest_component_voxels": 8,
                    "largest_component_mm3": 8.0,
                }
            )
        manifest = {
            "schema": CASE_SCHEMA,
            "case_id": case_id,
            "algorithm_version": ALGORITHM_VERSION,
            "dynamic_alignment_mode": "registered_to_venous",
            "ground_truth_read": False,
            "ground_truth_lesion_mask_used": False,
            "metrics_calculated": False,
            "final_decision": None,
            "research_only": True,
            "clinical_use_allowed": False,
            "requires_human_review": True,
            "status": "complete_blind_proposals",
            "analysis_mask_voxels": 1000,
            "normalization": {},
            "proposals": records,
            "source_hashes": {},
            "elapsed_seconds": 0.1,
        }
        manifest_path = case_root / "manifest.json"
        _json(manifest_path, manifest)
        manifest_hashes[case_id] = _sha256(manifest_path)

    summary = {
        "schema": COHORT_SCHEMA,
        "status": "complete_blind_proposals_with_declared_fallbacks",
        "algorithm_version": ALGORITHM_VERSION,
        "case_count": 4,
        "available_case_count": 3,
        "unavailable_case_ids": [case_ids[3]],
        "case_ids": case_ids,
        "thresholds": list(THRESHOLDS),
        "minimum_component_voxels": 8,
        "case_manifest_hashes": manifest_hashes,
        "max_case_seconds": 0.1,
        "labels_read": False,
        "ground_truth_lesion_masks_read": 0,
        "inference_executed": False,
        "research_only": True,
        "clinical_use_allowed": False,
        "requires_human_review": True,
    }
    _json(proposal_root / "summary.json", summary)

    lesion_a = np.zeros_like(proposal)
    lesion_a[1, 1, 1] = 1
    lesion_b = np.zeros_like(proposal)
    lesion_b[1, 1, 16] = 1
    mask_records = []
    for case_id, lesion in ((case_ids[0], lesion_a), (case_ids[1], lesion_b)):
        relative = f"{case_id}/L1_t1_venous_seg.nii.gz"
        path = extraction_root / relative
        _mask(path, lesion)
        mask_records.append(
            {
                "case_id": case_id,
                "lesion_id": "L1",
                "archive_member": f"public/{case_id}/L1.nii.gz",
                "relative_path": relative,
                "bytes": path.stat().st_size,
                "sha256": _sha256(path),
            }
        )
    _json(
        extraction_root / "extraction_manifest.json",
        {
            "schema": "argos-openswisshcc-v16-authorized-mask-extraction-v1",
            "protocol_signature": "test",
            "mask_count": len(mask_records),
            "masks": mask_records,
        },
    )
    return proposal_root, labels_path, extraction_root


def test_audit_reports_all_and_top5_recall_without_diagnostic_claim(tmp_path: Path) -> None:
    proposals, labels, extraction = _fixture(tmp_path)
    output = tmp_path / "audit"
    result = audit_enhancement_localizer(
        proposal_root=proposals,
        labels_path=labels,
        authorized_extraction_root=extraction,
        output_root=output,
        expected_case_count=4,
    )
    assert result["schema"] == AUDIT_SCHEMA
    assert result["available_positive_count"] == 2
    assert result["available_negative_count"] == 1
    assert result["positive_cases_with_venous_masks"] == 2
    assert result["venous_lesion_count"] == 2
    all_t3 = next(row for row in result["metrics"] if row["threshold_key"] == "t3" and row["selection"] == "all")
    top5_t3 = next(row for row in result["metrics"] if row["threshold_key"] == "t3" and row["selection"] == "top5")
    assert all_t3["case_recall"] == 1.0
    assert all_t3["lesion_recall"] == 1.0
    assert top5_t3["case_recall"] == 0.5
    assert top5_t3["lesion_recall"] == 0.5
    assert result["interpretation"]["specificity_claimed"] is False
    assert result["lesion_masks_used_for_inference"] is False
    assert result["medgemma_called"] is False
    assert (output / "audit.json").is_file()
    assert (output / "case_metrics.csv").is_file()
    assert (output / "report.md").is_file()


def test_audit_rejects_tampered_proposal_hash(tmp_path: Path) -> None:
    proposals, labels, extraction = _fixture(tmp_path)
    path = proposals / "anon-openswiss-a" / "joint_enhancement_proposals_t3.nii.gz"
    path.write_bytes(path.read_bytes() + b"tampered")
    with pytest.raises(PipelineError, match="adulterado"):
        audit_enhancement_localizer(
            proposal_root=proposals,
            labels_path=labels,
            authorized_extraction_root=extraction,
            output_root=tmp_path / "audit",
            expected_case_count=4,
        )


def test_audit_rejects_any_holdout_path(tmp_path: Path) -> None:
    proposals, labels, extraction = _fixture(tmp_path)
    with pytest.raises(PipelineError, match="holdout"):
        audit_enhancement_localizer(
            proposal_root=proposals,
            labels_path=labels,
            authorized_extraction_root=extraction,
            output_root=tmp_path / "holdout" / "audit",
            expected_case_count=4,
        )


def test_audit_ignores_declared_labels_outside_frozen_cohort(tmp_path: Path) -> None:
    proposals, labels, extraction = _fixture(tmp_path)
    with labels.open("a", encoding="utf-8") as handle:
        handle.write(
            json.dumps(
                {
                    "schema": "argos-openswisshcc-ground-truth-v1",
                    "case_id": "anon-openswiss-technically-excluded",
                    "label": "POSITIVE",
                }
            )
            + "\n"
        )
    result = audit_enhancement_localizer(
        proposal_root=proposals,
        labels_path=labels,
        authorized_extraction_root=extraction,
        output_root=tmp_path / "audit",
        expected_case_count=4,
    )
    assert result["labels_outside_frozen_cohort_ignored"] == [
        "anon-openswiss-technically-excluded"
    ]
