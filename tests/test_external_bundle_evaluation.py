from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from dtwin.core import PipelineError
from dtwin.learning import external_bundle_evaluation as external
from dtwin.learning.protocol import sha256_file


def _jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )


class _Bundle:
    def __init__(self, training_ids: set[str] | None = None):
        self.manifest = {"bundle_signature": "bundle-signed"}
        self.training_case_ids = set(training_ids or set())
        self.training_patient_group_ids: set[str] = set()


def _prediction_fixture(tmp_path: Path, monkeypatch, *, training_ids: set[str] | None = None):
    candidates = tmp_path / "candidates"
    embeddings = tmp_path / "embeddings"
    candidates.mkdir()
    embeddings.mkdir()
    (candidates / "dataset_manifest.json").write_text(
        json.dumps({"dataset_signature": "candidate-signed"}), encoding="utf-8"
    )
    candidate_rows = [
        {"case_id": "ext-a", "candidate_id": "p1", "dataset_id": "external"},
        {"case_id": "ext-b", "candidate_id": "p1", "dataset_id": "external"},
    ]
    _jsonl(candidates / "candidate_records.jsonl", candidate_rows)
    _jsonl(
        candidates / "technical_failures.jsonl",
        [{"case_id": "ext-c", "failure_reason": "no_panel"}],
    )
    embedding_rows = []
    for index, case_id in enumerate(("ext-a", "ext-b"), 1):
        relative = Path("embeddings") / case_id / "p1.npy"
        path = embeddings / relative
        path.parent.mkdir(parents=True)
        np.save(path, np.asarray([float(index), 0.0], dtype=np.float32), allow_pickle=False)
        embedding_rows.append(
            {
                "case_id": case_id, "candidate_id": "p1", "panel_number": 1,
                "embedding_path": relative.as_posix(),
            }
        )
    _jsonl(embeddings / "embedding_records.jsonl", embedding_rows)
    monkeypatch.setattr(external, "verify_candidate_dataset", lambda **_kwargs: {})
    monkeypatch.setattr(
        external, "verify_embeddings", lambda **_kwargs: {"embedding_signature": "embedding-signed"}
    )
    monkeypatch.setattr(external, "load_production_bundle", lambda _path: _Bundle(training_ids))
    monkeypatch.setattr(
        external,
        "classify_embeddings",
        lambda _bundle, matrix: {
            "prediction": "POSITIVE" if matrix[0, 0] == 1 else "NEGATIVE",
            "score": 0.9 if matrix[0, 0] == 1 else 0.1,
            "threshold": 0.5,
            "panel_count": int(matrix.shape[0]),
        },
    )
    output = tmp_path / "predictions"
    kwargs = dict(
        bundle_root=tmp_path / "bundle", candidate_root=candidates,
        embedding_root=embeddings, protocol_path=tmp_path / "protocol.json",
        splits_path=tmp_path / "splits.json", workspace_root=tmp_path,
        dataset_id="external", failure_case_prefix="ext-", expected_case_count=3,
        output_root=output,
    )
    return kwargs, output


def test_external_predictions_are_label_blind_and_count_failures(monkeypatch, tmp_path):
    kwargs, output = _prediction_fixture(tmp_path, monkeypatch)
    freeze = external.predict_external_bundle(**kwargs)
    rows = [json.loads(line) for line in (output / "predictions.jsonl").read_text().splitlines()]
    assert freeze["case_count"] == 3
    assert freeze["technical_failure_count"] == 1
    assert freeze["training_case_overlap"] == 0
    assert all("label" not in row and "ground_truth" not in row for row in rows)
    assert [row["prediction"] for row in rows] == ["POSITIVE", "NEGATIVE", "TECHNICAL_FAILURE"]


def test_external_prediction_rejects_training_overlap(monkeypatch, tmp_path):
    kwargs, _output = _prediction_fixture(tmp_path, monkeypatch, training_ids={"ext-a"})
    with pytest.raises(PipelineError, match="visto no treino"):
        external.predict_external_bundle(**kwargs)


def test_external_prediction_can_bind_exact_label_blind_case_manifest(monkeypatch, tmp_path):
    kwargs, _output = _prediction_fixture(tmp_path, monkeypatch)
    case_manifest = tmp_path / "holdout_inputs.jsonl"
    _jsonl(case_manifest, [
        {"case_id": case_id, "research_only": True, "ground_truth_read": False,
         "lesion_mask_present": False, "files": []}
        for case_id in ("ext-a", "ext-b", "ext-c")
    ])
    monkeypatch.setattr(external, "_verify_signed_candidate_artifact", lambda *_args: {})
    kwargs["case_manifest_path"] = case_manifest
    freeze = external.predict_external_bundle(**kwargs)
    assert freeze["case_manifest_sha256"] == sha256_file(case_manifest)
    assert freeze["case_count"] == 3


def test_external_prediction_rejects_case_manifest_that_is_not_label_blind(monkeypatch, tmp_path):
    kwargs, _output = _prediction_fixture(tmp_path, monkeypatch)
    case_manifest = tmp_path / "unsafe.jsonl"
    _jsonl(case_manifest, [
        {"case_id": "ext-a", "research_only": True, "ground_truth_read": True,
         "lesion_mask_present": False, "files": []},
    ])
    monkeypatch.setattr(external, "_verify_signed_candidate_artifact", lambda *_args: {})
    kwargs["case_manifest_path"] = case_manifest
    kwargs["expected_case_count"] = 1
    with pytest.raises(PipelineError, match="label-blind"):
        external.predict_external_bundle(**kwargs)


def test_external_evaluation_opens_labels_only_after_valid_freeze(monkeypatch, tmp_path):
    kwargs, prediction_root = _prediction_fixture(tmp_path, monkeypatch)
    external.predict_external_bundle(**kwargs)
    monkeypatch.setattr(external, "load_production_bundle", lambda _path: _Bundle())
    protected = [
        SimpleNamespace(case_id="ext-a", dataset_id="dev", label="POSITIVE"),
        SimpleNamespace(case_id="ext-b", dataset_id="holdout", label="NEGATIVE"),
        SimpleNamespace(case_id="ext-c", dataset_id="dev", label="POSITIVE"),
    ]
    monkeypatch.setattr(external, "load_protected_cases", lambda *_args: protected)
    report = external.evaluate_external_bundle(
        bundle_root=tmp_path / "bundle", prediction_root=prediction_root,
        training_protocol_config_path=tmp_path / "protocol.yaml",
        workspace_root=tmp_path, protected_dataset_ids={"dev", "holdout"},
        output_root=tmp_path / "evaluation",
    )
    assert report["ground_truth_opened_after_predictions_frozen"] is True
    assert report["overall"]["technical_failures"] == 1
    assert report["overall"]["sensitivity"] == 0.5
    assert report["overall"]["specificity"] == 1.0
    assert report["lesion_masks_read"] == 0


def test_external_evaluation_rejects_tampered_predictions(monkeypatch, tmp_path):
    kwargs, prediction_root = _prediction_fixture(tmp_path, monkeypatch)
    external.predict_external_bundle(**kwargs)
    path = prediction_root / "predictions.jsonl"
    path.write_text(path.read_text(encoding="utf-8") + "{}\n", encoding="utf-8")
    with pytest.raises(PipelineError, match="alteradas"):
        external.evaluate_external_bundle(
            bundle_root=tmp_path / "bundle", prediction_root=prediction_root,
            training_protocol_config_path=tmp_path / "protocol.yaml",
            workspace_root=tmp_path, protected_dataset_ids={"dev", "holdout"},
            output_root=tmp_path / "evaluation",
        )
