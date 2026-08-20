"""Retrospective development evaluation of v11 plus candidate shape.

The hypothesis was selected after development labels had already been opened.
Consequently this module can reproduce and audit the result, but it can never
qualify the final system or authorize reuse of the consumed v21 holdout.
"""
from __future__ import annotations

import csv
import json
import math
import random
import shutil
import statistics
import uuid
from pathlib import Path
from typing import Any

from dtwin.benchmark.openswisshcc_alignment import _publish_directory, _sha256
from dtwin.benchmark.openswisshcc_candidate_shape import CASE_SCHEMA, COHORT_SCHEMA
from dtwin.benchmark.openswisshcc_lesion_localizer_evaluation import (
    _load_development_labels,
)
from dtwin.benchmark.openswisshcc_localizer_roi_evaluation import _wilson
from dtwin.benchmark.openswisshcc_v20_fusion import (
    V11_WEIGHTS,
    _canonical_sha,
    _ecdf,
    verify_fusion_protocol,
)
from dtwin.benchmark.openswisshcc_volumetric_evaluation import (
    _best_threshold,
    _binary_metrics,
)
from dtwin.core import PipelineError
from dtwin.medgemma_screening import _write_json_atomic

EVALUATION_SCHEMA = "argos-openswisshcc-v23-shape-fusion-development-evaluation-v1"
CALIBRATOR_SCHEMA = "argos-openswisshcc-v23-shape-fusion-calibrator-v1"
PRIMARY_SHAPE_FEATURE = "candidate_weighted_linearity"
SHAPE_WEIGHT = 0.20
V11_WEIGHT = 0.80
REPEATS = 50
FOLDS = 5
RANDOM_SEED = 20260720


def _validated_calibrator(value: dict[str, Any]) -> dict[str, Any]:
    signature = value.get("calibrator_signature")
    unsigned = dict(value)
    unsigned.pop("calibrator_signature", None)
    references = value.get("ecdf_references")
    if (
        value.get("schema") != CALIBRATOR_SCHEMA
        or value.get("status") != "frozen_for_new_independent_external_validation"
        or signature != _canonical_sha(unsigned)
        or value.get("primary_shape_feature") != PRIMARY_SHAPE_FEATURE
        or value.get("weights") != {"v11": V11_WEIGHT, PRIMARY_SHAPE_FEATURE: SHAPE_WEIGHT}
        or not isinstance(value.get("decision_threshold"), (int, float))
        or isinstance(value.get("decision_threshold"), bool)
        or not math.isfinite(float(value["decision_threshold"]))
        or not isinstance(references, dict)
        or set(references) != {*V11_WEIGHTS, PRIMARY_SHAPE_FEATURE}
        or value.get("hypothesis_selected_after_development_labels") is not True
        or value.get("independent_balanced_validation_required") is not True
        or value.get("holdout_v21_reuse_forbidden") is not True
        or value.get("qualified") is not False
        or value.get("research_only") is not True
        or value.get("clinical_use_allowed") is not False
    ):
        raise PipelineError("Calibrador v23 ausente, adulterado ou inseguro.")
    expected_count = int(value.get("development_reference_count", 0))
    for name, reference in references.items():
        if (
            not isinstance(reference, list)
            or len(reference) != expected_count
            or any(
                isinstance(item, bool)
                or not isinstance(item, (int, float))
                or not math.isfinite(float(item))
                for item in reference
            )
            or reference != sorted(reference)
        ):
            raise PipelineError(f"Referencia ECDF v23 invalida: {name}.")
    return value


