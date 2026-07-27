from __future__ import annotations

import json
from pathlib import Path

import pytest

from dtwin.benchmark import openswisshcc_highdimensional_evaluation as evaluation
from dtwin.core import PipelineError


def _label(case_id: str, label: str) -> dict:
    return {
        "schema": "argos-openswisshcc-ground-truth-v1",
        "case_id": case_id,
        "public_subject_id": case_id.replace("anon-", "subject-"),
        "label": label,
        "target_condition": "hcc_presence",
        "label_basis": "public_dataset",
        "review_status": "reviewed",
    }


def _write_labels(
    root: Path,
    rows: list[dict],
    *,
    name: str = "development_labels.jsonl",
) -> Path:
    path = root / "protected_ground_truth" / name
    path.parent.mkdir(parents=True)
    path.write_text(
        "".join(json.dumps(row) + "\n" for row in rows),
        encoding="utf-8",
    )
    return path


def _blind_values(classifications: list[str]):
    case_ids = [
        f"anon-case-{index:02d}" for index in range(len(classifications))
    ]
    bundle = {
        "case_ids": case_ids,
        "bundle_signature": "b" * 64,
    }
    protocol = {
        "model_id": "google/medgemma-1.5-4b-it",
        "protocol_signature": "p" * 64,
    }
    predictions = {
        case_id: {
            "case_id": case_id,
            "classification": classification,
            "stack_manifest_sha256": f"{index:064x}",
            "request_elapsed_seconds": 100.0 + index,
        }
        for index, (case_id, classification) in enumerate(
            zip(case_ids, classifications)
        )
    }
    return bundle, protocol, predictions


def _prepare_inference(root: Path, case_ids: list[str]) -> Path:
    inference = root / "inference"
    (inference / "predictions").mkdir(parents=True)
    (inference / "progress.json").write_text("{}", encoding="utf-8")
    (inference / "summary.json").write_text("{}", encoding="utf-8")
    for case_id in case_ids:
        (inference / "predictions" / f"{case_id}.json").write_text(
            "{}",
            encoding="utf-8",
        )
    return inference


def test_explicit_authorization_is_required_before_any_validation(
    monkeypatch,
    tmp_path,
):
    def forbidden(**_kwargs):
        raise AssertionError("run cego não deveria ser tocado sem autorização")

    monkeypatch.setattr(
        evaluation,
        "validate_blind_highdimensional_run",
        forbidden,
    )
    with pytest.raises(PipelineError, match="autorização explícita"):
        evaluation.evaluate_highdimensional_development(
            bundle_root=tmp_path,
            protocol_path=tmp_path / "protocol.json",
            inference_root=tmp_path / "inference",
            protected_labels_path=tmp_path / "development_labels.jsonl",
            output_dir=tmp_path / "evaluation",
        )


def test_holdout_path_is_always_rejected(tmp_path):
    path = (
        tmp_path
        / "holdout"
        / "protected_ground_truth"
        / "development_labels.jsonl"
    )
    path.parent.mkdir(parents=True)
    path.write_text("", encoding="utf-8")
    with pytest.raises(PipelineError, match="Apenas development_labels"):
        evaluation._load_development_labels(
            path,
            expected_case_ids=[],
            expected_positive=0,
            expected_negative=0,
        )


def test_unauthorized_extra_label_is_rejected(tmp_path):
    path = _write_labels(tmp_path, [
        _label("anon-case-00", "POSITIVE"),
        _label("anon-extra", "NEGATIVE"),
    ])
    with pytest.raises(PipelineError, match="casos extras não autorizados"):
        evaluation._load_development_labels(
            path,
            expected_case_ids=["anon-case-00"],
            expected_positive=1,
            expected_negative=0,
        )


def test_single_explicit_technical_exclusion_is_allowed(tmp_path):
    path = _write_labels(tmp_path, [
        _label("anon-case-00", "POSITIVE"),
        _label("anon-excluded", "NEGATIVE"),
    ])
    labels, _hash = evaluation._load_development_labels(
        path,
        expected_case_ids=["anon-case-00"],
        expected_positive=1,
        expected_negative=0,
        expected_excluded_case_id="anon-excluded",
    )
    assert list(labels) == ["anon-case-00"]


def test_wrong_explicit_technical_exclusion_is_rejected(tmp_path):
    path = _write_labels(tmp_path, [
        _label("anon-case-00", "POSITIVE"),
        _label("anon-excluded", "NEGATIVE"),
    ])
    with pytest.raises(PipelineError, match="casos extras não autorizados"):
        evaluation._load_development_labels(
            path,
            expected_case_ids=["anon-case-00"],
            expected_positive=1,
            expected_negative=0,
            expected_excluded_case_id="anon-other",
        )


