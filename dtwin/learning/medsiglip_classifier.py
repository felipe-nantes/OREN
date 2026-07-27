"""Nested patient-level classifier over frozen MedSigLIP embeddings."""
from __future__ import annotations

import json
import math
import os
import tempfile
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

import joblib
import numpy as np
import yaml
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from dtwin.core import PipelineError
from dtwin.learning.medsiglip_embeddings import verify_embeddings
from dtwin.learning.protocol import (
    canonical_sha256,
    load_protected_cases,
    sha256_file,
    verify_protocol,
)
from dtwin.learning.schemas import ProtectedTrainingCase
from dtwin.learning.splits import validate_nested_splits


PREDICTION_SCHEMA = "argos-hybrid-medsiglip-oof-prediction-v1"
PREDICTION_FREEZE_SCHEMA = "argos-hybrid-medsiglip-oof-freeze-v1"
EVALUATION_SCHEMA = "argos-hybrid-medsiglip-oof-evaluation-v1"


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
        raise PipelineError(f"Config do classificador inválida: {path}") from exc
    if not isinstance(value, dict):
        raise PipelineError("Config do classificador deve ser objeto YAML.")
    if value.get("schema") != "argos-hybrid-medsiglip-classifier-config-v1":
        raise PipelineError("Schema do classificador inválido.")
    aggregations = value.get("panel_probability_aggregations")
    if not isinstance(aggregations, list) or not aggregations:
        raise PipelineError("Agregações de painel ausentes.")
    allowed = {"mean", "max", "top2_mean"}
    if any(item not in allowed for item in aggregations):
        raise PipelineError("Agregação de painel inválida.")
    c_grid = value.get("regularization_c_grid")
    if not isinstance(c_grid, list) or not c_grid:
        raise PipelineError("Grid C ausente.")
    if any(float(item) <= 0 for item in c_grid):
        raise PipelineError("Valores de C devem ser positivos.")
    return value


def _load_embedding_map(
    embedding_root: Path,
) -> tuple[dict[str, list[np.ndarray]], dict[str, list[str]]]:
    rows = _jsonl(
        Path(embedding_root) / "embedding_records.jsonl",
        "Registros de embeddings",
    )
    vectors: dict[str, list[np.ndarray]] = defaultdict(list)
    candidates: dict[str, list[str]] = defaultdict(list)
    for row in rows:
        if row.get("label_attached") is not False:
            raise PipelineError("Embedding contém label.")
        case_id = str(row["case_id"])
        vector = np.load(
            Path(embedding_root) / str(row["embedding_path"]),
            allow_pickle=False,
        ).astype(np.float64)
        if vector.ndim != 1 or not np.isfinite(vector).all():
            raise PipelineError(f"Embedding inválido em {case_id}.")
        vectors[case_id].append(vector)
        candidates[case_id].append(str(row["candidate_id"]))
    return dict(vectors), dict(candidates)


def _panel_matrix(
    case_ids: Iterable[str],
    embedding_map: dict[str, list[np.ndarray]],
    label_map: dict[str, int],
) -> tuple[np.ndarray, np.ndarray]:
    values: list[np.ndarray] = []
    labels: list[int] = []
    for case_id in case_ids:
        for vector in embedding_map.get(case_id, []):
            values.append(vector)
            labels.append(label_map[case_id])
    if not values or len(set(labels)) != 2:
        raise PipelineError("Treino requer embeddings nas duas classes.")
    return np.stack(values), np.asarray(labels, dtype=np.int64)


def _aggregate(probabilities: list[float], method: str) -> float:
    if not probabilities:
        raise PipelineError("Não é possível agregar caso sem painel.")
    ordered = sorted((float(value) for value in probabilities), reverse=True)
    if method == "mean":
        return float(np.mean(ordered))
    if method == "max":
        return ordered[0]
    if method == "top2_mean":
        return float(np.mean(ordered[:2]))
    raise PipelineError(f"Agregação desconhecida: {method}")


def _case_scores(
    model: Pipeline,
    case_ids: Iterable[str],
    embedding_map: dict[str, list[np.ndarray]],
    aggregation: str,
) -> dict[str, float]:
    result: dict[str, float] = {}
    for case_id in case_ids:
        vectors = embedding_map.get(case_id, [])
        if not vectors:
            continue
        matrix = np.stack(vectors)
        probabilities = model.predict_proba(matrix)[:, 1].tolist()
        result[case_id] = _aggregate(probabilities, aggregation)
    return result


def _fit_model(
    case_ids: Iterable[str],
    embedding_map: dict[str, list[np.ndarray]],
    label_map: dict[str, int],
    *,
    c_value: float,
    seed: int,
    max_iter: int,
) -> Pipeline:
    matrix, labels = _panel_matrix(case_ids, embedding_map, label_map)
    model = Pipeline(
        [
            ("scaler", StandardScaler()),
            (
                "classifier",
                LogisticRegression(
                    C=float(c_value),
                    class_weight="balanced",
                    dual=True,
                    max_iter=max_iter,
                    random_state=seed,
                    solver="liblinear",
                ),
            ),
        ]
    )
    model.fit(matrix, labels)
    return model


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
            if label == 1:
                fn += 1
            else:
                fp += 1
            continue
        prediction = int(scores[case_id] >= threshold)
        if label == 1 and prediction == 1:
            tp += 1
        elif label == 0 and prediction == 0:
            tn += 1
        elif label == 0:
            fp += 1
        else:
            fn += 1
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


