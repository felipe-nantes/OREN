"""Nested recalibration of frozen OpenSwissHCC v23-v26 signals.

The outer held-out patient is never used to fit feature scaling, logistic
coefficients, regularization strength, or the decision threshold.  Prediction
artifacts contain no ground-truth labels and are frozen before final metrics
are calculated.
"""
from __future__ import annotations

import hashlib
import json
import math
import random
import shutil
import statistics
import uuid
from pathlib import Path
from typing import Any

import numpy as np

from dtwin.benchmark.openswisshcc_alignment import _publish_directory
from dtwin.benchmark.openswisshcc_v20_fusion import _canonical_sha
from dtwin.benchmark.openswisshcc_volumetric_evaluation import _best_threshold
from dtwin.benchmark.v23_retrospective_multicohort_phase2 import FOLDS, REPEATS
from dtwin.benchmark.v23_retrospective_multicohort_phase4 import (
    _bootstrap,
    _confusion,
    _fold_rows,
    _roc_auc,
)
from dtwin.core import PipelineError


PROTOCOL_SCHEMA = "argos-openswisshcc-v27-nested-recalibration-protocol-v1"
PREDICTION_SCHEMA = "argos-openswisshcc-v27-nested-recalibration-prediction-v1"
FREEZE_SCHEMA = "argos-openswisshcc-v27-nested-recalibration-freeze-v1"
EVALUATION_SCHEMA = "argos-openswisshcc-v27-nested-recalibration-evaluation-v1"
INNER_FOLDS = 5
INNER_SEED = 20260724
RIDGE_GRID = (0.01, 0.1, 1.0, 10.0, 100.0)
PRIMARY_FAMILY = "all_frozen_signals"

V23_FEATURES = (
    "v23_localizer_log_volume",
    "v23_medgemma_uncertainty_margin",
    "v23_medsiglip_inverse_sagittal",
    "v23_candidate_weighted_linearity",
)
RUN_SUMMARY_FEATURES = (
    "max_positive_probability",
    "mean_positive_probability",
    "std_positive_probability",
    "mean_positive_negative_margin",
    "positive_panel_fraction",
)
PATHOLOGY_FEATURES = (
    "suspicious_panel_fraction",
    "benign_variant_panel_fraction",
    "artifact_panel_fraction",
)
FAMILIES = {
    "v23_core": V23_FEATURES,
    "v23_plus_v24_liver_enriched": V23_FEATURES
    + tuple(f"v24_{name}" for name in RUN_SUMMARY_FEATURES),
    "v23_plus_v25_pathology_target": V23_FEATURES
    + tuple(f"v25_{name}" for name in RUN_SUMMARY_FEATURES + PATHOLOGY_FEATURES),
    "v23_plus_v26_pathology_target_rag": V23_FEATURES
    + tuple(f"v26_{name}" for name in RUN_SUMMARY_FEATURES + PATHOLOGY_FEATURES),
    PRIMARY_FAMILY: V23_FEATURES
    + tuple(f"v24_{name}" for name in RUN_SUMMARY_FEATURES)
    + tuple(f"v25_{name}" for name in RUN_SUMMARY_FEATURES + PATHOLOGY_FEATURES)
    + tuple(f"v26_{name}" for name in RUN_SUMMARY_FEATURES + PATHOLOGY_FEATURES),
}


def _load(path: Path, description: str) -> dict[str, Any]:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PipelineError(f"{description} ausente ou inválido.") from exc
    if not isinstance(value, dict):
        raise PipelineError(f"{description} deve ser objeto JSON.")
    return value


