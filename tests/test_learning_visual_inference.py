from __future__ import annotations

import json

import numpy as np
import pytest

from dtwin.core import PipelineError
from dtwin.learning import visual_inference
from dtwin.learning.medsiglip_multiclass_classifier import BUNDLE_SCHEMA
from dtwin.learning.protocol import canonical_sha256


class _FakeModel:
    """Minimal stand-in for the sklearn Pipeline: 3 classes, class 1 positive."""

    class _clf:
        classes_ = np.array([0, 1, 2])

    named_steps = {"classifier": _clf()}

    def predict_proba(self, matrix):
        matrix = np.asarray(matrix, dtype=float)
        # positive prob rises with the first feature
        pos = 1 / (1 + np.exp(-matrix[:, 0]))
        rest = (1 - pos) / 2
        return np.stack([rest, pos, rest], axis=1)


def _write_bundle(tmp_path, training_case_ids, training_group_ids, threshold=0.5, aggregation="max"):
    import joblib

    root = tmp_path / "bundle"
    root.mkdir(parents=True)
    model_path = root / "production_model.joblib"
    joblib.dump(_FakeModel(), model_path)
    from dtwin.learning.protocol import sha256_file

    body = {
        "schema": BUNDLE_SCHEMA,
        "class_names": ["a", "b", "c"],
        "positive_classes": ["b"],
        "selected_aggregation": aggregation,
        "decision_threshold": threshold,
        "model_sha256": sha256_file(model_path),
        "training_case_ids": sorted(training_case_ids),
        "training_patient_group_ids": sorted(training_group_ids),
    }
    manifest = {**body, "bundle_signature": canonical_sha256(body)}
    (root / "bundle_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return root


def test_load_bundle_rejects_tampered_manifest(tmp_path):
    root = _write_bundle(tmp_path, {"c1"}, {"c1"})
    manifest_path = root / "bundle_manifest.json"
    data = json.loads(manifest_path.read_text())
    data["decision_threshold"] = 0.99  # tamper after signing
    manifest_path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(PipelineError, match="Assinatura do bundle"):
        visual_inference.load_production_bundle(root)


def test_load_bundle_rejects_tampered_model(tmp_path):
    import joblib

    root = _write_bundle(tmp_path, {"c1"}, {"c1"})
    joblib.dump(_FakeModel(), root / "production_model.joblib")  # rewrite -> hash mismatch is unlikely;
    # instead append bytes to guarantee a different hash
    with (root / "production_model.joblib").open("ab") as handle:
        handle.write(b"x")
    with pytest.raises(PipelineError, match="Modelo de produção foi alterado"):
        visual_inference.load_production_bundle(root)


def test_classify_embeddings_uses_positive_mass_aggregation_and_threshold(tmp_path):
    root = _write_bundle(tmp_path, {"c1"}, {"c1"}, threshold=0.5, aggregation="max")
    bundle = visual_inference.load_production_bundle(root)
    # one strongly-positive panel, one negative -> max aggregation -> positive
    embeddings = np.array([[5.0, 0, 0], [-5.0, 0, 0]])
    result = visual_inference.classify_embeddings(bundle, embeddings)
    assert result["prediction"] == "POSITIVE"
    assert result["panel_count"] == 2
    assert result["score"] > 0.5
    # mean aggregation of the same panels sits near 0.5 -> flips with threshold
    root2 = _write_bundle(tmp_path / "b2", {"c1"}, {"c1"}, threshold=0.9, aggregation="mean")
    bundle2 = visual_inference.load_production_bundle(root2)
    assert visual_inference.classify_embeddings(bundle2, embeddings)["prediction"] == "NEGATIVE"


def test_classify_rejects_empty_embeddings(tmp_path):
    root = _write_bundle(tmp_path, {"c1"}, {"c1"})
    bundle = visual_inference.load_production_bundle(root)
    with pytest.raises(PipelineError, match="Embeddings de painel inválidos"):
        visual_inference.classify_embeddings(bundle, np.empty((0, 3)))


def test_in_sample_status_matches_by_case_or_group(tmp_path):
    root = _write_bundle(tmp_path, training_case_ids={"train1"}, training_group_ids={"grp1"})
    bundle = visual_inference.load_production_bundle(root)
    assert visual_inference.in_sample_status(bundle, case_id="train1")["in_sample"] is True
    assert visual_inference.in_sample_status(bundle, case_id="new", patient_group_id="grp1")["in_sample"] is True
    fresh = visual_inference.in_sample_status(bundle, case_id="new", patient_group_id="grpX")
    assert fresh["in_sample"] is False


def test_partition_in_sample_separates_seen_from_unseen(tmp_path):
    root = _write_bundle(tmp_path, training_case_ids={"a", "b"}, training_group_ids={"a", "b"})
    bundle = visual_inference.load_production_bundle(root)
    part = visual_inference.partition_in_sample(
        bundle,
        [{"case_id": "a"}, {"case_id": "z"}, {"case_id": "b"}],
    )
    assert part["in_sample_case_ids"] == ["a", "b"]
    assert part["out_of_sample_case_ids"] == ["z"]
    assert part["any_in_sample"] is True
