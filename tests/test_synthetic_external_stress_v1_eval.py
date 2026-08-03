import json

from dtwin.benchmark.synthetic_external_stress_v1_eval import (
    _canonicalize_identical_checkpoint_duplicates,
    summarize_records,
)


def _row(expected, predicted, binary_expected, binary_prediction, failure=False):
    return {
        "expected_model_class": expected,
        "predicted_model_class": predicted,
        "binary_expected": binary_expected,
        "binary_prediction": binary_prediction,
        "technical_failure": failure,
    }


def test_summary_keeps_construction_metrics_explicit_and_counts_failures_as_errors():
    classes = [
        "fnh", "hcc", "hemangioma", "hepatic_cyst",
        "negative_unspecified", "positive_unspecified",
    ]
    rows = [
        _row("fnh", "fnh", "NEGATIVE", "NEGATIVE"),
        _row("hcc", "hcc", "POSITIVE", "POSITIVE"),
        _row("hemangioma", "hcc", "NEGATIVE", "POSITIVE"),
        _row("hepatic_cyst", "hepatic_cyst", "NEGATIVE", "NEGATIVE"),
        _row("negative_unspecified", None, "NEGATIVE", None, failure=True),
    ]
    report = summarize_records(rows, classes)
    binary = report["binary_technical_metrics"]
    assert binary["tp"] == 1
    assert binary["tn"] == 2
    assert binary["fp"] == 2
    assert binary["fn"] == 0
    assert binary["technical_failures"] == 1
    assert report["by_expected_class"]["fnh"]["recall_on_construction_labels"] == 1.0
    assert report["subtype_confusion_on_construction_labels"]["negative_unspecified"]["technical_failure"] == 1
    assert report["lesion_subtype_balanced_accuracy_on_construction_labels"] == 0.75


def test_checkpoint_recovery_collapses_only_identical_duplicates(tmp_path):
    checkpoint = tmp_path / "checkpoint.jsonl"
    rows = [
        {"case_id": "a", "prediction": "NEGATIVE"},
        {"case_id": "a", "prediction": "NEGATIVE"},
        {"case_id": "b", "prediction": "POSITIVE"},
    ]
    checkpoint.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows), encoding="utf-8"
    )
    canonical = _canonicalize_identical_checkpoint_duplicates(
        checkpoint,
        rows,
        protocol_signature="protocol",
        recovery_path=tmp_path / "recovery.json",
    )
    assert [row["case_id"] for row in canonical] == ["a", "b"]
    assert len(checkpoint.read_text(encoding="utf-8").splitlines()) == 2
    recovery = json.loads((tmp_path / "recovery.json").read_text(encoding="utf-8"))
    assert recovery["source_row_count"] == 3
    assert recovery["canonical_row_count"] == 2
    assert recovery["conflicting_duplicate_count"] == 0
