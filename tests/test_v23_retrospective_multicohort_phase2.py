from __future__ import annotations

import json
from pathlib import Path

import pytest

import dtwin.benchmark.v23_retrospective_multicohort_phase2 as subject
from dtwin.core import PipelineError


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )


def _input(case_id: str, schema: str, relative: str) -> dict:
    roles = ["t1_native", "t1_arterial_ttc_1", "t1_venous", "t1_delayed"]
    return {
        "schema": schema,
        "case_id": case_id,
        "research_only": True,
        "clinical_use_allowed": False,
        "files": [
            {
                "role": role,
                "relative_path": f"{relative}/{role}.bin",
                "bytes": 1,
                "sha256": f"{index + 1:064x}",
            }
            for index, role in enumerate(roles)
        ],
    }


def _label(case_id: str, subject_id: str, label: str) -> dict:
    return {
        "schema": "argos-openswisshcc-ground-truth-v1",
        "case_id": case_id,
        "public_subject_id": subject_id,
        "label": label,
        "review_status": "dataset_expert_validated",
    }


def _v11(case_id: str, schema: str) -> dict:
    return {
        "schema": schema,
        "case_id": case_id,
        "ground_truth_read": False,
        "metrics_calculated": False,
        "signals": {
            "medgemma_v4_uncertainty_margin": 0.1,
            "medsiglip_v5_inverse_sagittal": 0.2,
            "localizer_v10_log_volume": 1.0,
        },
    }


def _shape(case_id: str) -> dict:
    return {
        "schema": "argos-openswisshcc-candidate-shape-case-v23",
        "case_id": case_id,
        "ground_truth_read": False,
        "ground_truth_lesion_mask_used": False,
        "features": {"candidate_weighted_linearity": 0.5},
    }


def _fixture(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Path]:
    monkeypatch.setattr(
        subject,
        "verify_retrospective_multicohort_contract",
        lambda **_: {"contract_signature": "c" * 64},
    )
    dev_manifest = tmp_path / "dev/manifests/inputs.jsonl"
    hold_manifest = tmp_path / "hold/manifests/inputs.jsonl"
    cases = ["anon-case-001", "anon-case-002", "anon-case-003", "anon-case-004"]
    dev_rows = [
        _input(cases[0], "argos-public-liver-mri-input-v1", cases[0]),
        _input(cases[1], "argos-public-liver-mri-input-v1", cases[1]),
    ]
    hold_rows = [
        _input(cases[2], "argos-public-liver-mri-holdout-input-v1", cases[2]),
        _input(cases[3], "argos-public-liver-mri-holdout-input-v1", cases[3]),
    ]
    for root, rows in (
        (dev_manifest.parent.parent / "inputs", dev_rows),
        (hold_manifest.parent.parent / "inputs", hold_rows),
    ):
        for row in rows:
            for item in row["files"]:
                path = root / item["relative_path"]
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b"x")
    _write_jsonl(dev_manifest, dev_rows)
    _write_jsonl(hold_manifest, hold_rows)
    dev_labels = tmp_path / "dev_labels.jsonl"
    hold_labels = tmp_path / "hold_labels.jsonl"
    _write_jsonl(
        dev_labels,
        [_label(cases[0], "sub-001", "POSITIVE"), _label(cases[1], "sub-002", "NEGATIVE")],
    )
    _write_jsonl(
        hold_labels,
        [_label(cases[2], "sub-003", "POSITIVE"), _label(cases[3], "sub-004", "NEGATIVE")],
    )
    dev_v11 = tmp_path / "dev_v11.jsonl"
    hold_v11 = tmp_path / "hold_v11.jsonl"
    shapes = tmp_path / "shapes.jsonl"
    _write_jsonl(
        dev_v11,
        [_v11(case_id, "argos-openswisshcc-v20-blind-fusion-signal-v1") for case_id in cases[:2]],
    )
    _write_jsonl(
        hold_v11,
        [_v11(case_id, "argos-public-independent-v21-raw-signals-v1") for case_id in cases[2:]],
    )
    _write_jsonl(shapes, [_shape(case_id) for case_id in cases[:2]])
    contract = tmp_path / "contract.json"
    lock = tmp_path / "lock.json"
    contract.write_text("{}")
    lock.write_text("{}")
    return {
        "contract_path": contract,
        "baseline_lock_path": lock,
        "workspace_root": tmp_path,
        "development_manifest_path": dev_manifest,
        "development_labels_path": dev_labels,
        "holdout_manifest_path": hold_manifest,
        "holdout_labels_path": hold_labels,
        "development_v11_signals_path": dev_v11,
        "holdout_v11_signals_path": hold_v11,
        "development_shape_features_path": shapes,
        "output_dir": tmp_path / "phase2",
    }


def test_repeated_folds_are_deterministic_and_stratified():
    labels = {
        **{f"p-{index}": "POSITIVE" for index in range(10)},
        **{f"n-{index}": "NEGATIVE" for index in range(10)},
    }
    first = subject._stratified_repeated_folds(labels, repeats=3, folds=5, seed=9)
    second = subject._stratified_repeated_folds(labels, repeats=3, folds=5, seed=9)
    assert first == second
    for repeat in range(3):
        for label in ("POSITIVE", "NEGATIVE"):
            counts = [0] * 5
            for case_id, value in labels.items():
                if value == label:
                    counts[first[case_id][repeat]] += 1
            assert counts == [2, 2, 2, 2, 2]


