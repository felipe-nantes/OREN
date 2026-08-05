"""Nested OOF candidate-supervised classifier for 2.5D MedSigLIP patches."""
from __future__ import annotations

import json
import math
import os
import tempfile
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import yaml
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from dtwin.core import PipelineError
from dtwin.learning.medsiglip_embeddings import verify_embeddings
from dtwin.learning.protocol import canonical_sha256, sha256_file


def _json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PipelineError(f"JSON 2.5D inválido: {path}") from exc
    if not isinstance(value, dict):
        raise PipelineError("Objeto JSON 2.5D esperado.")
    return value


def _jsonl(path: Path) -> list[dict[str, Any]]:
    try:
        return [
            json.loads(line)
            for line in Path(path).read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    except (OSError, json.JSONDecodeError) as exc:
        raise PipelineError(f"JSONL 2.5D inválido: {path}") from exc


def _load_config(path: Path) -> dict[str, Any]:
    try:
        value = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise PipelineError("Config do classificador 2.5D inválida.") from exc
    if not isinstance(value, dict) or value.get("schema") != "argos-hybrid-patch25d-classifier-config-v1":
        raise PipelineError("Schema do classificador 2.5D inválido.")
    return value


def _load_inputs(
    embedding_root: Path, target_root: Path
) -> tuple[dict[str, list[tuple[str, np.ndarray]]], dict[tuple[str, str], int], dict[str, str]]:
    embeddings: dict[str, list[tuple[str, np.ndarray]]] = {}
    for row in _jsonl(Path(embedding_root) / "embedding_records.jsonl"):
        case_id, candidate_id = str(row["case_id"]), str(row["candidate_id"])
        vector = np.load(Path(embedding_root) / row["embedding_path"], allow_pickle=False).astype(np.float64)
        embeddings.setdefault(case_id, []).append((candidate_id, vector))
    target_manifest = _json(Path(target_root) / "target_manifest.json")
    targets_path = Path(target_root) / "protected_candidate_targets.jsonl"
    if target_manifest.get("targets_sha256") != sha256_file(targets_path):
        raise PipelineError("Targets protegidos 2.5D alterados.")
    targets: dict[tuple[str, str], int] = {}
    case_labels: dict[str, str] = {}
    for row in _jsonl(targets_path):
        case_id, candidate_id = str(row["case_id"]), str(row["candidate_id"])
        case_labels[case_id] = str(row["case_label"])
        if row.get("candidate_target") is not None:
            targets[(case_id, candidate_id)] = int(row["candidate_target"])
    ordered_embeddings = {
        case_id: sorted(vectors, key=lambda item: item[0])
        for case_id, vectors in embeddings.items()
    }
    return ordered_embeddings, targets, case_labels


def _fit(
    case_ids: list[str],
    embeddings: dict[str, list[tuple[str, np.ndarray]]],
    targets: dict[tuple[str, str], int],
    *,
    c_value: float,
    seed: int,
    max_iter: int,
    model_family: str = "logistic",
) -> Any:
    values: list[np.ndarray] = []
    labels: list[int] = []
    for case_id in case_ids:
        for candidate_id, vector in embeddings.get(case_id, []):
            key = (case_id, candidate_id)
            if key in targets:
                values.append(vector)
                labels.append(targets[key])
    if not values or set(labels) != {0, 1}:
        raise PipelineError("Treino 2.5D requer candidatos supervisionados nas duas classes.")
    if model_family == "logistic":
        model: Any = Pipeline(
            [
                ("scaler", StandardScaler()),
                (
                    "classifier",
                    LogisticRegression(
                        C=float(c_value),
                        class_weight="balanced",
                        dual=True,
                        max_iter=int(max_iter),
                        random_state=int(seed),
                        solver="liblinear",
                    ),
                ),
            ]
        )
    elif model_family == "hist_gradient_boosting":
        model = HistGradientBoostingClassifier(
            learning_rate=0.05,
            max_iter=min(int(max_iter), 300),
            max_leaf_nodes=7,
            min_samples_leaf=12,
            l2_regularization=float(c_value),
            class_weight="balanced",
            early_stopping=False,
            random_state=int(seed),
        )
    else:
        raise PipelineError(f"Familia de classificador candidata invalida: {model_family}.")
    model.fit(np.stack(values), np.asarray(labels))
    return model


def _aggregate(values: list[float], method: str) -> float:
    ordered = sorted(values, reverse=True)
    if method == "max":
        return ordered[0]
    if method == "top2_mean":
        return float(np.mean(ordered[:2]))
    if method == "top3_mean":
        return float(np.mean(ordered[:3]))
    raise PipelineError("Agregação 2.5D inválida.")


def _scores(
    model: Pipeline,
    case_ids: list[str],
    embeddings: dict[str, list[tuple[str, np.ndarray]]],
    aggregation: str,
) -> dict[str, float]:
    result: dict[str, float] = {}
    for case_id in case_ids:
        pairs = embeddings.get(case_id, [])
        if pairs:
            probabilities = model.predict_proba(
                np.stack([vector for _, vector in pairs])
            )[:, 1].tolist()
            result[case_id] = _aggregate(probabilities, aggregation)
    return result


def _confusion(
    case_ids: list[str], scores: dict[str, float], labels: dict[str, str], threshold: float
) -> dict[str, Any]:
    tp = tn = fp = fn = failures = 0
    for case_id in case_ids:
        positive = labels[case_id] == "POSITIVE"
        if case_id not in scores:
            failures += 1
            if positive:
                fn += 1
            else:
                fp += 1
            continue
        predicted = scores[case_id] >= threshold
        if positive and predicted:
            tp += 1
        elif not positive and not predicted:
            tn += 1
        elif positive:
            fn += 1
        else:
            fp += 1
    sensitivity = tp / (tp + fn)
    specificity = tn / (tn + fp)
    return {
        "tp": tp, "tn": tn, "fp": fp, "fn": fn, "technical_failures": failures,
        "sensitivity": sensitivity, "specificity": specificity,
        "balanced_accuracy": (sensitivity + specificity) / 2.0,
    }


def _best_threshold(
    case_ids: list[str], scores: dict[str, float], labels: dict[str, str]
) -> tuple[float, dict[str, Any]]:
    values = sorted(set(scores.values()))
    candidates = [0.0, 1.0, *values]
    candidates += [(a + b) / 2 for a, b in zip(values, values[1:])]
    return max(
        ((value, _confusion(case_ids, scores, labels, value)) for value in set(candidates)),
        key=lambda item: (
            min(item[1]["sensitivity"], item[1]["specificity"]),
            item[1]["balanced_accuracy"],
            -abs(item[0] - 0.5),
        ),
    )


def _filtered_folds(splits: dict[str, Any], cohort: set[str]) -> list[dict[str, Any]]:
    result = []
    for outer in splits["outer_folds"]:
        result.append(
            {
                "outer_fold": int(outer["outer_fold"]),
                "train_case_ids": [item for item in outer["train_case_ids"] if item in cohort],
                "test_case_ids": [item for item in outer["test_case_ids"] if item in cohort],
                "inner_folds": [
                    {
                        "inner_fold": int(inner["inner_fold"]),
                        "train_case_ids": [item for item in inner["train_case_ids"] if item in cohort],
                        "validation_case_ids": [item for item in inner["validation_case_ids"] if item in cohort],
                    }
                    for inner in outer["inner_folds"]
                ],
            }
        )
    tests = [case_id for outer in result for case_id in outer["test_case_ids"]]
    if len(tests) != len(set(tests)) or set(tests) != cohort:
        raise PipelineError("Splits filtrados 2.5D não cobrem a coorte.")
    return result


def _atomic_model(model: Pipeline, path: Path) -> None:
    descriptor, temporary_name = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        joblib.dump(model, temporary)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def generate_oof(
    *,
    config_path: Path,
    splits_path: Path,
    candidate_root: Path,
    embedding_root: Path,
    target_root: Path,
    output_root: Path,
) -> dict[str, Any]:
    output_root = Path(output_root).resolve()
    if output_root.exists():
        raise PipelineError("Predições 2.5D já existem.")
    output_root.mkdir(parents=True)
    config = _load_config(config_path)
    embedding_manifest = verify_embeddings(candidate_root=candidate_root, output_root=embedding_root)
    target_manifest = _json(Path(target_root) / "target_manifest.json")
    embeddings, targets, labels = _load_inputs(embedding_root, target_root)
    cohort = set(labels)
    splits = _json(splits_path)
    folds = _filtered_folds(splits, cohort)
    c_grid = [float(item) for item in config["regularization_c_grid"]]
    aggregations = list(config["aggregations"])
    seed, max_iter = int(config["seed"]), int(config["max_iter"])
    model_family = str(config.get("model_family", "logistic"))
    predictions: list[dict[str, Any]] = []
    selections: list[dict[str, Any]] = []
    for outer in folds:
        options = []
        for c_value in c_grid:
            fitted_inner: list[tuple[Any, list[str]]] = []
            for inner in outer["inner_folds"]:
                model = _fit(
                    inner["train_case_ids"], embeddings, targets,
                    c_value=c_value,
                    seed=seed + outer["outer_fold"] * 100 + inner["inner_fold"],
                    max_iter=max_iter, model_family=model_family,
                )
                fitted_inner.append((model, inner["validation_case_ids"]))
            for aggregation in aggregations:
                inner_scores: dict[str, float] = {}
                validation_ids: list[str] = []
                for model, ids in fitted_inner:
                    inner_scores.update(_scores(model, ids, embeddings, aggregation))
                    validation_ids.extend(ids)
                threshold, metrics = _best_threshold(validation_ids, inner_scores, labels)
                options.append(
                    {"c_value": c_value, "aggregation": aggregation, "threshold": threshold, "inner_metrics": metrics}
                )
        selected = max(
            options,
            key=lambda item: (
                min(item["inner_metrics"]["sensitivity"], item["inner_metrics"]["specificity"]),
                item["inner_metrics"]["balanced_accuracy"],
                -item["c_value"],
                -aggregations.index(item["aggregation"]),
            ),
        )
        model = _fit(
            outer["train_case_ids"], embeddings, targets,
            c_value=selected["c_value"], seed=seed + outer["outer_fold"], max_iter=max_iter,
            model_family=model_family,
        )
        test_scores = _scores(model, outer["test_case_ids"], embeddings, selected["aggregation"])
        model_path = output_root / f"outer_fold_{outer['outer_fold']}.joblib"
        _atomic_model(model, model_path)
        selections.append(
            {
                "outer_fold": outer["outer_fold"], **selected,
                "model_sha256": sha256_file(model_path),
                "held_out_case_or_candidate_labels_used": False,
            }
        )
        for case_id in outer["test_case_ids"]:
            score = test_scores.get(case_id)
            predictions.append(
                {
                    "schema": "argos-hybrid-patch25d-oof-prediction-v1",
                    "case_id": case_id,
                    "outer_fold": outer["outer_fold"],
                    "score": score,
                    "threshold": selected["threshold"],
                    "prediction": "TECHNICAL_FAILURE" if score is None else (
                        "POSITIVE" if score >= selected["threshold"] else "NEGATIVE"
                    ),
                    "candidate_count": len(embeddings.get(case_id, [])),
                    "technical_failure": score is None,
                    "ground_truth_in_artifact": False,
                    "research_only": True,
                }
            )
    predictions.sort(key=lambda row: row["case_id"])
    predictions_path = output_root / "oof_predictions.jsonl"
    predictions_path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in predictions), encoding="utf-8"
    )
    selections_path = output_root / "fold_selection.json"
    selections_path.write_text(json.dumps(selections, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    body = {
        "schema": "argos-hybrid-patch25d-oof-freeze-v1",
        "status": "frozen_before_final_metric_calculation",
        "candidate_id": config["candidate_id"],
        "case_count": len(predictions),
        "technical_failure_count": sum(row["technical_failure"] for row in predictions),
        "embedding_signature": embedding_manifest["embedding_signature"],
        "target_signature": target_manifest["target_signature"],
        "splits_sha256": sha256_file(splits_path),
        "config_sha256": sha256_file(config_path),
        "oof_predictions_sha256": sha256_file(predictions_path),
        "fold_selection_sha256": sha256_file(selections_path),
        "held_out_labels_used_for_fit_or_threshold": False,
        "lesion_masks_used_for_training_targets_only": True,
        "lesion_masks_used_at_inference": False,
        "research_only": True,
    }
    freeze = {**body, "prediction_signature": canonical_sha256(body)}
    (output_root / "prediction_freeze.json").write_text(
        json.dumps(freeze, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return freeze


def _wilson(successes: int, total: int) -> list[float]:
    z = 1.959963984540054
    p = successes / total
    denominator = 1 + z * z / total
    center = (p + z * z / (2 * total)) / denominator
    margin = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / denominator
    return [center - margin, center + margin]


def _auc(labels: list[int], scores: list[float]) -> float:
    positives = [score for label, score in zip(labels, scores) if label]
    negatives = [score for label, score in zip(labels, scores) if not label]
    return sum(1 if p > n else 0.5 if p == n else 0 for p in positives for n in negatives) / (
        len(positives) * len(negatives)
    )


def evaluate_oof(
    *,
    prediction_root: Path,
    embedding_root: Path,
    target_root: Path,
    output_root: Path,
) -> dict[str, Any]:
    output_root = Path(output_root).resolve()
    if output_root.exists():
        raise PipelineError("Avaliação 2.5D já existe.")
    output_root.mkdir(parents=True)
    freeze = _json(Path(prediction_root) / "prediction_freeze.json")
    unsigned = dict(freeze)
    signature = unsigned.pop("prediction_signature")
    if signature != canonical_sha256(unsigned):
        raise PipelineError("Freeze 2.5D alterado.")
    predictions_path = Path(prediction_root) / "oof_predictions.jsonl"
    if sha256_file(predictions_path) != freeze["oof_predictions_sha256"]:
        raise PipelineError("Predições 2.5D alteradas.")
    predictions = _jsonl(predictions_path)
    _, _, labels = _load_inputs(embedding_root, target_root)
    # Each outer fold owns its threshold; recompute discrete confusion exactly.
    tp = tn = fp = fn = failures = 0
    auc_labels: list[int] = []
    auc_scores: list[float] = []
    for row in predictions:
        positive = labels[row["case_id"]] == "POSITIVE"
        if row["technical_failure"]:
            failures += 1
            if positive: fn += 1
            else: fp += 1
            continue
        predicted = row["prediction"] == "POSITIVE"
        if positive and predicted: tp += 1
        elif not positive and not predicted: tn += 1
        elif positive: fn += 1
        else: fp += 1
        auc_labels.append(int(positive))
        auc_scores.append(float(row["score"]))
    sensitivity, specificity = tp / (tp + fn), tn / (tn + fp)
    body = {
        "schema": "argos-hybrid-patch25d-oof-evaluation-v1",
        "candidate_id": freeze["candidate_id"],
        "prediction_signature": freeze["prediction_signature"],
        "overall": {
            "case_count": len(predictions), "tp": tp, "tn": tn, "fp": fp, "fn": fn,
            "technical_failures": failures, "sensitivity": sensitivity,
            "specificity": specificity, "balanced_accuracy": (sensitivity + specificity) / 2,
            "roc_auc_computable_cases": _auc(auc_labels, auc_scores),
            "sensitivity_ci95_wilson": _wilson(tp, tp + fn),
            "specificity_ci95_wilson": _wilson(tn, tn + fp),
            "passed_75_75": sensitivity >= 0.75 and specificity >= 0.75,
        },
        "methodology": {
            "patient_grouped_nested_cv": True,
            "candidate_supervision_from_training_masks_only": True,
            "outer_predictions_only": True,
            "technical_failures_count_as_errors": True,
            "external_blind_validation": False,
        },
        "lesion_masks_used_at_inference": False,
        "research_only": True,
    }
    result = {**body, "evaluation_signature": canonical_sha256(body)}
    (output_root / "evaluation.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return result
