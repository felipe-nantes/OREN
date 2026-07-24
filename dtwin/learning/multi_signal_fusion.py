"""Nested OOF meta-fusion over already-frozen supervised signal scores.

Combines two or more previously frozen nested-OOF signals (for example the
Phase-5 frozen MedSigLIP linear classifier and the Phase-13 stage-3 LoRA
classifier) through a small L2-regularized logistic regression fit on the
signed margins of each base signal (``score - threshold``). Regularization
strength and decision threshold are selected exclusively within the inner
folds of the SAME frozen nested splits already used to produce every base
signal (``hybrid_v1_nested_splits.json``) — no new split is generated here.

This module never re-opens ground truth for the base signals themselves:
``score``/``threshold`` for each case are read straight from each source's
frozen ``oof_predictions.jsonl`` (already leave-outer-fold predictions).
Labels are loaded only to (a) fit this fusion's own parameters on cases
outside the current outer test fold, exactly like every prior phase, and (b)
compute final metrics. No case's fused score is ever produced by a model
that has seen that case's own true label — the fusion model for outer fold
k is fit exclusively on cases from the other folds.

``late_fusion.py`` (Phase 9, weighted-margin, exactly two hardcoded
signals) is intentionally left untouched: this module is a new, separate,
self-contained phase, following the project's convention of one module per
phase rather than mutating an already-frozen phase's code.
"""
from __future__ import annotations

import json
import math
import os
import tempfile
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import yaml
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
from dtwin.learning.schemas import ProtectedTrainingCase
from dtwin.learning.splits import validate_nested_splits


CONFIG_SCHEMA = "argos-hybrid-multi-signal-fusion-config-v1"
PREDICTION_SCHEMA = "argos-hybrid-multi-signal-fusion-oof-prediction-v1"
PREDICTION_FREEZE_SCHEMA = "argos-hybrid-multi-signal-fusion-oof-freeze-v1"
EVALUATION_SCHEMA = "argos-hybrid-multi-signal-fusion-oof-evaluation-v1"

V23_FREEZE_SCHEMA = "argos-v23-retrospective-phase4-prediction-freeze-v1"


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


def load_fusion_config(path: Path) -> dict[str, Any]:
    try:
        value = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise PipelineError(f"Config de fusão inválida: {path}") from exc
    if not isinstance(value, dict) or value.get("schema") != CONFIG_SCHEMA:
        raise PipelineError("Schema de fusão multi-sinal inválido.")
    signals = value.get("signals")
    if not isinstance(signals, list) or len(signals) < 2:
        raise PipelineError("Fusão multi-sinal exige ao menos dois sinais.")
    names = [str(item.get("name")) for item in signals]
    if len(names) != len(set(names)) or any(not name or name == "None" for name in names):
        raise PipelineError("Nomes de sinal ausentes ou duplicados.")
    c_grid = value.get("regularization_c_grid")
    if not isinstance(c_grid, list) or not c_grid or any(float(item) <= 0 for item in c_grid):
        raise PipelineError("Grid de regularização inválido.")
    if value.get("weight_selection") != "inner_oof_only":
        raise PipelineError("Pesos da fusão devem ser selecionados só no inner CV.")
    if value.get("threshold_selection") != "inner_oof_only":
        raise PipelineError("Threshold da fusão deve ser selecionado só no inner CV.")
    if value.get("technical_failures_count_as_errors") is not True:
        raise PipelineError("Falhas técnicas devem contar como erros.")
    return value


