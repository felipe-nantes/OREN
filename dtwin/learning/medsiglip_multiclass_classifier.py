"""Multiclass-supervised classifier over the frozen MedSigLIP embeddings.

Motivation. Phase 5 trained a BINARY head (POSITIVE vs NEGATIVE) on these same
embeddings and reached 72,27%/73,28%. Etapa A then showed the specificity
deficit is not spread across mimickers: it is concentrated almost entirely in
one bucket (hepatic cyst, ~42% called positive), and performance tracks lesion
conspicuity rather than lesion characterization. Etapa B tried to inject an
explicit hand-engineered enhancement feature and failed, consistent with the
project's broader pattern that learned representations carry the signal.

This module tests a different lever on the SAME representation: give the head
finer labels instead of a finer feature. LLD-MMRI declares the actual lesion
type per case (hcc / hemangioma / hepatic_cyst / fnh — discovered in Etapa A),
so the head can be trained to say WHICH lesion it sees, and the binary decision
is then derived as the total probability mass on the positive classes. The
hypothesis is that being forced to separate cyst from hcc explicitly yields a
better boundary than being told only "abnormal or not".

Design is deliberately an apples-to-apples ablation against Phase 5: same
embeddings, same frozen nested splits, same model family, same panel
aggregations, same inner-CV threshold selection, same failure policy. The only
difference is the label granularity used during fitting. Phase 5's artifacts
are never modified.

Label space. Fine labels exist only for LLD-MMRI; OpenSwissHCC declares just
the binary endpoint. Rather than invent a subtype for OpenSwiss cases (its
positives are not documented as specifically HCC in the protected source), they
keep explicitly unspecified classes. No label information is fabricated, and
the binary endpoint is unchanged.
"""
from __future__ import annotations

import json
import math
import os
import tempfile
from collections import defaultdict
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
    load_protected_label_rows,
    sha256_file,
    verify_protocol,
)
from dtwin.learning.robustness import clinical_subtype_map
from dtwin.learning.splits import validate_nested_splits


CONFIG_SCHEMA = "argos-hybrid-medsiglip-multiclass-config-v1"
PREDICTION_SCHEMA = "argos-hybrid-medsiglip-multiclass-oof-prediction-v1"
PREDICTION_FREEZE_SCHEMA = "argos-hybrid-medsiglip-multiclass-oof-freeze-v1"
EVALUATION_SCHEMA = "argos-hybrid-medsiglip-multiclass-oof-evaluation-v1"

# Classes for cases whose cohort declares only the binary endpoint.
POSITIVE_UNSPECIFIED = "positive_unspecified"
NEGATIVE_UNSPECIFIED = "negative_unspecified"


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


def load_multiclass_config(path: Path) -> dict[str, Any]:
    try:
        value = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise PipelineError(f"Config multiclasse inválida: {path}") from exc
    if not isinstance(value, dict) or value.get("schema") != CONFIG_SCHEMA:
        raise PipelineError("Schema multiclasse inválido.")
    aggregations = value.get("panel_probability_aggregations")
    allowed = {"mean", "max", "top2_mean"}
    if not isinstance(aggregations, list) or not aggregations:
        raise PipelineError("Agregações de painel ausentes.")
    if any(item not in allowed for item in aggregations):
        raise PipelineError("Agregação de painel inválida.")
    c_grid = value.get("regularization_c_grid")
    if not isinstance(c_grid, list) or not c_grid or any(float(v) <= 0 for v in c_grid):
        raise PipelineError("Grid C inválido.")
    positive_classes = value.get("positive_classes")
    if not isinstance(positive_classes, list) or not positive_classes:
        raise PipelineError("positive_classes deve ser lista não vazia.")
    if value.get("threshold_selection") != "inner_oof_only":
        raise PipelineError("Threshold deve ser selecionado só no inner CV.")
    if value.get("technical_failures_count_as_errors") is not True:
        raise PipelineError("Falhas técnicas devem contar como erros.")
    return value