def test_selected_arterial_and_ttc_arterial_are_both_exact_v23_compatible():
    common = ["t1_native", "t1_venous", "t1_delayed"]
    assert subject._has_exact_dynamic_roles([*common, "t1_arterial"]) == (True, [])
    assert subject._has_exact_dynamic_roles([*common, "t1_arterial_ttc_2"]) == (
        True,
        [],
    )


def test_phase2_binds_cases_without_labels_in_public_inventory(monkeypatch, tmp_path):
    kwargs = _fixture(tmp_path, monkeypatch)
    result = subject.build_phase2_openswisshcc_inventory(
        **kwargs, expected_cases=4, expected_positive=2, expected_negative=2
    )
    assert result["case_count"] == 4
    assert result["unique_patient_count"] == 4
    assert result["v11_signals_complete_count"] == 4
    assert result["candidate_weighted_linearity_complete_count"] == 2
    assert result["exact_v23_score_inputs_complete_count"] == 2
    assert result["missing_component_counts"] == {
        "v11": 0,
        "candidate_weighted_linearity": 2,
    }
    assert result["signal_availability_by_split"]["holdout_consumed"][
        "exact_v23_score_inputs_complete_count"
    ] == 0
    inventory = [
        json.loads(line)
        for line in (kwargs["output_dir"] / "case_inventory.jsonl")
        .read_text()
        .splitlines()
    ]
    assert all("label" not in row for row in inventory)
    assert all(row["image_pixels_read"] is False for row in inventory)


def test_phase2_rejects_duplicate_patient(monkeypatch, tmp_path):
    kwargs = _fixture(tmp_path, monkeypatch)
    rows = [
        _label("anon-case-003", "sub-003", "POSITIVE"),
        _label("anon-case-004", "sub-003", "NEGATIVE"),
    ]
    _write_jsonl(kwargs["holdout_labels_path"], rows)
    with pytest.raises(PipelineError, match="pacientes duplicados"):
        subject.build_phase2_openswisshcc_inventory(
            **kwargs, expected_cases=4, expected_positive=2, expected_negative=2
        )


def test_missing_phase_is_recorded_not_fabricated(monkeypatch, tmp_path):
    kwargs = _fixture(tmp_path, monkeypatch)
    rows = [
        json.loads(line)
        for line in kwargs["development_manifest_path"].read_text().splitlines()
    ]
    rows[0]["files"] = [
        item for item in rows[0]["files"] if item["role"] != "t1_delayed"
    ]
    _write_jsonl(kwargs["development_manifest_path"], rows)
    result = subject.build_phase2_openswisshcc_inventory(
        **kwargs, expected_cases=4, expected_positive=2, expected_negative=2
    )
    assert result["all_required_dynamic_phases_available_count"] == 3
    inventory = {
        row["case_id"]: row
        for row in map(
            json.loads,
            (kwargs["output_dir"] / "case_inventory.jsonl").read_text().splitlines(),
        )
    }
    assert inventory["anon-case-001"]["required_dynamic_phases_available"] is False
    assert inventory["anon-case-001"]["missing_required_dynamic_phases"] == ["t1_delayed"]


def test_verify_rejects_inventory_tampering(monkeypatch, tmp_path):
    kwargs = _fixture(tmp_path, monkeypatch)
    subject.build_phase2_openswisshcc_inventory(
        **kwargs, expected_cases=4, expected_positive=2, expected_negative=2
    )
    inventory = kwargs["output_dir"] / "case_inventory.jsonl"
    inventory.write_text(inventory.read_text() + "{}\n")
    with pytest.raises(PipelineError, match="adulterado"):
        subject.verify_phase2_openswisshcc_inventory(
            phase2_root=kwargs["output_dir"],
            contract_path=kwargs["contract_path"],
            baseline_lock_path=kwargs["baseline_lock_path"],
            workspace_root=kwargs["workspace_root"],
            expected_cases=4,
            expected_positive=2,
            expected_negative=2,
        )


def test_verify_rejects_fold_assignment_tampering(monkeypatch, tmp_path):
    kwargs = _fixture(tmp_path, monkeypatch)
    subject.build_phase2_openswisshcc_inventory(
        **kwargs, expected_cases=4, expected_positive=2, expected_negative=2
    )
    folds = kwargs["output_dir"] / "protected_ground_truth/fold_assignments.jsonl"
    rows = [json.loads(line) for line in folds.read_text().splitlines()]
    rows[0]["repeated_5fold_outer_assignments"][0] = 4
    _write_jsonl(folds, rows)
    summary_path = kwargs["output_dir"] / "summary.json"
    summary = json.loads(summary_path.read_text())
    summary["artifacts"]["protected_fold_assignments_sha256"] = subject._sha256(folds)
    unsigned = dict(summary)
    unsigned.pop("phase2_signature")
    summary["phase2_signature"] = subject._canonical_sha(unsigned)
    summary_path.write_text(json.dumps(summary))
    with pytest.raises(PipelineError, match="Estratificação"):
        subject.verify_phase2_openswisshcc_inventory(
            phase2_root=kwargs["output_dir"],
            contract_path=kwargs["contract_path"],
            baseline_lock_path=kwargs["baseline_lock_path"],
            workspace_root=kwargs["workspace_root"],
            expected_cases=4,
            expected_positive=2,
            expected_negative=2,
        )