def _verify_medsiglip_style_signal(
    root: Path, *, prediction_schema: str, freeze_schema: str
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Verify a frozen nested-OOF signal produced by a MedSigLIP-family module
    (Phase 5 linear classifier, Phase 13 head/partial/LoRA — they all share
    the same freeze shape: ``prediction_freeze.json`` + ``oof_predictions.jsonl``,
    signed with ``prediction_signature``)."""
    freeze = _json(root / "prediction_freeze.json", f"Freeze do sinal {root.name}")
    if freeze.get("schema") != freeze_schema:
        raise PipelineError(f"Schema de freeze inesperado em {root}.")
    unsigned = dict(freeze)
    signature = unsigned.pop("prediction_signature", None)
    if signature != canonical_sha256(unsigned):
        raise PipelineError(f"Assinatura do sinal diverge em {root}.")
    predictions_path = root / "oof_predictions.jsonl"
    if freeze.get("oof_predictions_sha256") != sha256_file(predictions_path):
        raise PipelineError(f"Predições do sinal foram alteradas em {root}.")
    if freeze.get("held_out_labels_used_for_fit_or_threshold") is not False:
        raise PipelineError(f"Sinal usou label do holdout na seleção em {root}.")
    rows = _jsonl(predictions_path, f"Predições do sinal {root.name}")
    if any(row.get("schema") != prediction_schema for row in rows):
        raise PipelineError(f"Registro de predição com schema inesperado em {root}.")
    return freeze, rows


def _verify_v23(root: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Verify the historical v23 retrospective OOF source (132 OpenSwissHCC
    cases). Duplicated from ``late_fusion.py`` on purpose: this module stays
    self-contained and never imports Phase 9's already-frozen code."""
    summary = _json(root / "summary.json", "Freeze v23")
    predictions_path = root / "loocv_predictions.jsonl"
    if (
        summary.get("schema") != V23_FREEZE_SCHEMA
        or summary.get("status") != "phase4_patient_level_oof_predictions_frozen"
        or summary.get("artifacts", {}).get("loocv_predictions_sha256")
        != sha256_file(predictions_path)
        or summary.get("threshold_fit_on_outer_training_only") is not True
        or summary.get("technical_failures_must_count_as_errors_during_evaluation") is not True
    ):
        raise PipelineError("Fonte OOF v23 não satisfaz o contrato congelado.")
    rows = _jsonl(predictions_path, "Predições v23")
    if len(rows) != 132 or len({row["case_id"] for row in rows}) != 132:
        raise PipelineError("Cobertura v23 divergente.")
    return summary, rows


def load_signal_scores(
    root: Path,
    *,
    prediction_schema: str,
    freeze_schema: str,
) -> dict[str, dict[str, Any]]:
    """Read one frozen signal's OOF scores into ``case_id -> {score, threshold,
    technical_failure}``. Handles both the MedSigLIP-family freeze shape and
    the historical v23 shape transparently based on the declared schema."""
    root = Path(root)
    if freeze_schema == V23_FREEZE_SCHEMA:
        _, rows = _verify_v23(root)
        return {
            str(row["case_id"]): {
                "score": row.get("score"),
                "threshold": row.get("threshold"),
                "technical_failure": row.get("score") is None
                or row.get("status") != "complete_out_of_fold_prediction",
            }
            for row in rows
        }
    _, rows = _verify_medsiglip_style_signal(
        root, prediction_schema=prediction_schema, freeze_schema=freeze_schema
    )
    return {
        str(row["case_id"]): {
            "score": row.get("score"),
            "threshold": row.get("threshold"),
            "technical_failure": bool(row.get("technical_failure")),
        }
        for row in rows
    }


def align_signals(
    signal_scores: dict[str, dict[str, dict[str, Any]]],
    protected_cases: Iterable[ProtectedTrainingCase],
) -> tuple[list[str], dict[str, ProtectedTrainingCase]]:
    """Intersect case coverage across every signal and the protected label
    source. Case metadata (label, patient_group_id, dataset_id) always comes
    from the authoritative protected source, never from a per-signal
    artifact, so every fusion signal is joined the same trustworthy way."""
    protected_by_id = {case.case_id: case for case in protected_cases}
    universes = [set(scores) for scores in signal_scores.values()]
    common = set(protected_by_id)
    for universe in universes:
        common &= universe
    if not common:
        raise PipelineError("Nenhum caso comum entre os sinais e os labels protegidos.")
    return sorted(common), protected_by_id


def _feature_vector(
    case_id: str, signal_scores: dict[str, dict[str, dict[str, Any]]], signal_names: list[str]
) -> np.ndarray | None:
    values: list[float] = []
    for name in signal_names:
        entry = signal_scores[name].get(case_id)
        if (
            entry is None
            or entry.get("technical_failure")
            or entry.get("score") is None
            or entry.get("threshold") is None
        ):
            return None
        values.append(float(entry["score"]) - float(entry["threshold"]))
    return np.asarray(values, dtype=np.float64)


def score_correlation(
    signal_scores: dict[str, dict[str, dict[str, Any]]], signal_a: str, signal_b: str
) -> float | None:
    """Pearson correlation between two signals' raw scores over their shared,
    technical-failure-free cases. Pure diagnostic — no labels involved."""
    common = sorted(set(signal_scores[signal_a]) & set(signal_scores[signal_b]))
    a: list[float] = []
    b: list[float] = []
    for case_id in common:
        left, right = signal_scores[signal_a][case_id], signal_scores[signal_b][case_id]
        if (
            left.get("technical_failure")
            or right.get("technical_failure")
            or left.get("score") is None
            or right.get("score") is None
        ):
            continue
        a.append(float(left["score"]))
        b.append(float(right["score"]))
    if len(a) < 2:
        return None
    matrix = np.corrcoef(np.asarray(a), np.asarray(b))
    return float(matrix[0, 1])


def _fit_meta_model(
    train_ids: list[str],
    signal_scores: dict[str, dict[str, dict[str, Any]]],
    signal_names: list[str],
    label_map: dict[str, int],
    *,
    c_value: float,
    seed: int,
    max_iter: int,
) -> Pipeline:
    features: list[np.ndarray] = []
    labels: list[int] = []
    for case_id in train_ids:
        vector = _feature_vector(case_id, signal_scores, signal_names)
        if vector is None:
            continue
        features.append(vector)
        labels.append(label_map[case_id])
    if not features or len(set(labels)) != 2:
        raise PipelineError("Treino da fusão requer casos válidos nas duas classes.")
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
    model.fit(np.stack(features), np.asarray(labels, dtype=np.int64))
    return model


def _meta_scores(
    model: Pipeline,
    case_ids: Iterable[str],
    signal_scores: dict[str, dict[str, dict[str, Any]]],
    signal_names: list[str],
) -> dict[str, float | None]:
    result: dict[str, float | None] = {}
    for case_id in case_ids:
        vector = _feature_vector(case_id, signal_scores, signal_names)
        if vector is None:
            result[case_id] = None
            continue
        result[case_id] = float(model.predict_proba(vector.reshape(1, -1))[0, 1])
    return result


def _confusion(
    case_ids: Iterable[str],
    scores: dict[str, float | None],
    label_map: dict[str, int],
    threshold: float,
) -> dict[str, Any]:
    tp = tn = fp = fn = failures = 0
    for case_id in case_ids:
        label = label_map[case_id]
        score = scores.get(case_id)
        if score is None:
            failures += 1
            if label == 1:
                fn += 1
            else:
                fp += 1
            continue
        prediction = int(score >= threshold)
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


def _threshold_candidates(scores: dict[str, float | None]) -> list[float]:
    unique = sorted({value for value in scores.values() if value is not None})
    if not unique:
        raise PipelineError("Scores internos ausentes para seleção de threshold.")
    candidates = [0.0, 1.0]
    candidates.extend(unique)
    candidates.extend((left + right) / 2.0 for left, right in zip(unique, unique[1:]))
    return sorted(set(candidates))


def _best_threshold(
    case_ids: list[str], scores: dict[str, float | None], label_map: dict[str, int]
) -> tuple[float, dict[str, Any]]:
    evaluated = [
        (threshold, _confusion(case_ids, scores, label_map, threshold))
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
    signal_scores: dict[str, dict[str, dict[str, Any]]],
    signal_names: list[str],
    label_map: dict[str, int],
    c_value: float,
    seed: int,
    max_iter: int,
) -> tuple[list[str], dict[str, float | None]]:
    validation_ids: list[str] = []
    scores: dict[str, float | None] = {}
    for inner in inner_folds:
        train_ids = [cid for cid in inner["train_case_ids"] if cid in label_map]
        current_validation = [cid for cid in inner["validation_case_ids"] if cid in label_map]
        if not current_validation:
            continue
        model = _fit_meta_model(
            train_ids,
            signal_scores,
            signal_names,
            label_map,
            c_value=c_value,
            seed=seed + int(inner["inner_fold"]),
            max_iter=max_iter,
        )
        current_scores = _meta_scores(model, current_validation, signal_scores, signal_names)
        overlap = set(scores) & set(current_scores)
        if overlap:
            raise PipelineError("Score interno duplicado na fusão.")
        scores.update(current_scores)
        validation_ids.extend(current_validation)
    if len(validation_ids) != len(set(validation_ids)):
        raise PipelineError("Caso repetido na validação interna da fusão.")
    return sorted(validation_ids), scores


def _restrict_splits_to_case_universe(
    splits: dict[str, Any], allowed_case_ids: set[str]
) -> dict[str, Any]:
    """Intersect a frozen nested-split structure with a smaller case universe
    (used when a signal, such as historical v23, only covers a subset of the
    full protocol population). Fold membership itself is never changed —
    cases keep whichever outer/inner fold they were already assigned to;
    they are only dropped where the intersection excludes them."""
    restricted_outer = []
    for outer in splits["outer_folds"]:
        train_ids = [cid for cid in outer["train_case_ids"] if cid in allowed_case_ids]
        test_ids = [cid for cid in outer["test_case_ids"] if cid in allowed_case_ids]
        inner_rows = []
        for inner in outer["inner_folds"]:
            inner_rows.append(
                {
                    "inner_fold": inner["inner_fold"],
                    "train_case_ids": [
                        cid for cid in inner["train_case_ids"] if cid in allowed_case_ids
                    ],
                    "validation_case_ids": [
                        cid for cid in inner["validation_case_ids"] if cid in allowed_case_ids
                    ],
                }
            )
        restricted_outer.append(
            {
                "outer_fold": outer["outer_fold"],
                "train_case_ids": train_ids,
                "test_case_ids": test_ids,
                "inner_folds": inner_rows,
            }
        )
    return {
        "schema": splits["schema"],
        "seed": splits["seed"],
        "outer_fold_count": splits["outer_fold_count"],
        "inner_fold_count": splits["inner_fold_count"],
        "case_count": sum(len(outer["test_case_ids"]) for outer in restricted_outer),
        "patient_group_count": splits.get("patient_group_count"),
        "outer_folds": restricted_outer,
    }


def generate_oof_predictions(
    *,
    fusion_config_path: Path,
    training_protocol_config_path: Path,
    training_protocol_path: Path,
    splits_path: Path,
    signal_roots: dict[str, Path],
    workspace_root: Path,
    output_root: Path,
) -> dict[str, Any]:
    output_root = Path(output_root).resolve()
    if output_root.exists():
        raise PipelineError("Predições de fusão já existem; saída é imutável.")
    output_root.mkdir(parents=True)
    config = load_fusion_config(fusion_config_path)
    protocol = verify_protocol(
        config_path=training_protocol_config_path,
        workspace_root=workspace_root,
        protocol_path=training_protocol_path,
        splits_path=splits_path,
    )
    splits = _json(splits_path, "Splits")
    validate_nested_splits(splits)
    protected_cases = load_protected_cases(training_protocol_config_path, workspace_root)

    signal_names = [str(item["name"]) for item in config["signals"]]
    signal_scores: dict[str, dict[str, dict[str, Any]]] = {}
    signal_source_signatures: dict[str, str] = {}
    for item in config["signals"]:
        name = str(item["name"])
        root = Path(signal_roots[name])
        prediction_schema = str(item["prediction_schema"])
        freeze_schema = str(item["freeze_schema"])
        signal_scores[name] = load_signal_scores(
            root, prediction_schema=prediction_schema, freeze_schema=freeze_schema
        )
        source_freeze_path = (
            root / "summary.json" if freeze_schema == V23_FREEZE_SCHEMA else root / "prediction_freeze.json"
        )
        signal_source_signatures[name] = sha256_file(source_freeze_path)

    common_case_ids, protected_by_id = align_signals(signal_scores, protected_cases)
    common_case_set = set(common_case_ids)
    restricted_splits = _restrict_splits_to_case_universe(splits, common_case_set)

    label_map = {
        case_id: int(protected_by_id[case_id].label == "POSITIVE") for case_id in common_case_ids
    }
    c_grid = [float(value) for value in config["regularization_c_grid"]]
    seed = int(config.get("seed", 20260724))
    max_iter = int(config.get("max_iter", 2000))

    predictions: list[dict[str, Any]] = []
    selections: list[dict[str, Any]] = []
    correlations = {
        f"{a}_vs_{b}": score_correlation(signal_scores, a, b)
        for index_a, a in enumerate(signal_names)
        for b in signal_names[index_a + 1 :]
    }

    for outer in restricted_splits["outer_folds"]:
        outer_index = int(outer["outer_fold"])
        outer_train_ids = [cid for cid in outer["train_case_ids"] if cid in label_map]
        outer_test_ids = [cid for cid in outer["test_case_ids"] if cid in label_map]
        if not outer_test_ids:
            continue
        candidates: list[dict[str, Any]] = []
        for c_value in c_grid:
            validation_ids, scores = _inner_oof_scores(
                inner_folds=list(outer["inner_folds"]),
                signal_scores=signal_scores,
                signal_names=signal_names,
                label_map=label_map,
                c_value=c_value,
                seed=seed + outer_index * 100,
                max_iter=max_iter,
            )
            if not validation_ids:
                continue
            threshold, metrics = _best_threshold(validation_ids, scores, label_map)
            candidates.append({"c_value": c_value, "threshold": threshold, "inner_metrics": metrics})
        if not candidates:
            raise PipelineError(f"Sem candidatos válidos de fusão no outer fold {outer_index}.")
        selected = max(
            candidates,
            key=lambda item: (
                min(item["inner_metrics"]["sensitivity"], item["inner_metrics"]["specificity"]),
                item["inner_metrics"]["balanced_accuracy"],
                -item["c_value"],
            ),
        )
        model = _fit_meta_model(
            outer_train_ids,
            signal_scores,
            signal_names,
            label_map,
            c_value=selected["c_value"],
            seed=seed + outer_index,
            max_iter=max_iter,
        )
        test_scores = _meta_scores(model, outer_test_ids, signal_scores, signal_names)
        selection = {
            "outer_fold": outer_index,
            **selected,
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
                    "patient_group_id": protected_by_id[case_id].patient_group_id,
                    "dataset_id": protected_by_id[case_id].dataset_id,
                    "outer_fold": outer_index,
                    "signals": signal_names,
                    "score": score,
                    "threshold": selected["threshold"],
                    "prediction": (
                        "TECHNICAL_FAILURE"
                        if score is None
                        else ("POSITIVE" if score >= selected["threshold"] else "NEGATIVE")
                    ),
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
        raise PipelineError("Predição de fusão duplicada.")
    if set(case_ids) != common_case_set:
        raise PipelineError("Predições de fusão não cobrem a coorte comum aos sinais.")

    predictions_path = output_root / "oof_predictions.jsonl"
    predictions_path.write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in predictions),
        encoding="utf-8",
    )
    selection_path = output_root / "fold_selection.json"
    selection_path.write_text(
        json.dumps(sorted(selections, key=lambda row: row["outer_fold"]), ensure_ascii=False, indent=2, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )
    correlation_path = output_root / "signal_correlations.json"
    correlation_path.write_text(
        json.dumps(correlations, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    body = {
        "schema": PREDICTION_FREEZE_SCHEMA,
        "status": "frozen_before_final_metric_calculation",
        "candidate_id": str(config["candidate_id"]),
        "signals": signal_names,
        "training_protocol_signature": protocol["protocol_signature"],
        "signal_source_signatures": signal_source_signatures,
        "fusion_config_sha256": sha256_file(fusion_config_path),
        "splits_sha256": sha256_file(splits_path),
        "case_count": len(predictions),
        "technical_failure_count": sum(bool(row["technical_failure"]) for row in predictions),
        "oof_predictions_sha256": sha256_file(predictions_path),
        "fold_selection_sha256": sha256_file(selection_path),
        "signal_correlations_sha256": sha256_file(correlation_path),
        "individual_ground_truth_persisted": False,
        "held_out_labels_used_for_fit_or_threshold": False,
        "lesion_masks_read": 0,
        "research_only": True,
        "clinical_use_allowed": False,
    }
    freeze = {**body, "prediction_signature": canonical_sha256(body)}
    (output_root / "prediction_freeze.json").write_text(
        json.dumps(freeze, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
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
    positives = [score for label, score in zip(labels, scores) if label == 1]
    negatives = [score for label, score in zip(labels, scores) if label == 0]
    if not positives or not negatives:
        return None
    wins = sum(
        1.0 if p > n else 0.5 if p == n else 0.0 for p in positives for n in negatives
    )
    return wins / (len(positives) * len(negatives))


def _metrics_for(rows: list[dict[str, Any]], protected_by_id: dict[str, ProtectedTrainingCase]) -> dict[str, Any]:
    tp = tn = fp = fn = failures = 0
    auc_labels: list[int] = []
    auc_scores: list[float] = []
    for row in rows:
        label = int(protected_by_id[str(row["case_id"])].label == "POSITIVE")
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
        raise PipelineError("Avaliação de fusão já existe; saída é imutável.")
    output_root.mkdir(parents=True)
    protocol = verify_protocol(
        config_path=training_protocol_config_path,
        workspace_root=workspace_root,
        protocol_path=training_protocol_path,
        splits_path=splits_path,
    )
    freeze = _json(Path(prediction_root) / "prediction_freeze.json", "Freeze de predições de fusão")
    unsigned = dict(freeze)
    signature = unsigned.pop("prediction_signature", None)
    if signature != canonical_sha256(unsigned):
        raise PipelineError("Assinatura das predições de fusão diverge.")
    predictions_path = Path(prediction_root) / "oof_predictions.jsonl"
    if freeze.get("oof_predictions_sha256") != sha256_file(predictions_path):
        raise PipelineError("Predições de fusão foram alteradas.")
    predictions = _jsonl(predictions_path, "Predições de fusão")
    if any("label" in row or "ground_truth" in row for row in predictions):
        raise PipelineError("Predições de fusão contêm ground truth.")

    protected_by_id = {
        case.case_id: case
        for case in load_protected_cases(training_protocol_config_path, workspace_root)
    }
    covered = {str(row["case_id"]) for row in predictions}
    if not covered <= set(protected_by_id):
        raise PipelineError("Predições de fusão citam caso fora do protocolo.")

    overall = _metrics_for(predictions, protected_by_id)
    by_dataset = {
        dataset_id: _metrics_for(
            [row for row in predictions if protected_by_id[str(row["case_id"])].dataset_id == dataset_id],
            protected_by_id,
        )
        for dataset_id in sorted({protected_by_id[cid].dataset_id for cid in covered})
    }
    body = {
        "schema": EVALUATION_SCHEMA,
        "candidate_id": freeze["candidate_id"],
        "signals": freeze["signals"],
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
            "retrospective_multicohort": len(by_dataset) > 1,
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
        json.dumps(evaluation, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return evaluation
