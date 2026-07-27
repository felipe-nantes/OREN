from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pytest
import SimpleITK as sitk

import dtwin.benchmark.v23_retrospective_multicohort_phase3 as subject
from dtwin.core import PipelineError


def _jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )


def _v11(case_id: str, schema: str) -> dict:
    return {
        "schema": schema,
        "case_id": case_id,
        "ground_truth_read": False,
        "metrics_calculated": False,
        "signals": {
            "medgemma_v4_uncertainty_margin": 0.1,
            "medsiglip_v5_inverse_sagittal": 0.2,
            "localizer_v10_log_volume": 1.2,
        },
    }


def _shape(case_id: str, value: float = 0.4) -> dict:
    return {
        "schema": "argos-openswisshcc-candidate-shape-case-v23",
        "case_id": case_id,
        "status": "complete_blind_shape_features",
        "ground_truth_read": False,
        "ground_truth_lesion_mask_used": False,
        "features": {"candidate_weighted_linearity": value},
    }


def test_v11_loader_keeps_only_exact_v11_signals(tmp_path):
    dev, hold = tmp_path / "dev.jsonl", tmp_path / "hold.jsonl"
    row = _v11("anon-a", "argos-openswisshcc-v20-blind-fusion-signal-v1")
    row["signals"]["post_label_extra"] = 999
    _jsonl(dev, [row])
    _jsonl(
        hold,
        [_v11("anon-b", "argos-public-independent-v21-raw-signals-v1")],
    )
    result = subject._validated_v11_rows(dev, hold)
    assert set(result["anon-a"]) == {
        "medgemma_v4_uncertainty_margin",
        "medsiglip_v5_inverse_sagittal",
        "localizer_v10_log_volume",
    }


def test_v11_loader_rejects_ground_truth_leak(tmp_path):
    row = _v11("anon-a", "argos-openswisshcc-v20-blind-fusion-signal-v1")
    row["ground_truth_read"] = True
    _jsonl(tmp_path / "dev", [row])
    _jsonl(
        tmp_path / "hold",
        [_v11("anon-b", "argos-public-independent-v21-raw-signals-v1")],
    )
    with pytest.raises(PipelineError, match="inválido"):
        subject._validated_v11_rows(tmp_path / "dev", tmp_path / "hold")