def build_multiclass_labels(
    protected_cases: Iterable[Any], subtype_by_id: dict[str, str]
) -> tuple[dict[str, str], dict[str, int]]:
    """Assign each case its finest available label, without inventing detail.

    Returns ``(class_by_case, binary_by_case)``. Fails closed if a clinical
    subtype ever disagrees with the binary endpoint it is supposed to refine —
    that would mean the label sources contradict each other.
    """
    class_by_case: dict[str, str] = {}
    binary_by_case: dict[str, int] = {}
    polarity: dict[str, set[int]] = defaultdict(set)
    for case in protected_cases:
        binary = int(case.label == "POSITIVE")
        binary_by_case[case.case_id] = binary
        subtype = subtype_by_id.get(case.case_id)
        if subtype:
            label = subtype
        else:
            label = POSITIVE_UNSPECIFIED if binary else NEGATIVE_UNSPECIFIED
        class_by_case[case.case_id] = label
        polarity[label].add(binary)
    mixed = sorted(name for name, values in polarity.items() if len(values) > 1)
    if mixed:
        raise PipelineError(
            f"Classe clínica com polaridade binária inconsistente: {mixed}"
        )
    return class_by_case, binary_by_case


def resolve_positive_classes(
    configured: Iterable[str],
    class_by_case: dict[str, str],
    binary_by_case: dict[str, int],
) -> list[str]:
    """Validate the configured positive classes against the binary endpoint.

    Every class present in the cohort must be declared with the same polarity
    the protected binary labels already imply, so the derived binary decision
    cannot silently disagree with the frozen endpoint.
    """
    configured = [str(item) for item in configured]
    present = sorted(set(class_by_case.values()))
    implied_positive = {
        label
        for label in present
        if any(
            binary_by_case[case_id] == 1
            for case_id, value in class_by_case.items()
            if value == label
        )
    }
    unknown = sorted(set(configured) - set(present))
    if unknown:
        raise PipelineError(f"positive_classes cita classe ausente da coorte: {unknown}")
    if set(configured) != implied_positive:
        raise PipelineError(
            "positive_classes divergem da polaridade dos labels protegidos: "
            f"configurado={sorted(configured)} implícito={sorted(implied_positive)}"
        )
    return sorted(configured)


def _load_embedding_map(embedding_root: Path) -> tuple[dict[str, list[np.ndarray]], dict[str, list[str]]]:
    rows = _jsonl(
        Path(embedding_root) / "embedding_records.jsonl", "Registros de embeddings"
    )
    vectors: dict[str, list[np.ndarray]] = defaultdict(list)
    candidates: dict[str, list[str]] = defaultdict(list)
    for row in rows:
        if row.get("label_attached") is not False:
            raise PipelineError("Embedding contém label.")
        case_id = str(row["case_id"])
        vector = np.load(
            Path(embedding_root) / str(row["embedding_path"]), allow_pickle=False
        ).astype(np.float64)
        if vector.ndim != 1 or not np.isfinite(vector).all():
            raise PipelineError(f"Embedding inválido em {case_id}.")
        vectors[case_id].append(vector)
        candidates[case_id].append(str(row["candidate_id"]))
    return dict(vectors), dict(candidates)


def _panel_matrix(
    case_ids: Iterable[str],
    embedding_map: dict[str, list[np.ndarray]],
    class_index: dict[str, int],
    class_by_case: dict[str, str],
) -> tuple[np.ndarray, np.ndarray]:
    values: list[np.ndarray] = []
    labels: list[int] = []
    for case_id in case_ids:
        for vector in embedding_map.get(case_id, []):
            values.append(vector)
            labels.append(class_index[class_by_case[case_id]])
    if not values:
        raise PipelineError("Treino multiclasse sem embeddings.")
    if len(set(labels)) < 2:
        raise PipelineError("Treino multiclasse requer ao menos duas classes.")
    return np.stack(values), np.asarray(labels, dtype=np.int64)


def _fit_model(
    case_ids: Iterable[str],
    embedding_map: dict[str, list[np.ndarray]],
    class_index: dict[str, int],
    class_by_case: dict[str, str],
    positive_indices: set[int],
    *,
    c_value: float,
    seed: int,
    max_iter: int,
) -> Pipeline:
    matrix, labels = _panel_matrix(case_ids, embedding_map, class_index, class_by_case)
    present = set(labels.tolist())
    if not (present & positive_indices):
        raise PipelineError("Treino multiclasse sem classe positiva presente.")
    if not (present - positive_indices):
        raise PipelineError("Treino multiclasse sem classe negativa presente.")
    model = Pipeline(
        [
            ("scaler", StandardScaler()),
            (
                "classifier",
                LogisticRegression(
                    C=float(c_value),
                    class_weight="balanced",
                    max_iter=max_iter,
                    random_state=seed,
                    solver="lbfgs",
                ),
            ),
        ]
    )
    model.fit(matrix, labels)
    return model