def score_with_frozen_calibrator(
    calibrator: dict[str, Any], *, signals: dict[str, float], weighted_linearity: float
) -> dict[str, Any]:
    """Score one unseen case without labels using frozen development references."""

    value = _validated_calibrator(calibrator)
    if set(signals) != set(V11_WEIGHTS):
        raise PipelineError("Sinais v11 externos incompletos para v23.")
    numeric = {name: float(signals[name]) for name in V11_WEIGHTS}
    shape = float(weighted_linearity)
    if (
        any(not math.isfinite(item) for item in numeric.values())
        or not math.isfinite(shape)
        or not 0.0 <= shape <= 1.0
    ):
        raise PipelineError("Sinal externo v23 invalido.")
    references = value["ecdf_references"]
    v11 = sum(
        V11_WEIGHTS[name] * _ecdf(numeric[name], references[name])
        for name in V11_WEIGHTS
    )
    score = V11_WEIGHT * v11 + SHAPE_WEIGHT * _ecdf(
        shape, references[PRIMARY_SHAPE_FEATURE]
    )
    threshold = float(value["decision_threshold"])
    return {
        "score": float(score),
        "threshold": threshold,
        "prediction": "POSITIVE" if score >= threshold else "NEGATIVE",
        "calibrator_signature": value["calibrator_signature"],
    }


def _load_json(path: Path, description: str) -> dict[str, Any]:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PipelineError(f"{description} ausente ou invalido.") from exc
    if not isinstance(value, dict):
        raise PipelineError(f"{description} deve ser objeto JSON.")
    return value


