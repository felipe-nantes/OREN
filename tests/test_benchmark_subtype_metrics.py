from dtwin.benchmark.subtype_metrics import (
    SUBTYPE_CLASSES,
    binary_label_for_subtype,
    compute_subtype_metrics,
)


def _row(truth: str, predicted: str | None, status: str = "decisive") -> dict:
    return {
        "truth_subtype": truth,
        "status": status,
        "subtype_determined": predicted is not None,
        "subtype": predicted,
    }


def test_subtype_binary_endpoint_is_pathology_target_not_any_alteration():
    assert binary_label_for_subtype("hcc") == "positive"
    assert binary_label_for_subtype("fnh") == "negative"
    assert binary_label_for_subtype("hemangioma") == "negative"
    assert binary_label_for_subtype("hepatic_cyst") == "negative"


def test_subtype_metrics_compute_balanced_accuracy_and_confusion():
    rows = [
        _row("hcc", "hcc"),
        _row("hcc", "hcc"),
        _row("fnh", "fnh"),
        _row("fnh", "fnh"),
        _row("hemangioma", "hemangioma"),
        _row("hemangioma", "hemangioma"),
        _row("hepatic_cyst", "hepatic_cyst"),
        _row("hepatic_cyst", "hemangioma"),
    ]
    metrics = compute_subtype_metrics(rows)
    assert metrics["top1_accuracy"] == 0.875
    assert metrics["balanced_accuracy"] == 0.875
    assert metrics["per_class"]["hepatic_cyst"]["recall"] == 0.5
    assert metrics["confusion_matrix"]["hepatic_cyst"]["hemangioma"] == 1
    assert metrics["class_coverage_complete"] is True
    assert metrics["target"]["met"] is True
    assert rows[-1]["subtype_correct"] is False


def test_subtype_metrics_penalize_undetermined_inconclusive_and_failure():
    rows = [
        _row("hcc", None),
        _row("fnh", "fnh", status="inconclusive"),
        _row("hemangioma", None, status="failed"),
        _row("hepatic_cyst", "hepatic_cyst"),
    ]
    metrics = compute_subtype_metrics(rows)
    assert metrics["top1_accuracy"] == 0.25
    assert metrics["balanced_accuracy"] == 0.25
    assert metrics["undetermined_cases"] == 3
    assert all(
        metrics["confusion_matrix"][truth]["undetermined"] == 1
        for truth in ("hcc", "fnh", "hemangioma")
    )


def test_subtype_gate_requires_all_four_reference_classes():
    metrics = compute_subtype_metrics([
        _row("hcc", "hcc"),
        _row("fnh", "fnh"),
        _row("hemangioma", "hemangioma"),
    ])
    assert metrics["balanced_accuracy"] == 1.0
    assert metrics["class_coverage_complete"] is False
    assert metrics["target"]["met"] is False
    assert metrics["target"]["reason"] == "missing_reference_classes"
    assert set(metrics["per_class"]) == set(SUBTYPE_CLASSES)


def test_subtype_metrics_reject_missing_or_open_vocabulary_truth():
    for invalid in (None, "adenoma"):
        try:
            compute_subtype_metrics([_row(invalid, "hcc")])  # type: ignore[arg-type]
        except ValueError as exc:
            assert "truth_subtype" in str(exc)
        else:
            raise AssertionError("ground truth inválido deveria ser rejeitado")