def _threshold_candidates(scores: dict[str, float]) -> list[float]:
    unique = sorted(set(scores.values()))
    if not unique:
        raise PipelineError("Scores internos ausentes.")
    candidates = [0.0, 1.0]
    candidates.extend(unique)
    candidates.extend(
        (left + right) / 2.0 for left, right in zip(unique, unique[1:])
    )
    return sorted(set(candidates))


def _best_threshold(
    case_ids: list[str],
    scores: dict[str, float],
    label_map: dict[str, int],
) -> tuple[float, dict[str, Any]]:
    evaluated = [
        (
            threshold,
            _confusion(case_ids, scores, label_map, threshold),
        )
        for threshold in _threshold_candidates(scores)
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
    embedding_map: dict[str, list[np.ndarray]],
    label_map: dict[str, int],
    c_value: float,
    aggregation: str,
    seed: int,
    max_iter: int,
) -> tuple[list[str], dict[str, float]]:
    validation_ids: list[str] = []
    scores: dict[str, float] = {}
    for inner in inner_folds:
        train_ids = list(inner["train_case_ids"])
        current_validation = list(inner["validation_case_ids"])
        model = _fit_model(
            train_ids,
            embedding_map,
            label_map,
            c_value=c_value,
            seed=seed + int(inner["inner_fold"]),
            max_iter=max_iter,
        )
        current_scores = _case_scores(
            model, current_validation, embedding_map, aggregation
        )
        overlap = set(scores) & set(current_scores)
        if overlap:
            raise PipelineError("Score interno duplicado.")
        scores.update(current_scores)
        validation_ids.extend(current_validation)
    if len(validation_ids) != len(set(validation_ids)):
        raise PipelineError("Caso repetido na validação interna.")
    return sorted(validation_ids), scores


