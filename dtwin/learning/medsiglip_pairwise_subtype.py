"""Nested OOF pairwise subtype head for single-phase MedSigLIP embeddings.

This is a research-only characterization head.  It never changes the frozen
HCC-vs-benign decision and it never reads lesion masks.  Every one-vs-one model
is fitted only with training-fold cases; held-out class probabilities are
persisted without ground truth and evaluated in a separate step.
"""
from __future__ import annotations

import itertools
import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import numpy as np
import yaml
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from dtwin.core import PipelineError
from dtwin.learning.medsiglip_embeddings import verify_embeddings
from dtwin.learning.medsiglip_multiclass_classifier import (
    _aggregate,
    _json,
    _jsonl,
    _load_embedding_map,
    _subtype_classification_metrics,
    build_multiclass_labels,
    restrict_splits,
)
from dtwin.learning.protocol import (
    canonical_sha256,
    load_protected_cases,
    load_protected_label_rows,
    sha256_file,
    verify_protocol,
)
from dtwin.learning.robustness import clinical_subtype_map
from dtwin.learning.splits import validate_nested_splits

CONFIG_SCHEMA = "argos-hybrid-medsiglip-pairwise-subtype-config-v1"
PREDICTION_SCHEMA = "argos-hybrid-medsiglip-pairwise-subtype-oof-prediction-v1"
FREEZE_SCHEMA = "argos-hybrid-medsiglip-pairwise-subtype-oof-freeze-v1"
EVALUATION_SCHEMA = "argos-hybrid-medsiglip-pairwise-subtype-oof-evaluation-v1"


def load_pairwise_config(path: Path) -> dict[str, Any]:
    try:
        value = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise PipelineError(f"Config pairwise inválida: {path}") from exc
    if not isinstance(value, dict) or value.get("schema") != CONFIG_SCHEMA:
        raise PipelineError("Schema pairwise inválido.")
    classes = value.get("class_names")
    if (
        not isinstance(classes, list)
        or len(classes) < 3
        or len(classes) != len(set(classes))
        or any(not str(item).strip() for item in classes)
    ):
        raise PipelineError("class_names deve conter ao menos três classes únicas.")
    c_grid = value.get("regularization_c_grid")
    if not isinstance(c_grid, list) or not c_grid or any(float(v) <= 0 for v in c_grid):
        raise PipelineError("Grid C pairwise inválido.")
    aggregations = value.get("panel_probability_aggregations")
    allowed = {"mean", "max", "top2_mean"}
    if not isinstance(aggregations, list) or not aggregations or any(v not in allowed for v in aggregations):
        raise PipelineError("Agregações pairwise inválidas.")
    if value.get("selection_objective") != "inner_macro_recall_only":
        raise PipelineError("Seleção pairwise deve usar macro recall interno.")
    if value.get("binary_decision_unchanged") is not True:
        raise PipelineError("O braço pairwise não pode alterar a decisão binária.")
    if value.get("technical_failures_count_as_errors") is not True:
        raise PipelineError("Falhas técnicas devem contar como erros.")
    return value


def class_pairs(class_names: Iterable[str]) -> list[tuple[str, str]]:
    names = sorted(str(value) for value in class_names)
    return list(itertools.combinations(names, 2))


def _fit_pair_models(
    case_ids: Iterable[str],
    embedding_map: dict[str, list[np.ndarray]],
    class_by_case: dict[str, str],
    class_names: list[str],
    *,
    c_value: float,
    seed: int,
    max_iter: int,
) -> dict[tuple[str, str], Pipeline]:
    models: dict[tuple[str, str], Pipeline] = {}
    ids = list(case_ids)
    for pair_index, (left, right) in enumerate(class_pairs(class_names)):
        matrix: list[np.ndarray] = []
        labels: list[int] = []
        for case_id in ids:
            subtype = class_by_case[case_id]
            if subtype not in (left, right):
                continue
            for vector in embedding_map.get(case_id, []):
                matrix.append(vector)
                labels.append(int(subtype == right))
        if not matrix or set(labels) != {0, 1}:
            raise PipelineError(f"Fold sem as duas classes do par {left}/{right}.")
        model = Pipeline(
            [
                ("scaler", StandardScaler()),
                (
                    "classifier",
                    LogisticRegression(
                        C=float(c_value),
                        class_weight="balanced",
                        max_iter=int(max_iter),
                        random_state=int(seed) + pair_index,
                        solver="lbfgs",
                    ),
                ),
            ]
        )
        model.fit(np.stack(matrix), np.asarray(labels, dtype=np.int64))
        models[(left, right)] = model
    return models