def _positive_probability(model: Pipeline, matrix: np.ndarray, positive_indices: set[int]) -> np.ndarray:
    """Binary score = probability mass on the positive classes."""
    probabilities = model.predict_proba(matrix)
    classes = list(model.named_steps["classifier"].classes_)
    columns = [index for index, label in enumerate(classes) if label in positive_indices]
    if not columns:
        raise PipelineError("Modelo multiclasse não expõe classe positiva.")
    return probabilities[:, columns].sum(axis=1)


def _aggregate(probabilities: list[float], method: str) -> float:
    if not probabilities:
        raise PipelineError("Não é possível agregar caso sem painel.")
    ordered = sorted((float(v) for v in probabilities), reverse=True)
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
    positive_indices: set[int],
    aggregation: str,
) -> dict[str, float]:
    result: dict[str, float] = {}
    for case_id in case_ids:
        vectors = embedding_map.get(case_id, [])
        if not vectors:
            continue
        scores = _positive_probability(model, np.stack(vectors), positive_indices)
        result[case_id] = _aggregate(scores.tolist(), aggregation)
    return result


def _confusion(
    case_ids: Iterable[str],
    scores: dict[str, float],
    binary_by_case: dict[str, int],
    threshold: float,
) -> dict[str, Any]:
    tp = tn = fp = fn = failures = 0
    for case_id in case_ids:
        label = binary_by_case[case_id]
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
    candidates = [0.0, 1.0, *unique]
    candidates.extend((a + b) / 2.0 for a, b in zip(unique, unique[1:]))
    return sorted(set(candidates))


def _best_threshold(
    case_ids: list[str], scores: dict[str, float], binary_by_case: dict[str, int]
) -> tuple[float, dict[str, Any]]:
    evaluated = [
        (threshold, _confusion(case_ids, scores, binary_by_case, threshold))
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
    class_index: dict[str, int],
    class_by_case: dict[str, str],
    binary_by_case: dict[str, int],
    positive_indices: set[int],
    c_value: float,
    aggregation: str,
    seed: int,
    max_iter: int,
) -> tuple[list[str], dict[str, float]]:
    validation_ids: list[str] = []
    scores: dict[str, float] = {}
    for inner in inner_folds:
        model = _fit_model(
            list(inner["train_case_ids"]),
            embedding_map,
            class_index,
            class_by_case,
            positive_indices,
            c_value=c_value,
            seed=seed + int(inner["inner_fold"]),
            max_iter=max_iter,
        )
        current_validation = list(inner["validation_case_ids"])
        current = _case_scores(
            model, current_validation, embedding_map, positive_indices, aggregation
        )
        if set(scores) & set(current):
            raise PipelineError("Score interno duplicado.")
        scores.update(current)
        validation_ids.extend(current_validation)
    if len(validation_ids) != len(set(validation_ids)):
        raise PipelineError("Caso repetido na validação interna.")
    return sorted(validation_ids), scores