def test_alignment_contract_requires_exact_partition(tmp_path):
    path = tmp_path / "alignment.json"
    path.write_text(
        json.dumps(
            {
                "schema": subject.ALIGNMENT_SUMMARY_SCHEMA,
                "status": "complete_label_blind_alignment_with_declared_fallbacks",
                "case_count": 2,
                "labels_read": False,
                "lesion_masks_read": 0,
                "alignments": [{"case_id": "anon-a", "sha256": "a" * 64}],
                "technical_fallbacks": [
                    {
                        "case_id": "anon-b",
                        "fallback": "venous_single_phase",
                        "reason": "gate",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    aligned, _, fallbacks = subject._alignment_contract(
        path, ["anon-a", "anon-b"]
    )
    assert aligned == {"anon-a"}
    assert fallbacks == {"anon-b": "gate"}


def test_alignment_contract_rejects_case_in_both_groups(tmp_path):
    path = tmp_path / "alignment.json"
    path.write_text(
        json.dumps(
            {
                "schema": subject.ALIGNMENT_SUMMARY_SCHEMA,
                "status": "complete_label_blind_alignment_with_declared_fallbacks",
                "case_count": 1,
                "labels_read": False,
                "lesion_masks_read": 0,
                "alignments": [{"case_id": "anon-a", "sha256": "a" * 64}],
                "technical_fallbacks": [
                    {
                        "case_id": "anon-a",
                        "fallback": "venous_single_phase",
                        "reason": "gate",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(PipelineError, match="não cobrem exatamente"):
        subject._alignment_contract(path, ["anon-a"])


def test_saved_candidate_shape_is_reproducible(tmp_path):
    array = np.zeros((7, 8, 9), dtype=np.uint8)
    array[1:6, 2:5, 2:7] = 1
    image = sitk.GetImageFromArray(array)
    image.SetSpacing((1.1, 1.2, 2.0))
    path = tmp_path / "mask.nii.gz"
    subject._save_mask(array, image, path)
    first = subject.compute_candidate_shape_features(image)
    second = subject.compute_candidate_shape_features(sitk.ReadImage(str(path)))
    assert set(first["features"]) == set(second["features"])
    for name in first["features"]:
        assert float(first["features"][name]) == pytest.approx(
            float(second["features"][name]), rel=1e-6
        )


def test_safe_declared_file_rehashes_content(tmp_path):
    path = tmp_path / "case/venous.bin"
    path.parent.mkdir()
    path.write_bytes(b"safe")
    item = {
        "role": "t1_venous",
        "relative_path": "case/venous.bin",
        "bytes": 4,
        "sha256": hashlib.sha256(b"safe").hexdigest(),
    }
    assert subject._safe_declared_file(tmp_path, item) == path.resolve()
    path.write_bytes(b"evil")
    with pytest.raises(PipelineError, match="adulterado"):
        subject._safe_declared_file(tmp_path, item)


def test_safe_declared_file_rejects_lesion_input(tmp_path):
    item = {
        "role": "lesion_mask",
        "relative_path": "mask.nii.gz",
        "bytes": 1,
        "sha256": "a" * 64,
    }
    with pytest.raises(PipelineError, match="proibida"):
        subject._safe_declared_file(tmp_path, item)


def test_development_shapes_reject_out_of_range_linearity(tmp_path):
    path = tmp_path / "shape.jsonl"
    _jsonl(path, [_shape("anon-a", 1.1)])
    with pytest.raises(PipelineError, match="inválida"):
        subject._validated_development_shapes(path)


def test_phase3_summary_signature_detects_tampering(monkeypatch, tmp_path):
    phase3 = tmp_path / "phase3"
    phase3.mkdir()
    _jsonl(
        phase3 / "exact_v23_signals.jsonl",
        [
            {
                "schema": subject.SIGNAL_SCHEMA,
                "case_id": "anon-a",
                "status": "complete_exact_v23_score_inputs",
                "v11_signals": {
                    "medgemma_v4_uncertainty_margin": 0.1,
                    "medsiglip_v5_inverse_sagittal": 0.2,
                    "localizer_v10_log_volume": 1.0,
                },
                "candidate_weighted_linearity": 0.3,
                "ground_truth_read": False,
                "metrics_calculated": False,
            }
        ],
    )
    _jsonl(
        phase3 / "holdout_shape_features.jsonl",
        [{"case_id": "placeholder"}],
    )
    _jsonl(
        phase3 / "technical_failures.jsonl",
        [{"case_id": "placeholder"}],
    )
    artifacts = {
        name: f"{name}.jsonl"
        for name in ("exact_v23_signals", "holdout_shape_features", "technical_failures")
    }
    artifacts.update(
        {
            f"{name}_sha256": subject._sha256(phase3 / f"{name}.jsonl")
            for name in ("exact_v23_signals", "holdout_shape_features", "technical_failures")
        }
    )
    body = {
        "schema": subject.SUMMARY_SCHEMA,
        "status": "phase3_exact_v23_signal_matrix_complete_with_explicit_failures",
        "phase2_signature": "2" * 64,
        "case_count": 1,
        "exact_v23_signal_count": 1,
        "technical_failure_count": 0,
        "holdout_shape_generated_count": 0,
        "artifacts": artifacts,
        "safety": {"labels_read": False, "lesion_masks_read": 0},
    }
    summary = {**body, "phase3_signature": subject._canonical_sha(body)}
    (phase3 / "summary.json").write_text(json.dumps(summary), encoding="utf-8")
    monkeypatch.setattr(
        subject,
        "verify_phase2_openswisshcc_inventory",
        lambda **_: {"phase2_signature": "2" * 64},
    )
    summary["case_count"] = 2
    (phase3 / "summary.json").write_text(json.dumps(summary), encoding="utf-8")
    with pytest.raises(PipelineError, match="adulterado"):
        subject.verify_phase3_exact_v23_signals(
            phase3_root=phase3,
            phase2_root=tmp_path,
            contract_path=tmp_path,
            baseline_lock_path=tmp_path,
            workspace_root=tmp_path,
            expected_cases=1,
        )
