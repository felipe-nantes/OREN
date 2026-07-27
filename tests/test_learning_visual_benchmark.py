from __future__ import annotations

import json

import numpy as np
import pytest

from dtwin.core import PipelineError
from dtwin.learning import visual_benchmark
from dtwin.learning.medsiglip_multiclass_classifier import BUNDLE_SCHEMA
from dtwin.learning.protocol import canonical_sha256, sha256_file


class _FakeModel:
    class _clf:
        classes_ = np.array([0, 1])

    named_steps = {"classifier": _clf()}

    def predict_proba(self, matrix):
        pos = 1 / (1 + np.exp(-np.asarray(matrix, dtype=float)[:, 0]))
        return np.stack([1 - pos, pos], axis=1)


def _bundle(tmp_path, training_case_ids):
    import joblib

    root = tmp_path / "bundle"
    root.mkdir(parents=True)
    model_path = root / "production_model.joblib"
    joblib.dump(_FakeModel(), model_path)
    body = {
        "schema": BUNDLE_SCHEMA,
        "candidate_id": "test_bundle",
        "class_names": ["neg", "pos"],
        "positive_classes": ["pos"],
        "selected_aggregation": "max",
        "decision_threshold": 0.5,
        "model_sha256": sha256_file(model_path),
        "training_case_ids": sorted(training_case_ids),
        "training_patient_group_ids": sorted(training_case_ids),
    }
    manifest = {**body, "bundle_signature": canonical_sha256(body)}
    (root / "bundle_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return root


def _case(case_id, label, feature, **extra):
    # feature drives the fake model's positive probability
    base = {
        "case_id": case_id,
        "label": label,
        "phase_paths": {"t1_arterial": "a", "t1_venous": "v", "t1_delayed": "d"},
        "coarse_liver_mask_path": "mask",
        "_feature": feature,
    }
    base.update(extra)
    return base


def _fakes():
    def panel_fn(case_id, phase_paths, mask_path, out_dir):
        return [out_dir / "panel_001.png"]  # not actually read; embed_fn is faked

    # embed_fn returns a vector whose first coord encodes the case's feature,
    # looked up from a closure map set per test
    return panel_fn


def test_out_of_sample_only_in_headline_and_in_sample_separated(tmp_path):
    bundle_root = _bundle(tmp_path, training_case_ids={"seen1"})
    cases = [
        _case("seen1", "POSITIVE", 5.0),   # in-sample, correct
        _case("new_pos", "POSITIVE", 5.0),  # out-of-sample, correct
        _case("new_neg", "NEGATIVE", -5.0),  # out-of-sample, correct
    ]
    feature_by_case = {c["case_id"]: c["_feature"] for c in cases}

    def embed_fn(panel_paths):
        # derive feature from the output dir name (case_id) embedded in path
        case_id = Path_str = str(panel_paths[0]).replace("\\", "/").split("/")[-2]
        return np.array([[feature_by_case[case_id]]])

    from pathlib import Path

    def panel_fn(case_id, phase_paths, mask_path, out_dir):
        Path(out_dir).mkdir(parents=True, exist_ok=True)
        return [Path(out_dir) / "panel_001.png"]

    report = visual_benchmark.run_visual_benchmark(
        bundle_root=bundle_root, cases=cases, work_dir=tmp_path / "work",
        panel_config_path="unused", embedding_config_path="unused",
        panel_fn=panel_fn, embed_fn=embed_fn,
    )
    assert report["in_sample_count"] == 1
    assert report["out_of_sample_count"] == 2
    # headline out-of-sample: 1 pos + 1 neg both correct
    oos = report["out_of_sample_metrics"]
    assert oos["sensitivity"] == 1.0 and oos["specificity"] == 1.0
    # in-sample reported separately and flagged
    assert report["in_sample_metrics_inflated_do_not_report_as_generalization"] is not None
    assert "in-sample" in report["warning"]


def test_case_failure_becomes_technical_error_not_fabricated_decision(tmp_path):
    bundle_root = _bundle(tmp_path, training_case_ids=set())
    cases = [_case("boom", "POSITIVE", 5.0)]

    def panel_fn(case_id, phase_paths, mask_path, out_dir):
        raise RuntimeError("render exploded")

    def embed_fn(panel_paths):  # never reached
        return np.array([[0.0]])

    report = visual_benchmark.run_visual_benchmark(
        bundle_root=bundle_root, cases=cases, work_dir=tmp_path / "work",
        panel_config_path="unused", embedding_config_path="unused",
        panel_fn=panel_fn, embed_fn=embed_fn,
    )
    row = report["cases"][0]
    assert row["technical_failure"] is True
    assert row["prediction"] == "TECHNICAL_FAILURE"
    assert "render exploded" in row["error"]
    # counted as an error on the positive axis
    assert report["out_of_sample_metrics"]["fn"] == 1


def test_all_in_sample_has_no_out_of_sample_headline(tmp_path):
    bundle_root = _bundle(tmp_path, training_case_ids={"a", "b"})
    cases = [_case("a", "POSITIVE", 5.0), _case("b", "NEGATIVE", -5.0)]

    def panel_fn(case_id, phase_paths, mask_path, out_dir):
        from pathlib import Path

        Path(out_dir).mkdir(parents=True, exist_ok=True)
        return [Path(out_dir) / "p.png"]

    def embed_fn(panel_paths):
        case_id = str(panel_paths[0]).replace("\\", "/").split("/")[-2]
        return np.array([[5.0 if case_id == "a" else -5.0]])

    report = visual_benchmark.run_visual_benchmark(
        bundle_root=bundle_root, cases=cases, work_dir=tmp_path / "work",
        panel_config_path="unused", embedding_config_path="unused",
        panel_fn=panel_fn, embed_fn=embed_fn,
    )
    assert report["out_of_sample_metrics"] is None
    assert report["out_of_sample_count"] == 0
    assert report["warning"] is not None


def test_empty_cases_rejected(tmp_path):
    bundle_root = _bundle(tmp_path, training_case_ids=set())
    with pytest.raises(PipelineError, match="ao menos um caso"):
        visual_benchmark.run_visual_benchmark(
            bundle_root=bundle_root, cases=[], work_dir=tmp_path,
            panel_config_path="x", embedding_config_path="y",
        )
