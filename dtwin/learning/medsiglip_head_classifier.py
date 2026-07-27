"""Phase-13 stage-1 nonlinear head over unchanged frozen MedSigLIP embeddings."""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import yaml
from sklearn.neural_network import MLPClassifier
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.utils.class_weight import compute_sample_weight

from dtwin.core import PipelineError
from dtwin.learning.medsiglip_classifier import _best_threshold
from dtwin.learning.medsiglip_embeddings import verify_embeddings
from dtwin.learning.protocol import (
    canonical_sha256,
    load_protected_cases,
    sha256_file,
    verify_protocol,
)
from dtwin.learning.splits import validate_nested_splits


def _json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PipelineError(f"JSON da cabeça MedSigLIP inválido: {path}") from exc
    if not isinstance(value, dict):
        raise PipelineError("Objeto JSON esperado.")
    return value


def _jsonl(path: Path) -> list[dict[str, Any]]:
    try:
        return [
            json.loads(line)
            for line in Path(path).read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    except (OSError, json.JSONDecodeError) as exc:
        raise PipelineError(f"JSONL da cabeça MedSigLIP inválido: {path}") from exc


def _config(path: Path) -> dict[str, Any]:
    try:
        value = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise PipelineError("Config da cabeça MedSigLIP inválida.") from exc
    if not isinstance(value, dict) or value.get("schema") != "argos-hybrid-medsiglip-head-config-v1":
        raise PipelineError("Schema da cabeça MedSigLIP inválido.")
    if value.get("encoder_trainable") is not False:
        raise PipelineError("Estágio 1 deve manter o encoder congelado.")
    return value


def _case_vectors(embedding_root: Path) -> dict[str, np.ndarray]:
    grouped: dict[str, list[np.ndarray]] = {}
    for row in _jsonl(Path(embedding_root) / "embedding_records.jsonl"):
        vector = np.load(Path(embedding_root) / row["embedding_path"], allow_pickle=False).astype(np.float64)
        grouped.setdefault(str(row["case_id"]), []).append(vector)
    result: dict[str, np.ndarray] = {}
    for case_id, vectors in grouped.items():
        pooled = np.mean(np.stack(vectors), axis=0)
        norm = float(np.linalg.norm(pooled))
        if not np.isfinite(pooled).all() or norm <= 0:
            raise PipelineError(f"Pooling MedSigLIP inválido: {case_id}.")
        result[case_id] = pooled / norm
    return result


def _fit(
    case_ids: list[str],
    vectors: dict[str, np.ndarray],
    labels: dict[str, int],
    *,
    hidden_units: int,
    alpha: float,
    seed: int,
    max_iter: int,
) -> Pipeline:
    available = [case_id for case_id in case_ids if case_id in vectors]
    matrix = np.stack([vectors[case_id] for case_id in available])
    targets = np.asarray([labels[case_id] for case_id in available], dtype=np.int64)
    if set(targets.tolist()) != {0, 1}:
        raise PipelineError("Cabeça MedSigLIP requer duas classes.")
    model = Pipeline(
        [
            ("scaler", StandardScaler()),
            (
                "classifier",
                MLPClassifier(
                    hidden_layer_sizes=(int(hidden_units),),
                    activation="relu",
                    alpha=float(alpha),
                    batch_size=32,
                    early_stopping=True,
                    validation_fraction=0.15,
                    n_iter_no_change=20,
                    max_iter=int(max_iter),
                    random_state=int(seed),
                    learning_rate_init=1e-3,
                ),
            ),
        ]
    )
    model.fit(matrix, targets, classifier__sample_weight=compute_sample_weight("balanced", targets))
    return model


def _scores(
    model: Pipeline, case_ids: list[str], vectors: dict[str, np.ndarray]
) -> dict[str, float]:
    available = [case_id for case_id in case_ids if case_id in vectors]
    if not available:
        return {}
    probabilities = model.predict_proba(np.stack([vectors[item] for item in available]))[:, 1]
    return {case_id: float(score) for case_id, score in zip(available, probabilities)}


def generate_oof(
    *,
    head_config_path: Path,
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
        raise PipelineError("Predições da cabeça MedSigLIP já existem.")
    output_root.mkdir(parents=True)
    config = _config(head_config_path)
    protocol = verify_protocol(
        config_path=training_protocol_config_path,
        workspace_root=workspace_root,
        protocol_path=training_protocol_path,
        splits_path=splits_path,
    )
    embeddings = verify_embeddings(candidate_root=candidate_root, output_root=embedding_root)
    splits = _json(splits_path)
    validate_nested_splits(splits)
    protected = load_protected_cases(training_protocol_config_path, workspace_root)
    protected_by_id = {case.case_id: case for case in protected}
    labels = {case.case_id: int(case.label == "POSITIVE") for case in protected}
    vectors = _case_vectors(embedding_root)
    predictions: list[dict[str, Any]] = []
    selections: list[dict[str, Any]] = []
    seed = int(config["seed"])
    for outer in splits["outer_folds"]:
        options: list[dict[str, Any]] = []
        for hidden_units in config["hidden_units_grid"]:
            for alpha in config["alpha_grid"]:
                inner_scores: dict[str, float] = {}
                validation_ids: list[str] = []
                for inner in outer["inner_folds"]:
                    model = _fit(
                        inner["train_case_ids"], vectors, labels,
                        hidden_units=int(hidden_units), alpha=float(alpha),
                        seed=seed + int(outer["outer_fold"]) * 100 + int(inner["inner_fold"]),
                        max_iter=int(config["max_iter"]),
                    )
                    ids = list(inner["validation_case_ids"])
                    inner_scores.update(_scores(model, ids, vectors))
                    validation_ids.extend(ids)
                threshold, metrics = _best_threshold(validation_ids, inner_scores, labels)
                options.append(
                    {
                        "hidden_units": int(hidden_units),
                        "alpha": float(alpha),
                        "threshold": threshold,
                        "inner_metrics": metrics,
                    }
                )
        selected = max(
            options,
            key=lambda item: (
                min(item["inner_metrics"]["sensitivity"], item["inner_metrics"]["specificity"]),
                item["inner_metrics"]["balanced_accuracy"],
                -item["hidden_units"],
                -item["alpha"],
            ),
        )
        model = _fit(
            outer["train_case_ids"], vectors, labels,
            hidden_units=selected["hidden_units"], alpha=selected["alpha"],
            seed=seed + int(outer["outer_fold"]), max_iter=int(config["max_iter"]),
        )
        test_ids = list(outer["test_case_ids"])
        test_scores = _scores(model, test_ids, vectors)
        model_path = output_root / f"outer_fold_{outer['outer_fold']}.joblib"
        descriptor, temporary_name = tempfile.mkstemp(dir=output_root, suffix=".tmp")
        os.close(descriptor)
        temporary = Path(temporary_name)
        try:
            joblib.dump(model, temporary)
            os.replace(temporary, model_path)
        finally:
            temporary.unlink(missing_ok=True)
        selections.append(
            {
                "outer_fold": int(outer["outer_fold"]),
                **selected,
                "model_sha256": sha256_file(model_path),
                "held_out_labels_used_for_fit_or_threshold": False,
            }
        )
        for case_id in test_ids:
            score = test_scores.get(case_id)
            predictions.append(
                {
                    "schema": "argos-hybrid-medsiglip-head-oof-prediction-v1",
                    "case_id": case_id,
                    "patient_group_id": case_id,
                    "dataset_id": protected_by_id[case_id].dataset_id,
                    "outer_fold": int(outer["outer_fold"]),
                    "panel_count": 0 if score is None else 1,
                    "score": score,
                    "threshold": selected["threshold"],
                    "prediction": "TECHNICAL_FAILURE" if score is None else (
                        "POSITIVE" if score >= selected["threshold"] else "NEGATIVE"
                    ),
                    "technical_failure": score is None,
                    "ground_truth_in_artifact": False,
                    "held_out_label_used": False,
                    "research_only": True,
                }
            )
    predictions.sort(key=lambda row: row["case_id"])
    predictions_path = output_root / "oof_predictions.jsonl"
    predictions_path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in predictions), encoding="utf-8"
    )
    selection_path = output_root / "fold_selection.json"
    selection_path.write_text(json.dumps(selections, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    body = {
        "schema": "argos-hybrid-medsiglip-head-oof-freeze-v1",
        "status": "frozen_before_final_metric_calculation",
        "candidate_id": config["candidate_id"],
        "training_protocol_signature": protocol["protocol_signature"],
        "embedding_signature": embeddings["embedding_signature"],
        "head_config_sha256": sha256_file(head_config_path),
        "splits_sha256": sha256_file(splits_path),
        "prediction_count": len(predictions),
        "technical_failure_count": sum(row["technical_failure"] for row in predictions),
        "oof_predictions_sha256": sha256_file(predictions_path),
        "fold_selection_sha256": sha256_file(selection_path),
        "individual_ground_truth_persisted": False,
        "held_out_labels_used_for_fit_or_threshold": False,
        "encoder_trainable": False,
        "lesion_masks_read": 0,
        "research_only": True,
        "clinical_use_allowed": False,
    }
    freeze = {**body, "prediction_signature": canonical_sha256(body)}
    (output_root / "prediction_freeze.json").write_text(
        json.dumps(freeze, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return freeze