def _load_shape_bundle(shape_root: Path, case_ids: list[str]) -> tuple[dict[str, Any], dict[str, float]]:
    root = Path(shape_root).resolve()
    summary_path = root / "summary.json"
    features_path = root / "features.jsonl"
    summary = _load_json(summary_path, "Resumo geometrico v23")
    try:
        rows = [
            json.loads(line)
            for line in features_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    except (OSError, json.JSONDecodeError) as exc:
        raise PipelineError("Features geometricas v23 ausentes ou invalidas.") from exc
    if (
        summary.get("schema") != COHORT_SCHEMA
        or summary.get("status") != "complete_blind_shape_features"
        or summary.get("case_count") != len(case_ids)
        or summary.get("case_ids") != case_ids
        or summary.get("features_sha256") != _sha256(features_path)
        or summary.get("labels_read") is not False
        or summary.get("ground_truth_lesion_masks_read") != 0
        or summary.get("inference_executed") is not False
        or summary.get("research_only") is not True
        or summary.get("clinical_use_allowed") is not False
        or len(rows) != len(case_ids)
    ):
        raise PipelineError("Bundle geometrico v23 violou hashes ou salvaguardas.")
    values: dict[str, float] = {}
    for expected_id, row in zip(case_ids, rows, strict=True):
        feature = row.get("features", {}).get(PRIMARY_SHAPE_FEATURE)
        if (
            row.get("schema") != CASE_SCHEMA
            or row.get("case_id") != expected_id
            or row.get("status") != "complete_blind_shape_features"
            or row.get("ground_truth_read") is not False
            or row.get("ground_truth_lesion_mask_used") is not False
            or row.get("inference_executed") is not False
            or row.get("research_only") is not True
            or row.get("clinical_use_allowed") is not False
            or isinstance(feature, bool)
            or not isinstance(feature, (int, float))
            or not math.isfinite(float(feature))
            or not 0.0 <= float(feature) <= 1.0
        ):
            raise PipelineError(f"Feature geometrica v23 invalida: {expected_id}.")
        values[expected_id] = float(feature)
    return summary, values


def _fusion_scores(
    rows: list[dict[str, Any]],
    shape_values: list[float],
    train: list[int],
    score_indices: list[int],
) -> list[float]:
    references = {
        name: [float(rows[index]["signals"][name]) for index in train]
        for name in V11_WEIGHTS
    }
    shape_reference = [shape_values[index] for index in train]
    return [
        V11_WEIGHT
        * sum(
            V11_WEIGHTS[name]
            * _ecdf(float(rows[index]["signals"][name]), references[name])
            for name in V11_WEIGHTS
        )
        + SHAPE_WEIGHT * _ecdf(shape_values[index], shape_reference)
        for index in score_indices
    ]


def _loocv(rows: list[dict[str, Any]], shapes: list[float], truth: list[bool]) -> dict[str, Any]:
    predictions: list[bool] = []
    thresholds: list[float] = []
    scores: list[float] = []
    for held_out in range(len(rows)):
        train = [index for index in range(len(rows)) if index != held_out]
        threshold, _ = _best_threshold(
            _fusion_scores(rows, shapes, train, train),
            [truth[index] for index in train],
        )
        score = _fusion_scores(rows, shapes, train, [held_out])[0]
        predictions.append(score >= threshold)
        thresholds.append(float(threshold))
        scores.append(float(score))
    return {
        **_binary_metrics(truth, predictions),
        "thresholds": thresholds,
        "scores": scores,
        "predictions": predictions,
    }


def _repeated(rows: list[dict[str, Any]], shapes: list[float], truth: list[bool]) -> dict[str, Any]:
    positive = [index for index, value in enumerate(truth) if value]
    negative = [index for index, value in enumerate(truth) if not value]
    if min(len(positive), len(negative)) < FOLDS:
        raise PipelineError("Coorte v23 insuficiente para validacao estratificada.")
    outcomes = []
    for repeat in range(REPEATS):
        rng = random.Random(RANDOM_SEED + repeat)
        pos, neg = positive[:], negative[:]
        rng.shuffle(pos)
        rng.shuffle(neg)
        groups = [[] for _ in range(FOLDS)]
        for index, item in enumerate(pos):
            groups[index % FOLDS].append(item)
        for index, item in enumerate(neg):
            groups[index % FOLDS].append(item)
        predicted = [False] * len(rows)
        for test_indices in groups:
            test = set(test_indices)
            train = [index for index in range(len(rows)) if index not in test]
            threshold, _ = _best_threshold(
                _fusion_scores(rows, shapes, train, train),
                [truth[index] for index in train],
            )
            for index, score in zip(
                test_indices,
                _fusion_scores(rows, shapes, train, test_indices),
                strict=True,
            ):
                predicted[index] = score >= threshold
        outcomes.append(_binary_metrics(truth, predicted))
    return {
        "repeats": REPEATS,
        "folds": FOLDS,
        "seed": RANDOM_SEED,
        "transform_and_threshold_fit_inside_each_training_fold": True,
        "runs_passing_75_75": sum(bool(item["passed_75_75"]) for item in outcomes),
        "median_sensitivity": statistics.median(float(item["sensitivity"]) for item in outcomes),
        "median_specificity": statistics.median(float(item["specificity"]) for item in outcomes),
        "minimum_sensitivity": min(float(item["sensitivity"]) for item in outcomes),
        "minimum_specificity": min(float(item["specificity"]) for item in outcomes),
    }


def evaluate_shape_fusion_development(
    *,
    v20_bundle_root: Path,
    v20_protocol_path: Path,
    shape_root: Path,
    labels_path: Path,
    output_dir: Path,
    allow_protected_development_labels: bool = False,
    expected_case_count: int = 87,
) -> dict[str, Any]:
    if allow_protected_development_labels is not True:
        raise PipelineError("Abertura dos labels de desenvolvimento v23 nao autorizada.")
    labels_path = Path(labels_path).resolve()
    if labels_path.name != "development_labels.jsonl" or any(
        "holdout" in part.lower() for part in labels_path.parts
    ):
        raise PipelineError("Avaliador v23 aceita somente development_labels.jsonl.")
    protocol, rows = verify_fusion_protocol(
        bundle_root=v20_bundle_root,
        protocol_path=v20_protocol_path,
        expected_case_count=expected_case_count,
    )
    case_ids = [str(row["case_id"]) for row in rows]
    shape_summary, shape_by_id = _load_shape_bundle(shape_root, case_ids)
    labels, labels_hash = _load_development_labels(labels_path, case_ids)
    truth = [labels[case_id]["label"] == "POSITIVE" for case_id in case_ids]
    shapes = [shape_by_id[case_id] for case_id in case_ids]
    primary = _loocv(rows, shapes, truth)
    repeated = _repeated(rows, shapes, truth)
    point_gate = bool(primary["sensitivity"] >= 0.75 and primary["specificity"] >= 0.75)
    robust_gate = bool(repeated["runs_passing_75_75"] == REPEATS)
    result = {
        "schema": EVALUATION_SCHEMA,
        "status": "retrospective_development_signal_promising_not_independently_validated",
        "case_count": len(case_ids),
        "positive_count": sum(truth),
        "negative_count": len(truth) - sum(truth),
        "primary_feature": PRIMARY_SHAPE_FEATURE,
        "weights": {"v11": V11_WEIGHT, PRIMARY_SHAPE_FEATURE: SHAPE_WEIGHT},
        "primary_loocv_metrics": {
            key: value
            for key, value in primary.items()
            if key not in {"scores", "predictions"}
        },
        "primary_loocv_confidence_intervals": {
            "sensitivity_95": _wilson(primary["tp"], primary["tp"] + primary["fn"]),
            "specificity_95": _wilson(primary["tn"], primary["tn"] + primary["fp"]),
        },
        "repeated_stratified_5fold": repeated,
        "development_point_gate_passed": point_gate,
        "development_robustness_gate_passed": robust_gate,
        "hypothesis_selected_after_development_labels": True,
        "selection_bias_possible": True,
        "independent_balanced_validation_required": True,
        "holdout_v21_reuse_forbidden": True,
        "final_system_qualification_claimed": False,
        "qualified": False,
        "source_hashes": {
            "v20_protocol": _sha256(Path(v20_protocol_path).resolve()),
            "v20_bundle_summary": _sha256(Path(v20_bundle_root).resolve() / "summary.json"),
            "shape_summary": _sha256(Path(shape_root).resolve() / "summary.json"),
            "shape_features": shape_summary["features_sha256"],
            "development_labels": labels_hash,
        },
        "ground_truth_read": True,
        "lesion_masks_read": False,
        "holdout_opened": False,
        "research_only": True,
        "clinical_use_allowed": False,
        "requires_human_review": True,
    }
    output = Path(output_dir).resolve()
    if output.exists():
        raise PipelineError("Avaliacao v23 ja existe; sobrescrita recusada.")
    output.parent.mkdir(parents=True, exist_ok=True)
    staging = output.parent / f"._v23eval_{uuid.uuid4().hex[:8]}"
    staging.mkdir()
    try:
        _write_json_atomic(staging / "evaluation.json", result)
        with (staging / "case_scores.csv").open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=["case_id", "label", PRIMARY_SHAPE_FEATURE, "loocv_score", "loocv_threshold", "prediction"],
            )
            writer.writeheader()
            for index, case_id in enumerate(case_ids):
                writer.writerow(
                    {
                        "case_id": case_id,
                        "label": labels[case_id]["label"],
                        PRIMARY_SHAPE_FEATURE: shapes[index],
                        "loocv_score": primary["scores"][index],
                        "loocv_threshold": primary["thresholds"][index],
                        "prediction": "POSITIVE" if primary["predictions"][index] else "NEGATIVE",
                    }
                )
        _publish_directory(staging, output)
        return result
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def freeze_shape_fusion_calibrator(
    *,
    v20_bundle_root: Path,
    v20_protocol_path: Path,
    shape_root: Path,
    labels_path: Path,
    output_path: Path,
    allow_protected_development_labels: bool = False,
    expected_case_count: int = 87,
) -> dict[str, Any]:
    """Freeze the already-selected v23 hypothesis for a genuinely new cohort."""

    if allow_protected_development_labels is not True:
        raise PipelineError("Congelamento v23 exige autorizacao dos labels de desenvolvimento.")
    labels_path = Path(labels_path).resolve()
    if labels_path.name != "development_labels.jsonl" or any(
        "holdout" in part.lower() for part in labels_path.parts
    ):
        raise PipelineError("Calibrador v23 aceita somente development_labels.jsonl.")
    protocol, rows = verify_fusion_protocol(
        bundle_root=v20_bundle_root,
        protocol_path=v20_protocol_path,
        expected_case_count=expected_case_count,
    )
    case_ids = [str(row["case_id"]) for row in rows]
    shape_summary, shape_by_id = _load_shape_bundle(shape_root, case_ids)
    labels, labels_hash = _load_development_labels(labels_path, case_ids)
    truth = [labels[case_id]["label"] == "POSITIVE" for case_id in case_ids]
    shapes = [shape_by_id[case_id] for case_id in case_ids]
    indices = list(range(len(rows)))
    scores = _fusion_scores(rows, shapes, indices, indices)
    threshold, apparent = _best_threshold(scores, truth)
    references = {
        name: sorted(float(row["signals"][name]) for row in rows)
        for name in V11_WEIGHTS
    }
    references[PRIMARY_SHAPE_FEATURE] = sorted(shapes)
    base = {
        "schema": CALIBRATOR_SCHEMA,
        "status": "frozen_for_new_independent_external_validation",
        "development_reference_count": len(rows),
        "development_positive_count": sum(truth),
        "development_negative_count": len(truth) - sum(truth),
        "primary_shape_feature": PRIMARY_SHAPE_FEATURE,
        "weights": {"v11": V11_WEIGHT, PRIMARY_SHAPE_FEATURE: SHAPE_WEIGHT},
        "transform": "frozen_development_ecdf_midrank_n_denominator",
        "threshold_selection": "maximize_minimum_sensitivity_specificity_then_balanced_accuracy_on_full_development",
        "decision_threshold": float(threshold),
        "development_apparent_metrics_not_external_validation": apparent,
        "ecdf_references": references,
        "hypothesis_selected_after_development_labels": True,
        "selection_bias_possible": True,
        "independent_balanced_validation_required": True,
        "holdout_v21_reuse_forbidden": True,
        "mac_27b_requires_separate_reader_calibration": True,
        "source_hashes": {
            "v20_protocol": _sha256(Path(v20_protocol_path).resolve()),
            "v20_bundle_summary": _sha256(Path(v20_bundle_root).resolve() / "summary.json"),
            "shape_summary": _sha256(Path(shape_root).resolve() / "summary.json"),
            "shape_features": shape_summary["features_sha256"],
            "development_labels": labels_hash,
        },
        "ground_truth_read": True,
        "lesion_masks_read": False,
        "holdout_opened": False,
        "final_system_qualification_claimed": False,
        "qualified": False,
        "research_only": True,
        "clinical_use_allowed": False,
        "requires_human_review": True,
    }
    calibrator = dict(base)
    calibrator["calibrator_signature"] = _canonical_sha(base)
    _validated_calibrator(calibrator)
    output_path = Path(output_path).resolve()
    if output_path.exists():
        if _load_json(output_path, "Calibrador v23 existente") != calibrator:
            raise PipelineError("Calibrador v23 existente diverge; sobrescrita recusada.")
        return calibrator
    output_path.parent.mkdir(parents=True, exist_ok=True)
    _write_json_atomic(output_path, calibrator)
    return calibrator


__all__ = [
    "CALIBRATOR_SCHEMA",
    "PRIMARY_SHAPE_FEATURE",
    "SHAPE_WEIGHT",
    "V11_WEIGHT",
    "evaluate_shape_fusion_development",
    "freeze_shape_fusion_calibrator",
    "score_with_frozen_calibrator",
    "_fusion_scores",
    "_loocv",
]