def test_excluded_case_cannot_still_belong_to_bundle(tmp_path):
    path = _write_labels(tmp_path, [_label("anon-case-00", "POSITIVE")])
    with pytest.raises(PipelineError, match="ainda pertence ao bundle"):
        evaluation._load_development_labels(
            path,
            expected_case_ids=["anon-case-00"],
            expected_positive=1,
            expected_negative=0,
            expected_excluded_case_id="anon-case-00",
        )


def test_label_class_counts_are_frozen(tmp_path):
    path = _write_labels(tmp_path, [_label("anon-case-00", "POSITIVE")])
    with pytest.raises(PipelineError, match="Contagem protegida inesperada"):
        evaluation._load_development_labels(
            path,
            expected_case_ids=["anon-case-00"],
            expected_positive=0,
            expected_negative=1,
        )


def test_inconclusive_counts_as_primary_error_and_outputs_are_atomic(
    monkeypatch,
    tmp_path,
):
    bundle, protocol, predictions = _blind_values(
        ["POSITIVA", "INCONCLUSIVA", "NEGATIVA", "POSITIVA"]
    )
    monkeypatch.setattr(
        evaluation,
        "validate_blind_highdimensional_run",
        lambda **_kwargs: (bundle, protocol, predictions),
    )
    labels = _write_labels(tmp_path, [
        _label(bundle["case_ids"][0], "POSITIVE"),
        _label(bundle["case_ids"][1], "POSITIVE"),
        _label(bundle["case_ids"][2], "NEGATIVE"),
        _label(bundle["case_ids"][3], "NEGATIVE"),
        _label("anon-excluded", "NEGATIVE"),
    ])
    inference = _prepare_inference(tmp_path, bundle["case_ids"])
    output = tmp_path / "evaluation"
    result = evaluation.evaluate_highdimensional_development(
        bundle_root=tmp_path / "bundle",
        protocol_path=tmp_path / "protocol.json",
        inference_root=inference,
        protected_labels_path=labels,
        output_dir=output,
        allow_protected_development_labels=True,
        expected_case_count=4,
        expected_positive=2,
        expected_negative=2,
        expected_excluded_case_id="anon-excluded",
    )
    primary = result["metrics"]["primary"]
    assert primary["sensitivity"] == 0.5
    assert primary["specificity"] == 0.5
    assert primary["inconclusive_count"] == 1
    assert result["passed"] is False
    assert result["holdout_opened"] is False
    assert result["timing"]["passed"] is True
    assert output.is_dir()
    artifact = json.loads((output / "evaluation.json").read_text(encoding="utf-8"))
    assert artifact["excluded_technical_case_id"] == "anon-excluded"
    assert not list(tmp_path.glob(".evaluation.staging.*"))


def test_gate_passes_only_when_both_metrics_and_time_pass(
    monkeypatch,
    tmp_path,
):
    bundle, protocol, predictions = _blind_values(
        ["POSITIVA", "POSITIVA", "NEGATIVA", "NEGATIVA"]
    )
    monkeypatch.setattr(
        evaluation,
        "validate_blind_highdimensional_run",
        lambda **_kwargs: (bundle, protocol, predictions),
    )
    labels = _write_labels(tmp_path, [
        _label(bundle["case_ids"][0], "POSITIVE"),
        _label(bundle["case_ids"][1], "POSITIVE"),
        _label(bundle["case_ids"][2], "NEGATIVE"),
        _label(bundle["case_ids"][3], "NEGATIVE"),
        _label("anon-excluded", "NEGATIVE"),
    ])
    inference = _prepare_inference(tmp_path, bundle["case_ids"])
    result = evaluation.evaluate_highdimensional_development(
        bundle_root=tmp_path / "bundle",
        protocol_path=tmp_path / "protocol.json",
        inference_root=inference,
        protected_labels_path=labels,
        output_dir=tmp_path / "evaluation",
        allow_protected_development_labels=True,
        expected_case_count=4,
        expected_positive=2,
        expected_negative=2,
        expected_excluded_case_id="anon-excluded",
    )
    assert result["metrics"]["primary"]["sensitivity"] == 1.0
    assert result["metrics"]["primary"]["specificity"] == 1.0
    assert result["passed"] is True


def test_existing_output_is_never_overwritten(monkeypatch, tmp_path):
    output = tmp_path / "evaluation"
    output.mkdir()
    monkeypatch.setattr(
        evaluation,
        "validate_blind_highdimensional_run",
        lambda **_kwargs: (_ for _ in ()).throw(
            AssertionError("não deveria validar")
        ),
    )
    with pytest.raises(PipelineError, match="sobrescrita recusada"):
        evaluation.evaluate_highdimensional_development(
            bundle_root=tmp_path,
            protocol_path=tmp_path / "protocol.json",
            inference_root=tmp_path,
            protected_labels_path=tmp_path / "development_labels.jsonl",
            output_dir=output,
            allow_protected_development_labels=True,
        )

