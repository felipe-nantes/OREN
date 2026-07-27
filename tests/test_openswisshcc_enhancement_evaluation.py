from __future__ import annotations

import json
from pathlib import Path

import pytest

from dtwin.benchmark.openswisshcc_alignment import _sha256
from dtwin.benchmark.openswisshcc_enhancement_evaluation import (
    EVALUATION_SCHEMA,
    evaluate_enhancement_features_development,
)
from dtwin.benchmark.openswisshcc_enhancement_maps import CASE_SCHEMA, COHORT_SCHEMA
from dtwin.core import PipelineError


def _bundle(tmp_path: Path):
    root = tmp_path / "features"
    root.mkdir()
    rows = []
    labels = []
    for index in range(87):
        case_id = f"anon-{index:03d}"
        positive = index < 39
        available = index < 84
        rows.append(
            {
                "schema": CASE_SCHEMA,
                "case_id": case_id,
                "status": "complete_blind_features" if available else "unavailable_unregistered_fallback",
                "features": {"signal": 1.0 if positive else 0.0} if available else None,
            }
        )
        labels.append(
            {
                "schema": "argos-openswisshcc-ground-truth-v1",
                "case_id": case_id,
                "label": "POSITIVE" if positive else "NEGATIVE",
            }
        )
    features_path = root / "features.jsonl"
    features_path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    (root / "summary.json").write_text(
        json.dumps(
            {
                "schema": COHORT_SCHEMA,
                "status": "complete_blind_features_with_declared_fallbacks",
                "case_count": 87,
                "available_case_count": 84,
                "case_ids": [row["case_id"] for row in rows],
                "features_sha256": _sha256(features_path),
                "labels_read": False,
                "ground_truth_lesion_masks_read": 0,
            }
        ),
        encoding="utf-8",
    )
    labels_path = tmp_path / "development_labels.jsonl"
    labels_path.write_text("".join(json.dumps(row) + "\n" for row in labels), encoding="utf-8")
    return root, labels_path


def test_perfect_development_feature_is_reported_but_not_qualified(tmp_path: Path):
    root, labels = _bundle(tmp_path)
    result = evaluate_enhancement_features_development(
        feature_root=root, labels_path=labels, output_dir=tmp_path / "evaluation"
    )
    assert result["schema"] == EVALUATION_SCHEMA
    assert result["best_feature"]["best_direction_auc"] == 1.0
    assert result["best_feature"]["any_apparent_threshold_meets_75_75"] is True
    assert result["continuation_to_medgemma_recommended"] is True
    assert result["qualified"] is False
    assert result["holdout_v21_used_for_selection"] is False
    assert result["ground_truth_lesion_masks_read"] == 0


def test_tampered_feature_bundle_is_rejected(tmp_path: Path):
    root, labels = _bundle(tmp_path)
    with (root / "features.jsonl").open("a", encoding="utf-8") as output:
        output.write("{}\n")
    with pytest.raises(PipelineError, match="adulterado"):
        evaluate_enhancement_features_development(
            feature_root=root, labels_path=labels, output_dir=tmp_path / "evaluation"
        )