def _jsonl(path: Path, description: str) -> list[dict[str, Any]]:
    try:
        rows = [
            json.loads(line)
            for line in Path(path).read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    except (OSError, json.JSONDecodeError) as exc:
        raise PipelineError(f"{description} ausente ou inválido.") from exc
    if not rows or any(not isinstance(row, dict) for row in rows):
        raise PipelineError(f"{description} deve conter objetos JSONL.")
    return rows


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with Path(path).open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
    except OSError as exc:
        raise PipelineError(f"Artefato ausente: {path}.") from exc
    return digest.hexdigest()


def _write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text(
        "".join(
            json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n"
            for row in rows
        ),
        encoding="utf-8",
    )


def _code_path(workspace_root: Path) -> Path:
    return (
        Path(workspace_root).resolve()
        / "dtwin/benchmark/openswisshcc_v27_nested_recalibration.py"
    )


def freeze_protocol(
    *,
    phase3_root: Path,
    v24_root: Path,
    v25_root: Path,
    v26_root: Path,
    workspace_root: Path,
    output_path: Path,
) -> dict[str, Any]:
    sources = {
        "phase3_exact_v23_signals": Path(phase3_root) / "exact_v23_signals.jsonl",
        "phase3_technical_failures": Path(phase3_root) / "technical_failures.jsonl",
        "v24_cases": Path(v24_root) / "cases.jsonl",
        "v25_cases": Path(v25_root) / "cases.jsonl",
        "v26_cases": Path(v26_root) / "cases.jsonl",
    }
    body = {
        "schema": PROTOCOL_SCHEMA,
        "status": "frozen_before_nested_prediction_generation",
        "candidate_id": "v27_nested_recalibration_of_frozen_v23_v26_signals",
        "primary_family": PRIMARY_FAMILY,
        "feature_families": {key: list(value) for key, value in FAMILIES.items()},
        "model": "class_balanced_l2_logistic_regression_newton_v1",
        "preprocessing": "outer_training_mean_std_only",
        "regularization_grid": list(RIDGE_GRID),
        "inner_validation": {
            "folds": INNER_FOLDS,
            "seed": INNER_SEED,
            "selection_order": [
                "maximum_minimum_of_sensitivity_and_specificity",
                "maximum_balanced_accuracy",
                "stronger_regularization",
            ],
            "threshold_fit": "pooled_inner_oof_predictions_only",
        },
        "outer_validation": {
            "primary": "patient_level_loocv",
            "robustness": f"{REPEATS}x{FOLDS}_fold_assignments_already_frozen",
        },
        "technical_failures_count_as_errors": True,
        "acceptance": {
            "loocv_sensitivity_minimum": 0.75,
            "loocv_specificity_minimum": 0.75,
            "must_improve_minimum_axis_over_v23": True,
            "repeated_validation_report_required": True,
        },
        "source_hashes": {key: _sha256(value) for key, value in sources.items()},
        "evaluation_code_sha256": _sha256(_code_path(workspace_root)),
        "labels_used_only_inside_training_and_final_evaluator": True,
        "held_out_label_use_forbidden": True,
        "lesion_masks_read": 0,
        "research_only": True,
        "clinical_use_allowed": False,
    }
    protocol = {**body, "protocol_signature": _canonical_sha(body)}
    destination = Path(output_path).resolve()
    if destination.exists():
        raise PipelineError("Protocolo v27 já existe.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    _write_json(destination, protocol)
    return protocol


def verify_protocol(
    *,
    protocol_path: Path,
    phase3_root: Path,
    v24_root: Path,
    v25_root: Path,
    v26_root: Path,
    workspace_root: Path,
) -> dict[str, Any]:
    protocol = _load(protocol_path, "Protocolo v27")
    unsigned = dict(protocol)
    signature = unsigned.pop("protocol_signature", None)
    expected_sources = {
        "phase3_exact_v23_signals": _sha256(
            Path(phase3_root) / "exact_v23_signals.jsonl"
        ),
        "phase3_technical_failures": _sha256(
            Path(phase3_root) / "technical_failures.jsonl"
        ),
        "v24_cases": _sha256(Path(v24_root) / "cases.jsonl"),
        "v25_cases": _sha256(Path(v25_root) / "cases.jsonl"),
        "v26_cases": _sha256(Path(v26_root) / "cases.jsonl"),
    }
    if (
        protocol.get("schema") != PROTOCOL_SCHEMA
        or signature != _canonical_sha(unsigned)
        or protocol.get("primary_family") != PRIMARY_FAMILY
        or protocol.get("feature_families")
        != {key: list(value) for key, value in FAMILIES.items()}
        or protocol.get("regularization_grid") != list(RIDGE_GRID)
        or protocol.get("source_hashes") != expected_sources
        or protocol.get("evaluation_code_sha256") != _sha256(_code_path(workspace_root))
        or protocol.get("held_out_label_use_forbidden") is not True
        or protocol.get("lesion_masks_read") != 0
    ):
        raise PipelineError("Protocolo v27 divergiu do código ou dos sinais congelados.")
    return protocol


def _finite_probability(value: Any, description: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise PipelineError(f"{description} inválida.")
    result = float(value)
    if not math.isfinite(result) or not 0.0 <= result <= 1.0:
        raise PipelineError(f"{description} fora de [0, 1].")
    return result


def _report_features(run_root: Path, case_row: dict[str, Any], prefix: str) -> dict[str, float]:
    case_id = case_row.get("case_id")
    if not isinstance(case_id, str):
        raise PipelineError("Caso de inferência sem case_id.")
    report_path = Path(run_root) / case_id / "medgemma_report.json"
    if _sha256(report_path) != case_row.get("report_sha256"):
        raise PipelineError(f"Hash do relatório divergiu em {case_id}.")
    report = _load(report_path, f"Relatório {case_id}")
    panels = report.get("panel_reports")
    if not isinstance(panels, list) or len(panels) != 3:
        raise PipelineError(f"Relatório {case_id} não contém três painéis.")
    positives: list[float] = []
    negatives: list[float] = []
    positive_count = suspicious = benign = artifact = 0
    for panel in panels:
        probabilities = panel.get("choice_probabilities")
        panel_report = panel.get("report")
        if not isinstance(probabilities, dict) or not isinstance(panel_report, dict):
            raise PipelineError(f"Painel inválido em {case_id}.")
        positive = _finite_probability(
            probabilities.get("POSITIVA"), f"Probabilidade positiva {case_id}"
        )
        negative = _finite_probability(
            probabilities.get("NEGATIVA"), f"Probabilidade negativa {case_id}"
        )
        positives.append(positive)
        negatives.append(negative)
        positive_count += panel_report.get("resultado_hipotese") == "POSITIVA"
        suspicious += panel_report.get("ha_lesao_focal_suspeita") is True
        benign += panel_report.get("ha_variante_anatomica_benigna") is True
        artifact += panel_report.get("ha_pseudolesao_ou_artefato") is True
    result = {
        f"{prefix}_max_positive_probability": max(positives),
        f"{prefix}_mean_positive_probability": statistics.fmean(positives),
        f"{prefix}_std_positive_probability": statistics.pstdev(positives),
        f"{prefix}_mean_positive_negative_margin": statistics.fmean(
            positive - negative for positive, negative in zip(positives, negatives)
        ),
        f"{prefix}_positive_panel_fraction": positive_count / len(panels),
        f"{prefix}_suspicious_panel_fraction": suspicious / len(panels),
        f"{prefix}_benign_variant_panel_fraction": benign / len(panels),
        f"{prefix}_artifact_panel_fraction": artifact / len(panels),
    }
    if not all(math.isfinite(value) for value in result.values()):
        raise PipelineError(f"Features não finitas em {case_id}.")
    return result


def _run_features(run_root: Path, prefix: str) -> dict[str, dict[str, float]]:
    rows = _jsonl(Path(run_root) / "cases.jsonl", f"Casos {prefix}")
    result: dict[str, dict[str, float]] = {}
    for row in rows:
        case_id = row.get("case_id")
        if (
            not isinstance(case_id, str)
            or case_id in result
            or row.get("labels_read") is not False
            or row.get("lesion_masks_read") != 0
            or row.get("status") != "success_pending_analysis"
        ):
            raise PipelineError(f"Registro congelado inválido em {prefix}.")
        result[case_id] = _report_features(run_root, row, prefix)
    if len(result) != 130:
        raise PipelineError(f"{prefix} não cobre os 130 casos computáveis.")
    return result


def _feature_matrix(
    *,
    phase3_root: Path,
    v24_root: Path,
    v25_root: Path,
    v26_root: Path,
) -> tuple[dict[str, dict[str, float]], set[str]]:
    features: dict[str, dict[str, float]] = {}
    for row in _jsonl(
        Path(phase3_root) / "exact_v23_signals.jsonl", "Sinais v23"
    ):
        case_id = row.get("case_id")
        v11 = row.get("v11_signals")
        if not isinstance(case_id, str) or case_id in features or not isinstance(v11, dict):
            raise PipelineError("Sinal v23 inválido.")
        values = {
            "v23_localizer_log_volume": v11.get("localizer_v10_log_volume"),
            "v23_medgemma_uncertainty_margin": v11.get(
                "medgemma_v4_uncertainty_margin"
            ),
            "v23_medsiglip_inverse_sagittal": v11.get(
                "medsiglip_v5_inverse_sagittal"
            ),
            "v23_candidate_weighted_linearity": row.get(
                "candidate_weighted_linearity"
            ),
        }
        if any(
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(float(value))
            for value in values.values()
        ):
            raise PipelineError(f"Sinal v23 não finito em {case_id}.")
        features[case_id] = {key: float(value) for key, value in values.items()}
    failures = {
        row["case_id"]
        for row in _jsonl(
            Path(phase3_root) / "technical_failures.jsonl", "Falhas v23"
        )
    }
    runs = (
        _run_features(v24_root, "v24"),
        _run_features(v25_root, "v25"),
        _run_features(v26_root, "v26"),
    )
    if len(features) != 130 or any(set(run) != set(features) for run in runs):
        raise PipelineError("Casos computáveis divergem entre v23-v26.")
    expected = set(FAMILIES[PRIMARY_FAMILY])
    for case_id in features:
        for run in runs:
            features[case_id].update(
                {
                    key: value
                    for key, value in run[case_id].items()
                    if key in expected
                }
            )
    if any(set(row) != expected for row in features.values()):
        raise PipelineError("Matriz v27 possui features ausentes ou extras.")
    if len(failures) != 2 or features.keys() & failures:
        raise PipelineError("Partição v27 deve conter 130 sinais e duas falhas.")
    return features, failures


def _sigmoid(values: np.ndarray) -> np.ndarray:
    clipped = np.clip(values, -35.0, 35.0)
    return 1.0 / (1.0 + np.exp(-clipped))


def _fit_scaler(matrix: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    mean = matrix.mean(axis=0)
    scale = matrix.std(axis=0)
    scale = np.where(scale < 1e-12, 1.0, scale)
    return mean, scale


def _fit_logistic(
    matrix: np.ndarray, truth: np.ndarray, ridge: float
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    mean, scale = _fit_scaler(matrix)
    standardized = (matrix - mean) / scale
    design = np.column_stack([np.ones(len(standardized)), standardized])
    weights = np.zeros(design.shape[1], dtype=float)
    positives = max(int(truth.sum()), 1)
    negatives = max(len(truth) - positives, 1)
    sample_weight = np.where(truth == 1, 0.5 / positives, 0.5 / negatives)
    penalty = np.diag([0.0] + [float(ridge)] * (design.shape[1] - 1))
    for _ in range(80):
        probabilities = _sigmoid(design @ weights)
        gradient = design.T @ (sample_weight * (probabilities - truth)) + penalty @ weights
        variance = sample_weight * probabilities * (1.0 - probabilities)
        hessian = design.T @ (design * variance[:, None]) + penalty
        hessian += np.eye(hessian.shape[0]) * 1e-9
        step = np.linalg.solve(hessian, gradient)
        weights -= step
        if float(np.max(np.abs(step))) < 1e-9:
            break
    if not np.all(np.isfinite(weights)):
        raise PipelineError("Ajuste logístico v27 não convergiu.")
    return weights, mean, scale


def _predict_logistic(
    matrix: np.ndarray,
    fitted: tuple[np.ndarray, np.ndarray, np.ndarray],
) -> np.ndarray:
    weights, mean, scale = fitted
    standardized = (matrix - mean) / scale
    design = np.column_stack([np.ones(len(standardized)), standardized])
    return _sigmoid(design @ weights)


def _inner_assignments(
    case_ids: list[str], labels: dict[str, bool]
) -> dict[str, int]:
    result: dict[str, int] = {}
    for truth in (False, True):
        group = [case_id for case_id in case_ids if labels[case_id] is truth]
        group.sort(
            key=lambda case_id: hashlib.sha256(
                f"{INNER_SEED}|{case_id}".encode("utf-8")
            ).hexdigest()
        )
        for index, case_id in enumerate(group):
            result[case_id] = index % INNER_FOLDS
    if len(result) != len(case_ids):
        raise PipelineError("Partição interna v27 incompleta.")
    return result


def _matrix(
    features: dict[str, dict[str, float]],
    case_ids: list[str],
    names: tuple[str, ...],
) -> np.ndarray:
    return np.asarray(
        [[features[case_id][name] for name in names] for case_id in case_ids],
        dtype=float,
    )


def _select_hyperparameters(
    *,
    features: dict[str, dict[str, float]],
    labels: dict[str, bool],
    training_ids: list[str],
    feature_names: tuple[str, ...],
) -> tuple[float, float, dict[str, Any]]:
    assignments = _inner_assignments(training_ids, labels)
    candidates: list[tuple[float, float, float, float, dict[str, Any]]] = []
    for ridge in RIDGE_GRID:
        oof: dict[str, float] = {}
        for fold in range(INNER_FOLDS):
            inner_train = [
                case_id for case_id in training_ids if assignments[case_id] != fold
            ]
            inner_test = [
                case_id for case_id in training_ids if assignments[case_id] == fold
            ]
            fitted = _fit_logistic(
                _matrix(features, inner_train, feature_names),
                np.asarray([labels[case_id] for case_id in inner_train], dtype=float),
                ridge,
            )
            predicted = _predict_logistic(
                _matrix(features, inner_test, feature_names), fitted
            )
            oof.update(zip(inner_test, map(float, predicted)))
        ordered_scores = [oof[case_id] for case_id in training_ids]
        ordered_truth = [labels[case_id] for case_id in training_ids]
        threshold, metric = _best_threshold(ordered_scores, ordered_truth)
        candidates.append(
            (
                float(metric["minimum_gate_metric"]),
                float(metric["balanced_accuracy"]),
                float(ridge),
                -float(threshold),
                {
                    "ridge": float(ridge),
                    "threshold": float(threshold),
                    "inner_metrics": metric,
                },
            )
        )
    selected = max(candidates)[-1]
    return selected["ridge"], selected["threshold"], selected


def _fit_outer(
    *,
    features: dict[str, dict[str, float]],
    labels: dict[str, bool],
    training_ids: list[str],
    test_ids: list[str],
    family: str,
) -> tuple[dict[str, float], dict[str, Any]]:
    feature_names = FAMILIES[family]
    ridge, threshold, selection = _select_hyperparameters(
        features=features,
        labels=labels,
        training_ids=training_ids,
        feature_names=feature_names,
    )
    fitted = _fit_logistic(
        _matrix(features, training_ids, feature_names),
        np.asarray([labels[case_id] for case_id in training_ids], dtype=float),
        ridge,
    )
    probabilities = _predict_logistic(_matrix(features, test_ids, feature_names), fitted)
    return dict(zip(test_ids, map(float, probabilities))), {
        **selection,
        "feature_family": family,
        "feature_count": len(feature_names),
        "training_case_count": len(training_ids),
    }


def _prediction(
    *,
    case_id: str,
    family: str,
    validation: str,
    score: float | None,
    threshold: float | None,
    selection: dict[str, Any] | None,
    extra: dict[str, Any],
) -> dict[str, Any]:
    return {
        "schema": PREDICTION_SCHEMA,
        "case_id": case_id,
        "feature_family": family,
        "validation": validation,
        "status": (
            "technical_failure_count_as_error"
            if score is None
            else "complete_out_of_fold_prediction"
        ),
        "score": score,
        "threshold": threshold,
        "prediction": (
            "TECHNICAL_FAILURE"
            if score is None or threshold is None
            else "POSITIVE"
            if score >= threshold
            else "NEGATIVE"
        ),
        "inner_selection": selection,
        "held_out_label_used_for_scaling": False,
        "held_out_label_used_for_model_fit": False,
        "held_out_label_used_for_regularization": False,
        "held_out_label_used_for_threshold": False,
        "lesion_masks_read": 0,
        **extra,
    }


def freeze_predictions(
    *,
    protocol_path: Path,
    phase2_root: Path,
    phase3_root: Path,
    v24_root: Path,
    v25_root: Path,
    v26_root: Path,
    workspace_root: Path,
    output_root: Path,
) -> dict[str, Any]:
    protocol = verify_protocol(
        protocol_path=protocol_path,
        phase3_root=phase3_root,
        v24_root=v24_root,
        v25_root=v25_root,
        v26_root=v26_root,
        workspace_root=workspace_root,
    )
    features, failures = _feature_matrix(
        phase3_root=phase3_root,
        v24_root=v24_root,
        v25_root=v25_root,
        v26_root=v26_root,
    )
    folds = _fold_rows(Path(phase2_root), 132)
    all_ids = sorted(folds)
    if set(features) | failures != set(all_ids):
        raise PipelineError("Coorte v27 divergiu dos folds protegidos.")
    labels = {
        case_id: folds[case_id]["label"] == "POSITIVE" for case_id in all_ids
    }
    computable = sorted(features)
    loocv_by_family: dict[str, list[dict[str, Any]]] = {}
    for family in FAMILIES:
        predictions: list[dict[str, Any]] = []
        for held_out in all_ids:
            if held_out in failures:
                predictions.append(
                    _prediction(
                        case_id=held_out,
                        family=family,
                        validation="loocv",
                        score=None,
                        threshold=None,
                        selection=None,
                        extra={"outer_fold_id": held_out},
                    )
                )
                continue
            training = [case_id for case_id in computable if case_id != held_out]
            scores, selection = _fit_outer(
                features=features,
                labels=labels,
                training_ids=training,
                test_ids=[held_out],
                family=family,
            )
            predictions.append(
                _prediction(
                    case_id=held_out,
                    family=family,
                    validation="loocv",
                    score=scores[held_out],
                    threshold=float(selection["threshold"]),
                    selection=selection,
                    extra={"outer_fold_id": held_out},
                )
            )
        loocv_by_family[family] = predictions

    repeated: list[dict[str, Any]] = []
    for repeat in range(REPEATS):
        for fold in range(FOLDS):
            test_ids = [
                case_id
                for case_id in all_ids
                if folds[case_id]["repeated_5fold_outer_assignments"][repeat] == fold
            ]
            computable_test = [case_id for case_id in test_ids if case_id in features]
            training = [
                case_id
                for case_id in computable
                if folds[case_id]["repeated_5fold_outer_assignments"][repeat] != fold
            ]
            scores, selection = _fit_outer(
                features=features,
                labels=labels,
                training_ids=training,
                test_ids=computable_test,
                family=PRIMARY_FAMILY,
            )
            for case_id in test_ids:
                failed = case_id in failures
                repeated.append(
                    _prediction(
                        case_id=case_id,
                        family=PRIMARY_FAMILY,
                        validation="repeated_5fold",
                        score=None if failed else scores[case_id],
                        threshold=None if failed else float(selection["threshold"]),
                        selection=None if failed else selection,
                        extra={"repeat": repeat, "outer_fold": fold},
                    )
                )

    destination = Path(output_root).resolve()
    if destination.exists():
        raise PipelineError("Freeze v27 já existe.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = destination.parent / f"._v27_predictions_{uuid.uuid4().hex[:8]}"
    staging.mkdir()
    try:
        artifacts: dict[str, Any] = {}
        for family, rows in loocv_by_family.items():
            filename = f"loocv_{family}.jsonl"
            _write_jsonl(staging / filename, rows)
            artifacts[family] = {
                "path": filename,
                "sha256": _sha256(staging / filename),
                "count": len(rows),
            }
        repeated_name = "repeated_5fold_primary.jsonl"
        _write_jsonl(staging / repeated_name, repeated)
        artifacts["repeated_primary"] = {
            "path": repeated_name,
            "sha256": _sha256(staging / repeated_name),
            "count": len(repeated),
        }
        body = {
            "schema": FREEZE_SCHEMA,
            "status": "v27_nested_oof_predictions_frozen_before_metrics",
            "protocol_signature": protocol["protocol_signature"],
            "case_count": 132,
            "computable_case_count": 130,
            "technical_failure_count": 2,
            "primary_family": PRIMARY_FAMILY,
            "artifacts": artifacts,
            "all_preprocessing_and_fitting_nested_in_outer_training": True,
            "metrics_calculated": False,
            "lesion_masks_read": 0,
        }
        summary = {**body, "prediction_freeze_signature": _canonical_sha(body)}
        _write_json(staging / "summary.json", summary)
        _publish_directory(staging, destination)
        return summary
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def _verify_prediction_freeze(
    prediction_root: Path, protocol: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, list[dict[str, Any]]]]:
    root = Path(prediction_root)
    summary = _load(root / "summary.json", "Freeze v27")
    unsigned = dict(summary)
    signature = unsigned.pop("prediction_freeze_signature", None)
    if (
        summary.get("schema") != FREEZE_SCHEMA
        or signature != _canonical_sha(unsigned)
        or summary.get("protocol_signature") != protocol["protocol_signature"]
        or summary.get("metrics_calculated") is not False
        or summary.get("primary_family") != PRIMARY_FAMILY
    ):
        raise PipelineError("Freeze v27 adulterado.")
    loaded: dict[str, list[dict[str, Any]]] = {}
    for key, artifact in summary["artifacts"].items():
        path = root / artifact["path"]
        if _sha256(path) != artifact["sha256"]:
            raise PipelineError("Hash de predição v27 divergiu.")
        rows = _jsonl(path, f"Predições v27 {key}")
        if len(rows) != artifact["count"] or any("label" in row for row in rows):
            raise PipelineError("Predições v27 têm cobertura ou vazamento inválido.")
        loaded[key] = rows
    if any(
        len(loaded[family]) != 132
        or len({row["case_id"] for row in loaded[family]}) != 132
        for family in FAMILIES
    ) or len(loaded["repeated_primary"]) != 132 * REPEATS:
        raise PipelineError("Predições v27 incompletas.")
    return summary, loaded


def evaluate_predictions(
    *,
    protocol_path: Path,
    prediction_root: Path,
    phase2_root: Path,
    phase3_root: Path,
    v24_root: Path,
    v25_root: Path,
    v26_root: Path,
    workspace_root: Path,
    v23_evaluation_path: Path,
    output_root: Path,
) -> dict[str, Any]:
    protocol = verify_protocol(
        protocol_path=protocol_path,
        phase3_root=phase3_root,
        v24_root=v24_root,
        v25_root=v25_root,
        v26_root=v26_root,
        workspace_root=workspace_root,
    )
    summary, predictions = _verify_prediction_freeze(prediction_root, protocol)
    folds = _fold_rows(Path(phase2_root), 132)
    labels = {case_id: row["label"] for case_id, row in folds.items()}
    ablations: dict[str, Any] = {}
    for family in FAMILIES:
        rows = predictions[family]
        ablations[family] = {
            "loocv": _confusion(rows, labels),
            "roc_auc_secondary": _roc_auc(rows, labels),
        }
    primary_rows = predictions[PRIMARY_FAMILY]
    primary = ablations[PRIMARY_FAMILY]["loocv"]
    repeat_metrics = []
    for repeat in range(REPEATS):
        rows = [
            row for row in predictions["repeated_primary"] if row["repeat"] == repeat
        ]
        repeat_metrics.append({"repeat": repeat, **_confusion(rows, labels)})
    v23 = _load(v23_evaluation_path, "Avaliação v23")
    v23_metric = v23["primary_loocv"]
    current_min = min(primary["sensitivity"], primary["specificity"])
    prior_min = min(v23_metric["sensitivity"], v23_metric["specificity"])
    passed = (
        primary["passed_75_75"]
        and current_min > prior_min
        and len(repeat_metrics) == REPEATS
    )
    body = {
        "schema": EVALUATION_SCHEMA,
        "status": "v27_candidate_passed" if passed else "v27_candidate_failed",
        "candidate_id": protocol["candidate_id"],
        "primary_family": PRIMARY_FAMILY,
        "primary_loocv": primary,
        "primary_roc_auc_secondary": ablations[PRIMARY_FAMILY][
            "roc_auc_secondary"
        ],
        "primary_bootstrap_95": _bootstrap(primary_rows, labels),
        "repeated_5fold_50": {
            "repeat_count": len(repeat_metrics),
            "passes_75_75": sum(row["passed_75_75"] for row in repeat_metrics),
            "median_sensitivity": statistics.median(
                row["sensitivity"] for row in repeat_metrics
            ),
            "median_specificity": statistics.median(
                row["specificity"] for row in repeat_metrics
            ),
            "minimum_sensitivity": min(
                row["sensitivity"] for row in repeat_metrics
            ),
            "minimum_specificity": min(
                row["specificity"] for row in repeat_metrics
            ),
            "per_repeat": repeat_metrics,
        },
        "predeclared_ablations": ablations,
        "comparison_to_v23": {
            "v23_sensitivity": v23_metric["sensitivity"],
            "v23_specificity": v23_metric["specificity"],
            "v23_minimum_axis": prior_min,
            "v27_minimum_axis": current_min,
            "improved_minimum_axis": current_min > prior_min,
        },
        "acceptance": {
            "loocv_sensitivity_at_least_75": primary["sensitivity"] >= 0.75,
            "loocv_specificity_at_least_75": primary["specificity"] >= 0.75,
            "improved_minimum_axis_over_v23": current_min > prior_min,
            "passed": passed,
        },
        "prediction_freeze_signature": summary["prediction_freeze_signature"],
        "technical_failures_counted_as_errors": True,
        "lesion_masks_read": 0,
        "research_only": True,
        "clinical_use_allowed": False,
    }
    evaluation = {**body, "evaluation_signature": _canonical_sha(body)}
    destination = Path(output_root).resolve()
    if destination.exists():
        raise PipelineError("Avaliação v27 já existe.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = destination.parent / f"._v27_evaluation_{uuid.uuid4().hex[:8]}"
    staging.mkdir()
    try:
        _write_json(staging / "evaluation.json", evaluation)
        _publish_directory(staging, destination)
        return evaluation
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise


__all__ = [
    "FAMILIES",
    "PRIMARY_FAMILY",
    "evaluate_predictions",
    "freeze_predictions",
    "freeze_protocol",
    "verify_protocol",
]