def generate_oof_predictions(
    *,
    classifier_config_path: Path,
    training_protocol_config_path: Path,
    training_protocol_path: Path,
    splits_path: Path,
    embedding_root: Path,
    candidate_root: Path,
    workspace_root: Path,
    output_root: Path,
) -> dict[str, Any]:
    output_root = Path(output_root).resolve()
    if output_root.exists():
        raise PipelineError("Predições OOF já existem; saída é imutável.")
    output_root.mkdir(parents=True)
    config = load_classifier_config(classifier_config_path)
    protocol = verify_protocol(
        config_path=training_protocol_config_path,
        workspace_root=workspace_root,
        protocol_path=training_protocol_path,
        splits_path=splits_path,
    )
    embedding_manifest = verify_embeddings(
        candidate_root=candidate_root, output_root=embedding_root
    )
    splits = _json(splits_path, "Splits")
    validate_nested_splits(splits)
    protected_cases = load_protected_cases(
        training_protocol_config_path, workspace_root
    )
    protected_by_id = {case.case_id: case for case in protected_cases}
    label_map = {
        case.case_id: int(case.label == "POSITIVE")
        for case in protected_cases
    }
    embedding_map, candidate_map = _load_embedding_map(embedding_root)
    c_grid = [float(value) for value in config["regularization_c_grid"]]
    aggregations = list(config["panel_probability_aggregations"])
    seed = int(config.get("seed", 20260724))
    max_iter = int(config.get("max_iter", 2000))
    predictions: list[dict[str, Any]] = []
    selections: list[dict[str, Any]] = []

    for outer in splits["outer_folds"]:
        outer_index = int(outer["outer_fold"])
        outer_train_ids = list(outer["train_case_ids"])
        outer_test_ids = list(outer["test_case_ids"])
        candidates: list[dict[str, Any]] = []
        for c_value in c_grid:
            for aggregation in aggregations:
                validation_ids, scores = _inner_oof_scores(
                    inner_folds=list(outer["inner_folds"]),
                    embedding_map=embedding_map,
                    label_map=label_map,
                    c_value=c_value,
                    aggregation=aggregation,
                    seed=seed + outer_index * 100,
                    max_iter=max_iter,
                )
                threshold, metrics = _best_threshold(
                    validation_ids, scores, label_map
                )
                candidates.append(
                    {
                        "c_value": c_value,
                        "aggregation": aggregation,
                        "threshold": threshold,
                        "inner_metrics": metrics,
                    }
                )
        selected = max(
            candidates,
            key=lambda item: (
                min(
                    item["inner_metrics"]["sensitivity"],
                    item["inner_metrics"]["specificity"],
                ),
                item["inner_metrics"]["balanced_accuracy"],
                -item["c_value"],
                -aggregations.index(item["aggregation"]),
            ),
        )
        model = _fit_model(
            outer_train_ids,
            embedding_map,
            label_map,
            c_value=selected["c_value"],
            seed=seed + outer_index,
            max_iter=max_iter,
        )
        test_scores = _case_scores(
            model,
            outer_test_ids,
            embedding_map,
            selected["aggregation"],
        )
        model_path = output_root / f"outer_fold_{outer_index}.joblib"
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{model_path.name}.", suffix=".tmp", dir=output_root
        )
        os.close(descriptor)
        temporary = Path(temporary_name)
        try:
            joblib.dump(model, temporary)
            os.replace(temporary, model_path)
        finally:
            temporary.unlink(missing_ok=True)
        selection = {
            "outer_fold": outer_index,
            **selected,
            "model_sha256": sha256_file(model_path),
            "outer_train_case_count": len(outer_train_ids),
            "outer_test_case_count": len(outer_test_ids),
            "held_out_labels_used_for_fit_or_threshold": False,
        }
        selections.append(selection)
        for case_id in outer_test_ids:
            score = test_scores.get(case_id)
            predictions.append(
                {
                    "schema": PREDICTION_SCHEMA,
                    "case_id": case_id,
                    "patient_group_id": case_id,
                    "dataset_id": protected_by_id[case_id].dataset_id,
                    "outer_fold": outer_index,
                    "panel_count": len(candidate_map.get(case_id, [])),
                    "score": score,
                    "threshold": selected["threshold"],
                    "prediction": (
                        "TECHNICAL_FAILURE"
                        if score is None
                        else ("POSITIVE" if score >= selected["threshold"] else "NEGATIVE")
                    ),
                    "aggregation": selected["aggregation"],
                    "model_c": selected["c_value"],
                    "technical_failure": score is None,
                    "ground_truth_in_artifact": False,
                    "held_out_label_used": False,
                    "research_only": True,
                }
            )

    predictions.sort(key=lambda row: row["case_id"])
    case_ids = [row["case_id"] for row in predictions]
    if len(case_ids) != len(set(case_ids)):
        raise PipelineError("Predição OOF duplicada.")
    if set(case_ids) != set(protected_by_id):
        raise PipelineError("Predições OOF não cobrem a coorte protegida.")
    predictions_path = output_root / "oof_predictions.jsonl"
    predictions_path.write_text(
        "".join(
            json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n"
            for row in predictions
        ),
        encoding="utf-8",
    )
    selection_path = output_root / "fold_selection.json"
    selection_path.write_text(
        json.dumps(selections, ensure_ascii=False, indent=2, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )
    body = {
        "schema": PREDICTION_FREEZE_SCHEMA,
        "status": "frozen_before_final_metric_calculation",
        "candidate_id": str(config["candidate_id"]),
        "training_protocol_signature": protocol["protocol_signature"],
        "embedding_signature": embedding_manifest["embedding_signature"],
        "classifier_config_sha256": sha256_file(classifier_config_path),
        "splits_sha256": sha256_file(splits_path),
        "prediction_count": len(predictions),
        "technical_failure_count": sum(
            bool(row["technical_failure"]) for row in predictions
        ),
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
        json.dumps(freeze, ensure_ascii=False, indent=2, sort_keys=True)
        + "\n",
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
    margin = (
        z
        * math.sqrt(
            proportion * (1 - proportion) / total + z * z / (4 * total * total)
        )
        / denominator
    )
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
        raise PipelineError("Avaliação já existe; saída é imutável.")
    output_root.mkdir(parents=True)
    protocol = verify_protocol(
        config_path=training_protocol_config_path,
        workspace_root=workspace_root,
        protocol_path=training_protocol_path,
        splits_path=splits_path,
    )
    freeze = _json(
        Path(prediction_root) / "prediction_freeze.json",
        "Freeze de predições",
    )
    unsigned = dict(freeze)
    signature = unsigned.pop("prediction_signature", None)
    if signature != canonical_sha256(unsigned):
        raise PipelineError("Assinatura das predições diverge.")
    predictions_path = Path(prediction_root) / "oof_predictions.jsonl"
    if freeze.get("oof_predictions_sha256") != sha256_file(predictions_path):
        raise PipelineError("Predições OOF foram alteradas.")
    predictions = _jsonl(predictions_path, "Predições OOF")
    if any("label" in row or "ground_truth" in row for row in predictions):
        raise PipelineError("Predições contêm ground truth.")
    protected = {
        case.case_id: case
        for case in load_protected_cases(
            training_protocol_config_path, workspace_root
        )
    }
    if {row["case_id"] for row in predictions} != set(protected):
        raise PipelineError("Predições e labels não cobrem os mesmos casos.")

    def metrics_for(rows: list[dict[str, Any]]) -> dict[str, Any]:
        tp = tn = fp = fn = failures = 0
        auc_labels: list[int] = []
        auc_scores: list[float] = []
        for row in rows:
            case = protected[str(row["case_id"])]
            label = int(case.label == "POSITIVE")
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
        for dataset_id in sorted(
            {case.dataset_id for case in protected.values()}
        )
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
            "inner_oof_model_and_threshold_selection": True,
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
        json.dumps(
            evaluation, ensure_ascii=False, indent=2, sort_keys=True
        )
        + "\n",
        encoding="utf-8",
    )
    return evaluation