def generate_oof_predictions(
    *,
    multiclass_config_path: Path,
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
        raise PipelineError("Predições multiclasse já existem; saída é imutável.")
    output_root.mkdir(parents=True)
    config = load_multiclass_config(multiclass_config_path)
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

    protected_cases = load_protected_cases(training_protocol_config_path, workspace_root)
    subtype_by_id = clinical_subtype_map(
        load_protected_label_rows(training_protocol_config_path, workspace_root)
    )
    class_by_case, binary_by_case = build_multiclass_labels(protected_cases, subtype_by_id)
    positive_classes = resolve_positive_classes(
        config["positive_classes"], class_by_case, binary_by_case
    )
    class_names = sorted(set(class_by_case.values()))
    class_index = {name: index for index, name in enumerate(class_names)}
    positive_indices = {class_index[name] for name in positive_classes}
    protected_by_id = {case.case_id: case for case in protected_cases}

    embedding_map, candidate_map = _load_embedding_map(embedding_root)
    c_grid = [float(v) for v in config["regularization_c_grid"]]
    aggregations = list(config["panel_probability_aggregations"])
    seed = int(config.get("seed", 20260724))
    max_iter = int(config.get("max_iter", 3000))

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
                    class_index=class_index,
                    class_by_case=class_by_case,
                    binary_by_case=binary_by_case,
                    positive_indices=positive_indices,
                    c_value=c_value,
                    aggregation=aggregation,
                    seed=seed + outer_index * 100,
                    max_iter=max_iter,
                )
                threshold, metrics = _best_threshold(
                    validation_ids, scores, binary_by_case
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
                min(item["inner_metrics"]["sensitivity"], item["inner_metrics"]["specificity"]),
                item["inner_metrics"]["balanced_accuracy"],
                -item["c_value"],
                -aggregations.index(item["aggregation"]),
            ),
        )
        model = _fit_model(
            outer_train_ids,
            embedding_map,
            class_index,
            class_by_case,
            positive_indices,
            c_value=selected["c_value"],
            seed=seed + outer_index,
            max_iter=max_iter,
        )
        test_scores = _case_scores(
            model, outer_test_ids, embedding_map, positive_indices, selected["aggregation"]
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
        selections.append(
            {
                "outer_fold": outer_index,
                **selected,
                "model_sha256": sha256_file(model_path),
                "outer_train_case_count": len(outer_train_ids),
                "outer_test_case_count": len(outer_test_ids),
                "held_out_labels_used_for_fit_or_threshold": False,
            }
        )
        for case_id in outer_test_ids:
            score = test_scores.get(case_id)
            predictions.append(
                {
                    "schema": PREDICTION_SCHEMA,
                    "case_id": case_id,
                    "patient_group_id": protected_by_id[case_id].patient_group_id,
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
        "class_names": class_names,
        "positive_classes": positive_classes,
        "class_case_counts": {
            name: sum(1 for value in class_by_case.values() if value == name)
            for name in class_names
        },
        "training_protocol_signature": protocol["protocol_signature"],
        "embedding_signature": embedding_manifest["embedding_signature"],
        "multiclass_config_sha256": sha256_file(multiclass_config_path),
        "splits_sha256": sha256_file(splits_path),
        "prediction_count": len(predictions),
        "technical_failure_count": sum(bool(row["technical_failure"]) for row in predictions),
        "oof_predictions_sha256": sha256_file(predictions_path),
        "fold_selection_sha256": sha256_file(selection_path),
        "individual_ground_truth_persisted": False,
        "held_out_labels_used_for_fit_or_threshold": False,
        "binary_endpoint_unchanged": True,
        "phase5_artifacts_modified": False,
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
    margin = z * math.sqrt(proportion * (1 - proportion) / total + z * z / (4 * total * total)) / denominator
    return [max(0.0, center - margin), min(1.0, center + margin)]


def _auc(labels: list[int], scores: list[float]) -> float | None:
    positives = [s for label, s in zip(labels, scores) if label == 1]
    negatives = [s for label, s in zip(labels, scores) if label == 0]
    if not positives or not negatives:
        return None
    wins = sum(1.0 if p > n else 0.5 if p == n else 0.0 for p in positives for n in negatives)
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
        raise PipelineError("Avaliação multiclasse já existe; saída é imutável.")
    output_root.mkdir(parents=True)
    protocol = verify_protocol(
        config_path=training_protocol_config_path,
        workspace_root=workspace_root,
        protocol_path=training_protocol_path,
        splits_path=splits_path,
    )
    freeze = _json(Path(prediction_root) / "prediction_freeze.json", "Freeze multiclasse")
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

    protected_cases = load_protected_cases(training_protocol_config_path, workspace_root)
    protected = {case.case_id: case for case in protected_cases}
    if {str(row["case_id"]) for row in predictions} != set(protected):
        raise PipelineError("Predições e labels não cobrem os mesmos casos.")
    subtype_by_id = clinical_subtype_map(
        load_protected_label_rows(training_protocol_config_path, workspace_root)
    )

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
            [row for row in predictions if protected[str(row["case_id"])].dataset_id == dataset_id]
        )
        for dataset_id in sorted({case.dataset_id for case in protected.values()})
    }
    by_clinical_subtype = {
        subtype: metrics_for(
            [row for row in predictions if subtype_by_id.get(str(row["case_id"])) == subtype]
        )
        for subtype in sorted(set(subtype_by_id.values()))
    }
    body = {
        "schema": EVALUATION_SCHEMA,
        "candidate_id": freeze["candidate_id"],
        "class_names": freeze["class_names"],
        "positive_classes": freeze["positive_classes"],
        "training_protocol_signature": protocol["protocol_signature"],
        "prediction_signature": freeze["prediction_signature"],
        "overall": overall,
        "by_dataset": by_dataset,
        "by_clinical_subtype": by_clinical_subtype,
        "methodology": {
            "patient_grouped_nested_cv": True,
            "outer_predictions_only": True,
            "inner_oof_model_and_threshold_selection": True,
            "multiclass_supervision_binary_endpoint": True,
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
