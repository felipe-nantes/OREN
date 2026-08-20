"""Nested patient-level classifier over frozen label-blind radiomics features."""
from __future__ import annotations

import json
import math
import os
import tempfile
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import yaml
from sklearn.feature_selection import SelectKBest, f_classif
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from dtwin.core import PipelineError
from dtwin.learning.protocol import (
    canonical_sha256,
    load_protected_cases,
    sha256_file,
    verify_protocol,
)
from dtwin.learning.radiomics_features import verify_radiomics_features
from dtwin.learning.splits import validate_nested_splits

PREDICTION_SCHEMA = "argos-hybrid-radiomics-oof-prediction-v1"
PREDICTION_FREEZE_SCHEMA = "argos-hybrid-radiomics-oof-freeze-v1"
EVALUATION_SCHEMA = "argos-hybrid-radiomics-oof-evaluation-v1"


def _json(path: Path, description: str) -> Any:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PipelineError(f"{description} ausente ou inválido: {path}") from exc


def _jsonl(path: Path, description: str) -> list[dict[str, Any]]:
    try:
        rows = [
            json.loads(line)
            for line in Path(path).read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    except (OSError, json.JSONDecodeError) as exc:
        raise PipelineError(f"{description} ausente ou inválido: {path}") from exc
    if any(not isinstance(row, dict) for row in rows):
        raise PipelineError(f"{description} contém registro inválido.")
    return rows


def load_classifier_config(path: Path) -> dict[str, Any]:
    try:
        value = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise PipelineError(f"Config do classificador radiômico inválida: {path}") from exc
    if not isinstance(value, dict):
        raise PipelineError("Config do classificador radiômico deve ser objeto YAML.")
    if value.get("schema") != "argos-hybrid-radiomics-classifier-config-v1":
        raise PipelineError("Schema do classificador radiômico inválido.")
    if value.get("model") != "class_balanced_elastic_net_logistic_regression":
        raise PipelineError("Modelo primário radiômico não autorizado.")
    for key in ("regularization_c_grid", "l1_ratio_grid", "feature_count_grid"):
        if not isinstance(value.get(key), list) or not value[key]:
            raise PipelineError(f"Grid ausente: {key}.")
    if any(float(item) <= 0 for item in value["regularization_c_grid"]):
        raise PipelineError("Valores de C devem ser positivos.")
    if any(not 0.0 <= float(item) <= 1.0 for item in value["l1_ratio_grid"]):
        raise PipelineError("l1_ratio deve estar entre zero e um.")
    for item in value["feature_count_grid"]:
        if item != "all" and int(item) <= 0:
            raise PipelineError("Número de features deve ser positivo ou 'all'.")
    if value.get("technical_failures_count_as_errors") is not True:
        raise PipelineError("Falhas técnicas devem contar como erros.")
    return value


def _load_feature_matrix(
    radiomics_root: Path,
) -> tuple[dict[str, np.ndarray], list[str], set[str]]:
    manifest = _json(Path(radiomics_root) / "radiomics_manifest.json", "Manifesto radiômico")
    feature_names = list(manifest.get("feature_names") or [])
    rows = _jsonl(Path(radiomics_root) / "features.jsonl", "Features radiômicas")
    failures = _jsonl(
        Path(radiomics_root) / "technical_failures.jsonl", "Falhas radiômicas"
    )
    feature_map: dict[str, np.ndarray] = {}
    for row in rows:
        if row.get("ground_truth_read") is not False or row.get("lesion_mask_read") is not False:
            raise PipelineError("Artefato radiômico contém dado protegido.")
        vector = np.asarray(
            [float(row["features"][name]) for name in feature_names], dtype=np.float64
        )
        if vector.shape != (len(feature_names),) or not np.isfinite(vector).all():
            raise PipelineError(f"Vetor radiômico inválido em {row.get('case_id')}.")
        case_id = str(row["case_id"])
        if case_id in feature_map:
            raise PipelineError("Caso radiômico duplicado.")
        feature_map[case_id] = vector
    failed = {str(row["case_id"]) for row in failures}
    if failed & set(feature_map):
        raise PipelineError("Caso simultaneamente válido e falho.")
    return feature_map, feature_names, failed


def _matrix(
    case_ids: Iterable[str],
    feature_map: dict[str, np.ndarray],
    label_map: dict[str, int],
) -> tuple[np.ndarray, np.ndarray]:
    available = [case_id for case_id in case_ids if case_id in feature_map]
    if not available:
        raise PipelineError("Treino radiômico sem casos válidos.")
    labels = np.asarray([label_map[case_id] for case_id in available], dtype=np.int64)
    if len(set(labels.tolist())) != 2:
        raise PipelineError("Treino radiômico requer as duas classes.")
    return np.stack([feature_map[case_id] for case_id in available]), labels


def _fit_model(
    case_ids: Iterable[str],
    feature_map: dict[str, np.ndarray],
    label_map: dict[str, int],
    *,
    c_value: float,
    l1_ratio: float,
    feature_count: int | str,
    seed: int,
    max_iter: int,
) -> Pipeline:
    matrix, labels = _matrix(case_ids, feature_map, label_map)
    k_value: int | str = "all" if feature_count == "all" else min(int(feature_count), matrix.shape[1])
    model = Pipeline(
        [
            ("imputer", SimpleImputer(strategy="median")),
            ("scaler", StandardScaler()),
            ("selector", SelectKBest(score_func=f_classif, k=k_value)),
            (
                "classifier",
                LogisticRegression(
                    C=float(c_value),
                    class_weight="balanced",
                    l1_ratio=float(l1_ratio),
                    max_iter=int(max_iter),
                    penalty="elasticnet",
                    random_state=int(seed),
                    solver="saga",
                    tol=1e-4,
                ),
            ),
        ]
    )
    model.fit(matrix, labels)
    return model


def _scores(
    model: Pipeline, case_ids: Iterable[str], feature_map: dict[str, np.ndarray]
) -> dict[str, float]:
    available = [case_id for case_id in case_ids if case_id in feature_map]
    if not available:
        return {}
    probabilities = model.predict_proba(
        np.stack([feature_map[case_id] for case_id in available])
    )[:, 1]
    return {case_id: float(score) for case_id, score in zip(available, probabilities)}


def _confusion(
    case_ids: Iterable[str],
    scores: dict[str, float],
    label_map: dict[str, int],
    threshold: float,
) -> dict[str, Any]:
    tp = tn = fp = fn = failures = 0
    for case_id in case_ids:
        label = label_map[case_id]
        if case_id not in scores:
            failures += 1
            if label:
                fn += 1
            else:
                fp += 1
            continue
        prediction = int(scores[case_id] >= threshold)
        if label and prediction:
            tp += 1
        elif not label and not prediction:
            tn += 1
        elif label:
            fn += 1
        else:
            fp += 1
    sensitivity = tp / (tp + fn) if tp + fn else 0.0
    specificity = tn / (tn + fp) if tn + fp else 0.0
    return {
        "tp": tp,
        "tn": tn,
        "fp": fp,
        "fn": fn,
        "technical_failures": failures,
        "sensitivity": sensitivity,
        "specificity": specificity,
        "balanced_accuracy": (sensitivity + specificity) / 2.0,
    }


def _best_threshold(
    case_ids: list[str], scores: dict[str, float], label_map: dict[str, int]
) -> tuple[float, dict[str, Any]]:
    values = sorted(set(scores.values()))
    if not values:
        raise PipelineError("Scores internos radiômicos ausentes.")
    candidates = [0.0, 1.0, *values]
    candidates.extend((left + right) / 2.0 for left, right in zip(values, values[1:]))
    evaluated = [
        (threshold, _confusion(case_ids, scores, label_map, threshold))
        for threshold in sorted(set(candidates))
    ]
    threshold, metrics = max(
        evaluated,
        key=lambda item: (
            min(item[1]["sensitivity"], item[1]["specificity"]),
            item[1]["balanced_accuracy"],
            -abs(item[0] - 0.5),
            -item[0],
        ),
    )
    return float(threshold), metrics


def _inner_oof_scores(
    *,
    inner_folds: list[dict[str, Any]],
    feature_map: dict[str, np.ndarray],
    label_map: dict[str, int],
    c_value: float,
    l1_ratio: float,
    feature_count: int | str,
    seed: int,
    max_iter: int,
) -> tuple[list[str], dict[str, float]]:
    validation_ids: list[str] = []
    scores: dict[str, float] = {}
    for inner in inner_folds:
        model = _fit_model(
            inner["train_case_ids"],
            feature_map,
            label_map,
            c_value=c_value,
            l1_ratio=l1_ratio,
            feature_count=feature_count,
            seed=seed + int(inner["inner_fold"]),
            max_iter=max_iter,
        )
        current_ids = list(inner["validation_case_ids"])
        current_scores = _scores(model, current_ids, feature_map)
        if set(scores) & set(current_scores):
            raise PipelineError("Score interno radiômico duplicado.")
        scores.update(current_scores)
        validation_ids.extend(current_ids)
    if len(validation_ids) != len(set(validation_ids)):
        raise PipelineError("Caso repetido na validação interna.")
    return sorted(validation_ids), scores


def _atomic_joblib(model: Pipeline, path: Path) -> None:
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        joblib.dump(model, temporary)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def generate_oof_predictions(
    *,
    classifier_config_path: Path,
    training_protocol_config_path: Path,
    training_protocol_path: Path,
    splits_path: Path,
    radiomics_root: Path,
    candidate_root: Path,
    workspace_root: Path,
    output_root: Path,
) -> dict[str, Any]:
    output_root = Path(output_root).resolve()
    if output_root.exists():
        raise PipelineError("Predições OOF radiômicas já existem; saída é imutável.")
    output_root.mkdir(parents=True)
    config = load_classifier_config(classifier_config_path)
    protocol = verify_protocol(
        config_path=training_protocol_config_path,
        workspace_root=workspace_root,
        protocol_path=training_protocol_path,
        splits_path=splits_path,
    )
    radiomics_manifest = verify_radiomics_features(
        candidate_root=candidate_root,
        workspace_root=workspace_root,
        output_root=radiomics_root,
    )
    splits = _json(splits_path, "Splits")
    validate_nested_splits(splits)
    protected_cases = load_protected_cases(training_protocol_config_path, workspace_root)
    protected_by_id = {case.case_id: case for case in protected_cases}
    label_map = {case.case_id: int(case.label == "POSITIVE") for case in protected_cases}
    feature_map, feature_names, failed_cases = _load_feature_matrix(radiomics_root)
    if set(feature_map) | failed_cases != set(protected_by_id):
        raise PipelineError("Radiômica e protocolo protegido não cobrem a mesma coorte.")

    c_grid = [float(value) for value in config["regularization_c_grid"]]
    l1_grid = [float(value) for value in config["l1_ratio_grid"]]
    feature_grid = list(config["feature_count_grid"])
    seed = int(config.get("seed", 20260724))
    max_iter = int(config.get("max_iter", 5000))
    predictions: list[dict[str, Any]] = []
    selections: list[dict[str, Any]] = []

    for outer in splits["outer_folds"]:
        outer_index = int(outer["outer_fold"])
        candidates: list[dict[str, Any]] = []
        for c_value in c_grid:
            for l1_ratio in l1_grid:
                for feature_count in feature_grid:
                    validation_ids, scores = _inner_oof_scores(
                        inner_folds=list(outer["inner_folds"]),
                        feature_map=feature_map,
                        label_map=label_map,
                        c_value=c_value,
                        l1_ratio=l1_ratio,
                        feature_count=feature_count,
                        seed=seed + outer_index * 100,
                        max_iter=max_iter,
                    )
                    threshold, metrics = _best_threshold(validation_ids, scores, label_map)
                    candidates.append(
                        {
                            "c_value": c_value,
                            "l1_ratio": l1_ratio,
                            "feature_count": feature_count,
                            "threshold": threshold,
                            "inner_metrics": metrics,
                        }
                    )
        selected = max(
            candidates,
            key=lambda item: (
                min(item["inner_metrics"]["sensitivity"], item["inner_metrics"]["specificity"]),
                item["inner_metrics"]["balanced_accuracy"],
                -int(item["feature_count"]) if item["feature_count"] != "all" else -len(feature_names),
                -item["c_value"],
                -item["l1_ratio"],
            ),
        )
        model = _fit_model(
            outer["train_case_ids"],
            feature_map,
            label_map,
            c_value=selected["c_value"],
            l1_ratio=selected["l1_ratio"],
            feature_count=selected["feature_count"],
            seed=seed + outer_index,
            max_iter=max_iter,
        )
        test_ids = list(outer["test_case_ids"])
        test_scores = _scores(model, test_ids, feature_map)
        model_path = output_root / f"outer_fold_{outer_index}.joblib"
        _atomic_joblib(model, model_path)
        selected_features = [
            name
            for name, keep in zip(
                feature_names, model.named_steps["selector"].get_support().tolist()
            )
            if keep
        ]
        selections.append(
            {
                "outer_fold": outer_index,
                **selected,
                "selected_feature_names": selected_features,
                "model_sha256": sha256_file(model_path),
                "outer_train_case_count": len(outer["train_case_ids"]),
                "outer_test_case_count": len(test_ids),
                "held_out_labels_used_for_fit_or_threshold": False,
            }
        )
        for case_id in test_ids:
            score = test_scores.get(case_id)
            predictions.append(
                {
                    "schema": PREDICTION_SCHEMA,
                    "case_id": case_id,
                    "patient_group_id": case_id,
                    "dataset_id": protected_by_id[case_id].dataset_id,
                    "outer_fold": outer_index,
                    "score": score,
                    "threshold": selected["threshold"],
                    "prediction": (
                        "TECHNICAL_FAILURE"
                        if score is None
                        else ("POSITIVE" if score >= selected["threshold"] else "NEGATIVE")
                    ),
                    "model_c": selected["c_value"],
                    "model_l1_ratio": selected["l1_ratio"],
                    "selected_feature_count": len(selected_features),
                    "technical_failure": score is None,
                    "ground_truth_in_artifact": False,
                    "held_out_label_used": False,
                    "research_only": True,
                }
            )

    predictions.sort(key=lambda row: row["case_id"])
    if len(predictions) != len(protected_by_id) or {
        row["case_id"] for row in predictions
    } != set(protected_by_id):
        raise PipelineError("Predições radiômicas OOF não cobrem a coorte.")
    predictions_path = output_root / "oof_predictions.jsonl"
    predictions_path.write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in predictions),
        encoding="utf-8",
    )
    selection_path = output_root / "fold_selection.json"
    selection_path.write_text(
        json.dumps(selections, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    body = {
        "schema": PREDICTION_FREEZE_SCHEMA,
        "status": "frozen_before_final_metric_calculation",
        "candidate_id": str(config["candidate_id"]),
        "training_protocol_signature": protocol["protocol_signature"],
        "radiomics_signature": radiomics_manifest["radiomics_signature"],
        "classifier_config_sha256": sha256_file(classifier_config_path),
        "splits_sha256": sha256_file(splits_path),
        "prediction_count": len(predictions),
        "technical_failure_count": sum(bool(row["technical_failure"]) for row in predictions),
        "oof_predictions_sha256": sha256_file(predictions_path),
        "fold_selection_sha256": sha256_file(selection_path),
        "individual_ground_truth_persisted": False,
        "held_out_labels_used_for_fit_or_threshold": False,
        "lesion_masks_read": 0,
        "research_only": True,
        "clinical_use_allowed": False,
    }
    freeze = {**body, "prediction_signature": canonical_sha256(body)}
    (output_root / "prediction_freeze.json").write_text(
        json.dumps(freeze, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return freeze


def _wilson(successes: int, total: int) -> list[float]:
    if total <= 0:
        return [0.0, 0.0]
    z = 1.959963984540054
    proportion = successes / total
    denominator = 1 + z * z / total
    center = (proportion + z * z / (2 * total)) / denominator
    margin = z * math.sqrt(
        proportion * (1 - proportion) / total + z * z / (4 * total * total)
    ) / denominator
    return [max(0.0, center - margin), min(1.0, center + margin)]


def _auc(labels: list[int], scores: list[float]) -> float | None:
    positives = [score for label, score in zip(labels, scores) if label == 1]
    negatives = [score for label, score in zip(labels, scores) if label == 0]
    if not positives or not negatives:
        return None
    wins = sum(
        1.0 if positive > negative else 0.5 if positive == negative else 0.0
        for positive in positives
        for negative in negatives
    )
    return wins / (len(positives) * len(negatives))


def evaluate_oof_predictions(
    *,
    training_protocol_config_path: Path,
    training_protocol_path: Path,
    splits_path: Path,
    prediction_root: Path,
    workspace_root: Path,
    output_root: Path,
) -> dict[str, Any]:
    output_root = Path(output_root).resolve()
    if output_root.exists():
        raise PipelineError("Avaliação radiômica já existe; saída é imutável.")
    output_root.mkdir(parents=True)
    protocol = verify_protocol(
        config_path=training_protocol_config_path,
        workspace_root=workspace_root,
        protocol_path=training_protocol_path,
        splits_path=splits_path,
    )
    freeze = _json(Path(prediction_root) / "prediction_freeze.json", "Freeze radiômico")
    unsigned = dict(freeze)
    signature = unsigned.pop("prediction_signature", None)
    if signature != canonical_sha256(unsigned):
        raise PipelineError("Assinatura das predições radiômicas diverge.")
    predictions_path = Path(prediction_root) / "oof_predictions.jsonl"
    if freeze.get("oof_predictions_sha256") != sha256_file(predictions_path):
        raise PipelineError("Predições radiômicas OOF foram alteradas.")
    predictions = _jsonl(predictions_path, "Predições radiômicas OOF")
    if any("label" in row or "ground_truth" in row for row in predictions):
        raise PipelineError("Predições radiômicas contêm ground truth.")
    protected = {
        case.case_id: case
        for case in load_protected_cases(training_protocol_config_path, workspace_root)
    }
    if {row["case_id"] for row in predictions} != set(protected):
        raise PipelineError("Predições e labels não cobrem os mesmos casos.")

    def metrics_for(rows: list[dict[str, Any]]) -> dict[str, Any]:
        tp = tn = fp = fn = failures = 0
        auc_labels: list[int] = []
        auc_scores: list[float] = []
        for row in rows:
            label = int(protected[str(row["case_id"])].label == "POSITIVE")
            if row.get("technical_failure") is True:
                failures += 1
                if label:
                    fn += 1
                else:
                    fp += 1
                continue
            prediction = row.get("prediction")
            if prediction == "POSITIVE" and label:
                tp += 1
            elif prediction == "NEGATIVE" and not label:
                tn += 1
            elif label:
                fn += 1
            else:
                fp += 1
            auc_labels.append(label)
            auc_scores.append(float(row["score"]))
        sensitivity = tp / (tp + fn) if tp + fn else 0.0
        specificity = tn / (tn + fp) if tn + fp else 0.0
        return {
            "case_count": len(rows),
            "tp": tp,
            "tn": tn,
            "fp": fp,
            "fn": fn,
            "technical_failures": failures,
            "sensitivity": sensitivity,
            "specificity": specificity,
            "balanced_accuracy": (sensitivity + specificity) / 2.0,
            "roc_auc_computable_cases": _auc(auc_labels, auc_scores),
            "sensitivity_ci95_wilson": _wilson(tp, tp + fn),
            "specificity_ci95_wilson": _wilson(tn, tn + fp),
            "passed_75_75": sensitivity >= 0.75 and specificity >= 0.75,
        }

    overall = metrics_for(predictions)
    by_dataset = {
        dataset_id: metrics_for(
            [
                row
                for row in predictions
                if protected[str(row["case_id"])].dataset_id == dataset_id
            ]
        )
        for dataset_id in sorted({case.dataset_id for case in protected.values()})
    }
    body = {
        "schema": EVALUATION_SCHEMA,
        "candidate_id": freeze["candidate_id"],
        "training_protocol_signature": protocol["protocol_signature"],
        "prediction_signature": freeze["prediction_signature"],
        "overall": overall,
        "by_dataset": by_dataset,
        "methodology": {
            "patient_grouped_nested_cv": True,
            "outer_predictions_only": True,
            "inner_oof_model_feature_and_threshold_selection": True,
            "technical_failures_count_as_errors": True,
            "individual_ground_truth_persisted_in_predictions": False,
            "retrospective_multicohort": True,
            "external_blind_validation": False,
        },
        "acceptance": {
            "sensitivity_minimum": 0.75,
            "specificity_minimum": 0.75,
            "passed": overall["passed_75_75"],
        },
        "lesion_masks_read": 0,
        "research_only": True,
        "clinical_use_allowed": False,
    }
    evaluation = {**body, "evaluation_signature": canonical_sha256(body)}
    (output_root / "evaluation.json").write_text(
        json.dumps(evaluation, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return evaluation
