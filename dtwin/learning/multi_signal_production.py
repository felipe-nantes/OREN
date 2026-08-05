"""Production training and external inference for frozen multi-signal fusion."""
from __future__ import annotations

import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any

import joblib
import numpy as np

from dtwin.core import PipelineError
from dtwin.learning.external_bundle_evaluation import _jsonl, _metrics
from dtwin.learning.multi_signal_fusion import (
    _best_threshold,
    _fit_meta_model,
    _meta_scores,
    _restrict_splits_to_case_universe,
    align_signals,
    load_fusion_config,
    load_signal_scores,
)
from dtwin.learning.protocol import (
    canonical_sha256,
    load_protected_cases,
    sha256_file,
    verify_protocol,
)
from dtwin.learning.splits import validate_nested_splits
from dtwin.learning.visual_inference import load_production_bundle


BUNDLE_SCHEMA = "oren-multi-signal-fusion-production-bundle-v1"
PREDICTION_SCHEMA = "oren-multi-signal-fusion-external-prediction-v1"
FREEZE_SCHEMA = "oren-multi-signal-fusion-external-freeze-v1"
EVALUATION_SCHEMA = "oren-multi-signal-fusion-external-evaluation-v1"


def _json(path: Path, description: str) -> dict[str, Any]:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PipelineError(f"{description} ausente ou invalido: {path}") from exc
    if not isinstance(value, dict):
        raise PipelineError(f"{description} deve ser objeto JSON.")
    return value


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )


def _verify_signed(payload: dict[str, Any], signature_field: str) -> None:
    unsigned = dict(payload)
    signature = unsigned.pop(signature_field, None)
    if signature != canonical_sha256(unsigned):
        raise PipelineError("Assinatura de artefato diverge.")


def load_fusion_production_bundle(root: Path) -> tuple[dict[str, Any], Any]:
    root = Path(root).resolve()
    manifest = _json(root / "bundle_manifest.json", "Bundle de fusao")
    if manifest.get("schema") != BUNDLE_SCHEMA:
        raise PipelineError("Schema do bundle de fusao invalido.")
    _verify_signed(manifest, "bundle_signature")
    model_path = root / "production_model.joblib"
    if manifest.get("model_sha256") != sha256_file(model_path):
        raise PipelineError("Modelo de fusao foi alterado.")
    return manifest, joblib.load(model_path)