def pairwise_probability_mass(
    models: dict[tuple[str, str], Pipeline],
    vectors: list[np.ndarray],
    class_names: list[str],
    aggregation: str,
) -> dict[str, float]:
    """Borda-style probability coupling over all one-vs-one comparisons."""
    if not vectors:
        raise PipelineError("Caso sem embedding para inferência pairwise.")
    matrix = np.stack(vectors)
    votes = {name: 0.0 for name in class_names}
    expected = set(class_pairs(class_names))
    if set(models) != expected:
        raise PipelineError("Coleção incompleta de modelos pairwise.")
    for left, right in sorted(models):
        probability_right = models[(left, right)].predict_proba(matrix)[:, 1]
        p_right = _aggregate(probability_right.tolist(), aggregation)
        votes[left] += 1.0 - p_right
        votes[right] += p_right
    total = float(sum(votes.values()))
    if not np.isfinite(total) or total <= 0:
        raise PipelineError("Massa pairwise inválida.")
    return {name: float(votes[name] / total) for name in class_names}


def _case_masses(
    models: dict[tuple[str, str], Pipeline],
    case_ids: Iterable[str],
    embedding_map: dict[str, list[np.ndarray]],
    class_names: list[str],
    aggregation: str,
) -> dict[str, dict[str, float]]:
    return {
        case_id: pairwise_probability_mass(models, vectors, class_names, aggregation)
        for case_id in case_ids
        if (vectors := embedding_map.get(case_id, []))
    }


def _macro_recall(
    case_ids: Iterable[str],
    masses: dict[str, dict[str, float]],
    class_by_case: dict[str, str],
    class_names: list[str],
) -> dict[str, Any]:
    hits = {name: 0 for name in class_names}
    totals = {name: 0 for name in class_names}
    failures = 0
    for case_id in case_ids:
        truth = class_by_case[case_id]
        totals[truth] += 1
        if case_id not in masses:
            failures += 1
            continue
        predicted = max(masses[case_id], key=masses[case_id].get)
        hits[truth] += int(predicted == truth)
    recalls = {name: hits[name] / totals[name] if totals[name] else 0.0 for name in class_names}
    return {
        "balanced_accuracy": float(np.mean(list(recalls.values()))),
        "top1_accuracy": sum(hits.values()) / sum(totals.values()),
        "recall_by_subtype": recalls,
        "technical_failures": failures,
    }


def _inner_oof_masses(
    inner_folds: list[dict[str, Any]],
    embedding_map: dict[str, list[np.ndarray]],
    class_by_case: dict[str, str],
    class_names: list[str],
    *,
    c_value: float,
    aggregation: str,
    seed: int,
    max_iter: int,
) -> tuple[list[str], dict[str, dict[str, float]]]:
    validation_ids: list[str] = []
    masses: dict[str, dict[str, float]] = {}
    for inner in inner_folds:
        models = _fit_pair_models(
            inner["train_case_ids"], embedding_map, class_by_case, class_names,
            c_value=c_value, seed=seed + int(inner["inner_fold"]), max_iter=max_iter,
        )
        current_ids = list(inner["validation_case_ids"])
        current = _case_masses(models, current_ids, embedding_map, class_names, aggregation)
        if set(masses) & set(current):
            raise PipelineError("Predição pairwise interna duplicada.")
        masses.update(current)
        validation_ids.extend(current_ids)
    if len(validation_ids) != len(set(validation_ids)):
        raise PipelineError("Caso repetido na validação pairwise interna.")
    return validation_ids, masses


