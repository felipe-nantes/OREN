from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import SimpleITK as sitk

from dtwin.benchmark.liver_segmentation_comparison import evaluate, segmentation_metrics
from dtwin.core import PipelineError


def _sphere(shape=(20, 22, 24), center=(10, 11, 12), radius=6):
    zz, yy, xx = np.indices(shape)
    return ((zz - center[0]) ** 2 + (yy - center[1]) ** 2 + (xx - center[2]) ** 2) <= radius**2


def _write(path: Path, values: np.ndarray, spacing=(1.0, 1.2, 2.0)):
    path.parent.mkdir(parents=True, exist_ok=True)
    image = sitk.GetImageFromArray(values)
    image.SetSpacing(spacing)
    sitk.WriteImage(image, str(path), useCompression=True)


def test_perfect_segmentation_metrics_are_exact():
    mask = _sphere()
    metrics = segmentation_metrics(mask, mask, (1.0, 1.2, 2.0))
    assert metrics["dice"] == 1.0
    assert metrics["jaccard"] == 1.0
    assert metrics["precision"] == 1.0
    assert metrics["recall"] == 1.0
    assert metrics["volume_ratio"] == 1.0
    assert metrics["hd95_mm"] == 0.0
    assert metrics["assd_mm"] == 0.0


def test_shifted_segmentation_has_surface_and_overlap_penalty():
    reference = _sphere()
    prediction = np.roll(reference, 2, axis=2)
    metrics = segmentation_metrics(prediction, reference, (1.0, 1.0, 1.0))
    assert 0.0 < metrics["dice"] < 1.0
    assert metrics["hd95_mm"] > 0.0
    assert metrics["assd_mm"] > 0.0


def test_multiclass_prediction_uses_configured_liver_label(tmp_path):
    repo = tmp_path
    case = repo / "cohort" / "anon-labelmap"
    source = np.zeros((20, 22, 24), dtype=np.float32)
    liver = _sphere().astype(np.uint8)
    labelmap = np.zeros_like(liver)
    labelmap[liver > 0] = 5
    labelmap[0:4, 0:4, 0:4] = 2
    _write(case / "source.nii.gz", source)
    _write(case / "reference.nii.gz", liver)
    _write(repo / "predictions" / "anon-labelmap.nii.gz", labelmap)
    config = repo / "config.yaml"
    config.write_text(
        """schema: argos-liver-segmentation-benchmark-config-v2
research_only: true
cohort: {id: labelmap, root: cohort, source_name: source.nii.gz, reference_name: reference.nii.gz, ground_truth_used_only_after_prediction: true}
models:
  - id: multiclass
    required: true
    label_value: 5
    mask_template: "predictions/{case_id}.nii.gz"
output: {root: experiments/result, generate_gallery: false}
""",
        encoding="utf-8",
    )
    result = evaluate(config, repo=repo)
    assert result["models"]["multiclass"]["median_dice"] == 1.0


def test_evaluator_generates_results_and_gallery_without_touching_cases(tmp_path):
    repo = tmp_path
    cohort = repo / "cohort"
    predictions = repo / "predictions"
    for index in range(2):
        case_id = f"anon-test-{index}"
        case = cohort / case_id
        source = np.random.default_rng(index).normal(size=(20, 22, 24)).astype(np.float32)
        reference = _sphere(center=(10, 11, 11 + index)).astype(np.uint8)
        _write(case / "source.nii.gz", source)
        _write(case / "reference.nii.gz", reference)
        _write(predictions / f"{case_id}.nii.gz", reference)
    config = repo / "config.yaml"
    config.write_text(
        """schema: argos-liver-segmentation-benchmark-config-v2
research_only: true
cohort:
  id: synthetic
  root: cohort
  source_name: source.nii.gz
  reference_name: reference.nii.gz
  ground_truth_used_only_after_prediction: true
models:
  - id: perfect
    display_name: Perfect
    color: '#00FF00'
    required: true
    mask_template: predictions/{case_id}.nii.gz
  - id: absent_optional
    display_name: Absent
    required: false
    mask_template: missing/{case_id}.nii.gz
output:
  root: experiments/result
  generate_gallery: true
""",
        encoding="utf-8",
    )

    result = evaluate(config, repo=repo)

    assert result["case_count"] == 2
    assert result["models"]["perfect"]["median_dice"] == 1.0
    assert result["models"]["absent_optional"]["evaluated_cases"] == 0
    assert (repo / "experiments/result/gallery/index.html").is_file()
    assert len(list((repo / "experiments/result/gallery/images").glob("*.png"))) == 2
    assert not (cohort / "anon-test-0" / "evaluation.json").exists()


def test_required_prediction_missing_fails_closed(tmp_path):
    cohort = tmp_path / "cohort" / "anon-test"
    values = _sphere().astype(np.uint8)
    _write(cohort / "source.nii.gz", values.astype(np.float32))
    _write(cohort / "reference.nii.gz", values)
    config = tmp_path / "config.yaml"
    config.write_text(
        """schema: argos-liver-segmentation-benchmark-config-v2
research_only: true
cohort: {id: synthetic, root: cohort, source_name: source.nii.gz, reference_name: reference.nii.gz, ground_truth_used_only_after_prediction: true}
models:
  - {id: required, required: true, mask_template: "missing/{case_id}.nii.gz"}
output: {root: experiments/result, generate_gallery: false}
""",
        encoding="utf-8",
    )
    with pytest.raises(PipelineError, match="obrigatoria"):
        evaluate(config, repo=tmp_path)


def test_evaluator_refuses_overwrite(tmp_path):
    output = tmp_path / "experiments/result"
    output.mkdir(parents=True)
    config = tmp_path / "config.yaml"
    config.write_text(
        """schema: argos-liver-segmentation-benchmark-config-v2
research_only: true
cohort: {id: x, root: cohort, source_name: source.nii.gz, reference_name: reference.nii.gz, ground_truth_used_only_after_prediction: true}
models: [{id: x, required: false, mask_template: "p/{case_id}.nii.gz"}]
output: {root: experiments/result, generate_gallery: false}
""",
        encoding="utf-8",
    )
    (tmp_path / "cohort").mkdir()
    with pytest.raises(PipelineError, match="sobrescrita"):
        evaluate(config, repo=tmp_path)