def train_fusion_production_bundle(
    *,
    fusion_config_path: Path,
    training_protocol_config_path: Path,
    training_protocol_path: Path,
    splits_path: Path,
    signal_roots: dict[str, Path],
    base_bundle_roots: dict[str, Path],
    workspace_root: Path,
    output_root: Path,
) -> dict[str, Any]:
    destination = Path(output_root).resolve()
    if destination.exists():
        raise PipelineError("Bundle de fusao ja existe; saida e imutavel.")
    config = load_fusion_config(fusion_config_path)
    protocol = verify_protocol(
        config_path=training_protocol_config_path,
        workspace_root=workspace_root,
        protocol_path=training_protocol_path,
        splits_path=splits_path,
    )
    splits = _json(splits_path, "Splits")
    validate_nested_splits(splits)
    signal_names = [str(item["name"]) for item in config["signals"]]
    if set(signal_roots) != set(signal_names) or set(base_bundle_roots) != set(signal_names):
        raise PipelineError("Raizes OOF/bundles nao correspondem aos sinais configurados.")
    signal_scores: dict[str, dict[str, dict[str, Any]]] = {}
    signal_contracts: dict[str, dict[str, str]] = {}
    for item in config["signals"]:
        name = str(item["name"])
        signal_scores[name] = load_signal_scores(
            signal_roots[name],
            prediction_schema=str(item["prediction_schema"]),
            freeze_schema=str(item["freeze_schema"]),
        )
        freeze_path = Path(signal_roots[name]) / "prediction_freeze.json"
        base_bundle = load_production_bundle(base_bundle_roots[name])
        signal_contracts[name] = {
            "oof_freeze_sha256": sha256_file(freeze_path),
            "base_bundle_signature": str(base_bundle.manifest["bundle_signature"]),
        }
    case_ids, protected = align_signals(
        signal_scores, load_protected_cases(training_protocol_config_path, workspace_root)
    )
    label_map = {case_id: int(protected[case_id].label == "POSITIVE") for case_id in case_ids}
    restricted = _restrict_splits_to_case_universe(splits, set(case_ids))
    policy = str(config.get("missing_signal_policy", "fail_case"))
    seed = int(config.get("seed", 20260804))
    max_iter = int(config.get("max_iter", 2000))
    candidates: list[dict[str, Any]] = []
    for c_value in [float(value) for value in config["regularization_c_grid"]]:
        cv_scores: dict[str, float | None] = {}
        for outer in restricted["outer_folds"]:
            train_ids = [cid for cid in outer["train_case_ids"] if cid in label_map]
            test_ids = [cid for cid in outer["test_case_ids"] if cid in label_map]
            if not test_ids:
                continue
            model = _fit_meta_model(
                train_ids, signal_scores, signal_names, label_map,
                c_value=c_value, seed=seed + int(outer["outer_fold"]),
                max_iter=max_iter, missing_signal_policy=policy,
            )
            cv_scores.update(_meta_scores(model, test_ids, signal_scores, signal_names, policy))
        if set(cv_scores) != set(case_ids):
            raise PipelineError("CV de producao nao cobriu todos os casos de desenvolvimento.")
        threshold, metrics = _best_threshold(case_ids, cv_scores, label_map)
        candidates.append({"c_value": c_value, "threshold": threshold, "metrics": metrics})
    selected = max(
        candidates,
        key=lambda item: (
            min(item["metrics"]["sensitivity"], item["metrics"]["specificity"]),
            item["metrics"]["balanced_accuracy"], -item["c_value"],
        ),
    )
    final_model = _fit_meta_model(
        case_ids, signal_scores, signal_names, label_map,
        c_value=float(selected["c_value"]), seed=seed, max_iter=max_iter,
        missing_signal_policy=policy,
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{destination.name}.", dir=destination.parent))
    try:
        model_path = staging / "production_model.joblib"
        joblib.dump(final_model, model_path)
        body = {
            "schema": BUNDLE_SCHEMA,
            "candidate_id": str(config["candidate_id"]),
            "signals": signal_names,
            "signal_contracts": signal_contracts,
            "missing_signal_policy": policy,
            "selected_c_value": float(selected["c_value"]),
            "decision_threshold": float(selected["threshold"]),
            "development_cv_selection_metrics": selected["metrics"],
            "development_cv_selection_is_not_generalization_estimate": True,
            "external_validation_required": True,
            "training_case_count": len(case_ids),
            "training_case_ids": case_ids,
            "training_protocol_signature": protocol["protocol_signature"],
            "fusion_config_sha256": sha256_file(fusion_config_path),
            "splits_sha256": sha256_file(splits_path),
            "model_sha256": sha256_file(model_path),
            "individual_ground_truth_persisted": False,
            "lesion_masks_read": 0,
            "research_only": True,
            "clinical_use_allowed": False,
        }
        manifest = {**body, "bundle_signature": canonical_sha256(body)}
        (staging / "bundle_manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        os.replace(staging, destination)
        return manifest
    finally:
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)


def _load_external_signal(root: Path) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    freeze = _json(Path(root) / "prediction_freeze.json", "Freeze externo")
    _verify_signed(freeze, "prediction_signature")
    rows_path = Path(root) / "predictions.jsonl"
    if freeze.get("predictions_sha256") != sha256_file(rows_path):
        raise PipelineError("Predicoes externas de base foram alteradas.")
    rows = _jsonl(rows_path, "Predicoes externas de base")
    if any("label" in row or "ground_truth" in row for row in rows):
        raise PipelineError("Sinal externo contem ground truth.")
    return freeze, {
        str(row["case_id"]): {
            "score": row.get("score"), "threshold": row.get("threshold"),
            "technical_failure": bool(row.get("technical_failure")),
        }
        for row in rows
    }


def predict_external_fusion(
    *, bundle_root: Path, signal_prediction_roots: dict[str, Path], output_root: Path
) -> dict[str, Any]:
    output = Path(output_root).resolve()
    if output.exists():
        raise PipelineError("Predicoes externas de fusao ja existem; saida e imutavel.")
    manifest, model = load_fusion_production_bundle(bundle_root)
    names = list(manifest["signals"])
    if set(signal_prediction_roots) != set(names):
        raise PipelineError("Predicoes externas nao correspondem aos sinais do bundle.")
    scores: dict[str, dict[str, dict[str, Any]]] = {}
    source_signatures: dict[str, str] = {}
    case_universe: set[str] | None = None
    for name in names:
        freeze, scores[name] = _load_external_signal(signal_prediction_roots[name])
        if freeze.get("bundle_signature") != manifest["signal_contracts"][name]["base_bundle_signature"]:
            raise PipelineError(f"Sinal externo {name} foi gerado por outro bundle.")
        source_signatures[name] = str(freeze["prediction_signature"])
        current = set(scores[name])
        case_universe = current if case_universe is None else case_universe & current
    if not case_universe or any(set(scores[name]) != case_universe for name in names):
        raise PipelineError("Sinais externos nao possuem a mesma cobertura de casos.")
    overlap = set(manifest["training_case_ids"]) & case_universe
    if overlap:
        raise PipelineError("Fusao externa contem caso visto no treino.")
    policy = str(manifest["missing_signal_policy"])
    fused = _meta_scores(model, sorted(case_universe), scores, names, policy)
    threshold = float(manifest["decision_threshold"])
    rows = [{
        "schema": PREDICTION_SCHEMA,
        "case_id": case_id,
        "prediction": (
            "TECHNICAL_FAILURE" if fused[case_id] is None
            else ("POSITIVE" if float(fused[case_id]) >= threshold else "NEGATIVE")
        ),
        "technical_failure": fused[case_id] is None,
        "score": fused[case_id], "threshold": threshold, "signals": names,
        "ground_truth_in_artifact": False, "lesion_mask_read": False,
        "research_only": True,
    } for case_id in sorted(case_universe)]
    output.mkdir(parents=True)
    rows_path = output / "predictions.jsonl"
    _write_jsonl(rows_path, rows)
    body = {
        "schema": FREEZE_SCHEMA,
        "status": "frozen_before_external_metric_calculation",
        "bundle_signature": manifest["bundle_signature"],
        "source_prediction_signatures": source_signatures,
        "case_count": len(rows),
        "technical_failure_count": sum(bool(row["technical_failure"]) for row in rows),
        "predictions_sha256": sha256_file(rows_path),
        "training_case_overlap": 0,
        "ground_truth_read": False, "lesion_masks_read": 0,
        "research_only": True, "clinical_use_allowed": False,
    }
    freeze = {**body, "prediction_signature": canonical_sha256(body)}
    (output / "prediction_freeze.json").write_text(
        json.dumps(freeze, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return freeze


def evaluate_external_fusion(
    *, prediction_root: Path, training_protocol_config_path: Path,
    workspace_root: Path, protected_dataset_ids: set[str], output_root: Path
) -> dict[str, Any]:
    output = Path(output_root).resolve()
    if output.exists():
        raise PipelineError("Avaliacao externa de fusao ja existe; saida e imutavel.")
    freeze = _json(Path(prediction_root) / "prediction_freeze.json", "Freeze de fusao")
    if freeze.get("schema") != FREEZE_SCHEMA:
        raise PipelineError("Schema do freeze externo de fusao invalido.")
    _verify_signed(freeze, "prediction_signature")
    rows_path = Path(prediction_root) / "predictions.jsonl"
    if freeze.get("predictions_sha256") != sha256_file(rows_path):
        raise PipelineError("Predicoes externas de fusao foram alteradas.")
    rows = _jsonl(rows_path, "Predicoes externas de fusao")
    protected = {
        case.case_id: case for case in load_protected_cases(
            training_protocol_config_path, workspace_root
        ) if case.dataset_id in protected_dataset_ids
    }
    if {str(row["case_id"]) for row in rows} != set(protected):
        raise PipelineError("Cobertura da fusao diverge dos labels externos autorizados.")
    labels = {case_id: case.label for case_id, case in protected.items()}
    body = {
        "schema": EVALUATION_SCHEMA,
        "prediction_signature": freeze["prediction_signature"],
        "ground_truth_opened_after_predictions_frozen": True,
        "technical_failures_count_as_errors": True,
        "overall": _metrics(rows, labels),
        "lesion_masks_read": 0, "research_only": True, "clinical_use_allowed": False,
    }
    report = {**body, "evaluation_signature": canonical_sha256(body)}
    output.mkdir(parents=True)
    (output / "evaluation.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return report


__all__ = [
    "evaluate_external_fusion", "load_fusion_production_bundle",
    "predict_external_fusion", "train_fusion_production_bundle",
]