def generate_pairwise_oof_predictions(
    *,
    pairwise_config_path: Path,
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
        raise PipelineError("Predições pairwise já existem; saída é imutável.")
    output_root.mkdir(parents=True)
    config = load_pairwise_config(pairwise_config_path)
    protocol = verify_protocol(
        config_path=training_protocol_config_path,
        workspace_root=workspace_root,
        protocol_path=training_protocol_path,
        splits_path=splits_path,
    )
    embedding_manifest = verify_embeddings(candidate_root=candidate_root, output_root=embedding_root)
    splits = _json(splits_path, "Splits")
    validate_nested_splits(splits)
    protected_cases = load_protected_cases(training_protocol_config_path, workspace_root)
    allowed_datasets = set(config.get("restrict_to_dataset_ids", []))
    if allowed_datasets:
        protected_cases = [case for case in protected_cases if case.dataset_id in allowed_datasets]
        splits = restrict_splits(splits, {case.case_id for case in protected_cases})
    subtype_by_id = clinical_subtype_map(
        load_protected_label_rows(training_protocol_config_path, workspace_root)
    )
    class_by_case, _ = build_multiclass_labels(protected_cases, subtype_by_id)
    class_names = sorted(str(value) for value in config["class_names"])
    observed = set(class_by_case.values())
    if observed != set(class_names):
        raise PipelineError(f"Classes pairwise divergentes: esperado={class_names}, observado={sorted(observed)}")
    embedding_map, candidate_map = _load_embedding_map(embedding_root)
    seed = int(config.get("seed", 20260803))
    max_iter = int(config.get("max_iter", 3000))
    aggregations = list(config["panel_probability_aggregations"])
    predictions: list[dict[str, Any]] = []
    selections: list[dict[str, Any]] = []
    protected_by_id = {case.case_id: case for case in protected_cases}

    for outer in splits["outer_folds"]:
        if not outer["test_case_ids"]:
            continue
        outer_index = int(outer["outer_fold"])
        options = []
        for c_value in [float(v) for v in config["regularization_c_grid"]]:
            for aggregation in aggregations:
                validation_ids, masses = _inner_oof_masses(
                    list(outer["inner_folds"]), embedding_map, class_by_case, class_names,
                    c_value=c_value, aggregation=aggregation,
                    seed=seed + outer_index * 100, max_iter=max_iter,
                )
                metrics = _macro_recall(validation_ids, masses, class_by_case, class_names)
                options.append({
                    "c_value": c_value,
                    "aggregation": aggregation,
                    "inner_metrics": metrics,
                })
        selected = max(
            options,
            key=lambda item: (
                item["inner_metrics"]["balanced_accuracy"],
                item["inner_metrics"]["top1_accuracy"],
                -item["c_value"],
                -aggregations.index(item["aggregation"]),
            ),
        )
        models = _fit_pair_models(
            outer["train_case_ids"], embedding_map, class_by_case, class_names,
            c_value=selected["c_value"], seed=seed + outer_index, max_iter=max_iter,
        )
        masses = _case_masses(
            models, outer["test_case_ids"], embedding_map, class_names, selected["aggregation"]
        )
        selections.append({
            "outer_fold": outer_index,
            **selected,
            "held_out_labels_used_for_fit_or_selection": False,
        })
        for case_id in outer["test_case_ids"]:
            mass = masses.get(case_id)
            predictions.append({
                "schema": PREDICTION_SCHEMA,
                "case_id": case_id,
                "patient_group_id": protected_by_id[case_id].patient_group_id,
                "dataset_id": protected_by_id[case_id].dataset_id,
                "outer_fold": outer_index,
                "panel_count": len(candidate_map.get(case_id, [])),
                "class_probabilities": mass,
                "predicted_class": max(mass, key=mass.get) if mass else "TECHNICAL_FAILURE",
                "technical_failure": mass is None,
                "aggregation": selected["aggregation"],
                "model_c": selected["c_value"],
                "ground_truth_in_artifact": False,
                "held_out_label_used": False,
                "changes_binary_decision": False,
                "research_only": True,
            })
    predictions.sort(key=lambda row: row["case_id"])
    if {row["case_id"] for row in predictions} != set(protected_by_id):
        raise PipelineError("Predições pairwise não cobrem toda a coorte restrita.")
    prediction_path = output_root / "oof_predictions.jsonl"
    prediction_path.write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in predictions),
        encoding="utf-8",
    )
    selection_path = output_root / "fold_selection.json"
    selection_path.write_text(json.dumps(selections, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    body = {
        "schema": FREEZE_SCHEMA,
        "status": "frozen_before_protected_subtype_evaluation",
        "candidate_id": config["candidate_id"],
        "class_names": class_names,
        "pair_count": len(class_pairs(class_names)),
        "prediction_count": len(predictions),
        "technical_failure_count": sum(row["technical_failure"] for row in predictions),
        "training_protocol_signature": protocol["protocol_signature"],
        "embedding_signature": embedding_manifest["embedding_signature"],
        "config_sha256": sha256_file(pairwise_config_path),
        "splits_sha256": sha256_file(splits_path),
        "oof_predictions_sha256": sha256_file(prediction_path),
        "fold_selection_sha256": sha256_file(selection_path),
        "held_out_labels_used_for_fit_or_selection": False,
        "individual_ground_truth_persisted": False,
        "binary_decision_unchanged": True,
        "lesion_masks_read": 0,
        "research_only": True,
        "clinical_use_allowed": False,
    }
    freeze = {**body, "prediction_signature": canonical_sha256(body)}
    (output_root / "prediction_freeze.json").write_text(
        json.dumps(freeze, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return freeze


def evaluate_pairwise_oof_predictions(
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
        raise PipelineError("Avaliação pairwise já existe; saída é imutável.")
    output_root.mkdir(parents=True)
    protocol = verify_protocol(
        config_path=training_protocol_config_path, workspace_root=workspace_root,
        protocol_path=training_protocol_path, splits_path=splits_path,
    )
    freeze = _json(Path(prediction_root) / "prediction_freeze.json", "Freeze pairwise")
    unsigned = dict(freeze)
    signature = unsigned.pop("prediction_signature", None)
    if signature != canonical_sha256(unsigned):
        raise PipelineError("Assinatura pairwise diverge.")
    prediction_path = Path(prediction_root) / "oof_predictions.jsonl"
    if freeze.get("oof_predictions_sha256") != sha256_file(prediction_path):
        raise PipelineError("Predições pairwise foram alteradas.")
    rows = _jsonl(prediction_path, "Predições pairwise")
    if any("label" in row or "ground_truth" in row for row in rows):
        raise PipelineError("Predições pairwise contêm ground truth.")
    subtype_by_id = clinical_subtype_map(
        load_protected_label_rows(training_protocol_config_path, workspace_root)
    )
    metrics = _subtype_classification_metrics(rows, subtype_by_id, freeze["class_names"])
    baseline_balanced = 0.4888009873765622
    baseline_top1 = 0.564179104477612
    body = {
        "schema": EVALUATION_SCHEMA,
        "candidate_id": freeze["candidate_id"],
        "training_protocol_signature": protocol["protocol_signature"],
        "prediction_signature": freeze["prediction_signature"],
        "subtype_metrics": metrics,
        "comparison_to_prespecified_baseline": {
            "baseline_balanced_accuracy": baseline_balanced,
            "baseline_top1_accuracy": baseline_top1,
            "minimum_absolute_balanced_accuracy_gain": 0.05,
            "minimum_top1_accuracy": 0.60,
            "balanced_accuracy_gain": metrics["balanced_accuracy"] - baseline_balanced,
            "top1_accuracy_gain": metrics["top1_accuracy"] - baseline_top1,
            "passed_experimental_gate": (
                metrics["balanced_accuracy"] >= baseline_balanced + 0.05
                and metrics["top1_accuracy"] >= 0.60
            ),
        },
        "binary_decision_unchanged": True,
        "lesion_masks_read": 0,
        "external_validation": False,
        "research_only": True,
        "clinical_use_allowed": False,
    }
    evaluation = {**body, "evaluation_signature": canonical_sha256(body)}
    (output_root / "evaluation.json").write_text(
        json.dumps(evaluation, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return evaluation
