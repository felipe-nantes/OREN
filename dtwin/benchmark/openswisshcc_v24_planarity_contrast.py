"""Nested development evaluation of a predeclared v23 morphology extension.

The v24 hypothesis adds one fixed feature to the frozen v23 anchor:
weighted planarity minus weighted linearity. Feature weight selection and the
decision threshold are fitted only inside training folds.
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
import random
import shutil
import statistics
import time
import uuid
from pathlib import Path
from typing import Any

from dtwin.benchmark.openswisshcc_alignment import _publish_directory
from dtwin.benchmark.openswisshcc_candidate_shape import CASE_SCHEMA
from dtwin.benchmark.openswisshcc_v20_fusion import (
    BLIND_SIGNAL_SCHEMA,
    _canonical_sha,
    _ecdf,
)
from dtwin.benchmark.openswisshcc_v23_baseline import verify_v23_baseline_lock
from dtwin.benchmark.openswisshcc_v23_shape_fusion import (
    _fusion_scores as _v23_anchor_scores,
)
from dtwin.benchmark.openswisshcc_volumetric_evaluation import (
    _best_threshold,
    _binary_metrics,
)
from dtwin.core import PipelineError

PROTOCOL_SCHEMA = "argos-openswisshcc-v24-planarity-contrast-protocol-v1"
EVALUATION_SCHEMA = "argos-openswisshcc-v24-planarity-contrast-evaluation-v1"
FEATURE_NAME = "candidate_weighted_planarity_minus_linearity"
FEATURE_DEFINITION = (
    "candidate_weighted_planarity - candidate_weighted_linearity"
)
FEATURE_DIRECTION = "higher_is_more_positive"
WEIGHT_GRID = (0.0, 0.05, 0.10, 0.15, 0.20)
REPEATS = 50
FOLDS = 5
RANDOM_SEED = 20260723


def _load_json(path: Path, description: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PipelineError(f"{description} ausente ou inválido.") from exc
    if not isinstance(value, dict):
        raise PipelineError(f"{description} deve ser objeto JSON.")
    return value


def _load_jsonl(path: Path, description: str) -> list[dict[str, Any]]:
    try:
        rows = [
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    except (OSError, json.JSONDecodeError) as exc:
        raise PipelineError(f"{description} ausente ou inválido.") from exc
    if not rows or not all(isinstance(row, dict) for row in rows):
        raise PipelineError(f"{description} deve conter objetos JSONL.")
    return rows


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
    except OSError as exc:
        raise PipelineError(f"Artefato v24 ausente: {path}.") from exc
    return digest.hexdigest()


def _write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _finite(value: Any, description: str) -> float:
    if isinstance(value, bool):
        raise PipelineError(f"{description} não é numérico finito.")
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise PipelineError(f"{description} não é numérico finito.") from exc
    if not math.isfinite(result):
        raise PipelineError(f"{description} não é numérico finito.")
    return result


def planarity_contrast(features: dict[str, Any]) -> float:
    """Return the single predeclared v24 feature without labels."""

    planarity = _finite(
        features.get("candidate_weighted_planarity"),
        "Planaridade ponderada",
    )
    linearity = _finite(
        features.get("candidate_weighted_linearity"),
        "Linearidade ponderada",
    )
    if not 0.0 <= planarity <= 1.0 or not 0.0 <= linearity <= 1.0:
        raise PipelineError("Planaridade/linearidade fora de [0, 1].")
    return float(planarity - linearity)


def _candidate_scores(
    rows: list[dict[str, Any]],
    linearity: list[float],
    contrast: list[float],
    train: list[int],
    score_indices: list[int],
    weight: float,
) -> list[float]:
    if weight not in WEIGHT_GRID:
        raise PipelineError("Peso v24 fora da grade predefinida.")
    anchor = _v23_anchor_scores(rows, linearity, train, score_indices)
    reference = [contrast[index] for index in train]
    return [
        (1.0 - weight) * anchor_score
        + weight * _ecdf(contrast[index], reference)
        for anchor_score, index in zip(anchor, score_indices, strict=True)
    ]


def _selection_key(metrics: dict[str, Any], weight: float) -> tuple[float, float, float, float]:
    return (
        float(metrics["minimum_gate_metric"]),
        float(metrics["balanced_accuracy"]),
        float(metrics["sensitivity"]),
        -float(weight),
    )


def _select_weight_nested(
    *,
    rows: list[dict[str, Any]],
    linearity: list[float],
    contrast: list[float],
    truth: list[bool],
    train_indices: list[int],
) -> dict[str, Any]:
    """Select weight by inner LOOCV using training indices only."""

    if len(train_indices) < 10:
        raise PipelineError("Treino interno v24 insuficiente.")
    candidates: list[dict[str, Any]] = []
    for weight in WEIGHT_GRID:
        predicted: list[bool] = []
        inner_truth: list[bool] = []
        for validation_index in train_indices:
            inner_train = [
                index for index in train_indices if index != validation_index
            ]
            threshold, _ = _best_threshold(
                _candidate_scores(
                    rows,
                    linearity,
                    contrast,
                    inner_train,
                    inner_train,
                    weight,
                ),
                [truth[index] for index in inner_train],
            )
            score = _candidate_scores(
                rows,
                linearity,
                contrast,
                inner_train,
                [validation_index],
                weight,
            )[0]
            predicted.append(score >= threshold)
            inner_truth.append(truth[validation_index])
        metrics = _binary_metrics(inner_truth, predicted)
        candidates.append({"weight": weight, "metrics": metrics})
    selected = max(
        candidates,
        key=lambda item: _selection_key(item["metrics"], item["weight"]),
    )
    return {
        "selected_weight": float(selected["weight"]),
        "selected_inner_metrics": selected["metrics"],
        "candidate_metrics": candidates,
    }


def _nested_loocv(
    rows: list[dict[str, Any]],
    linearity: list[float],
    contrast: list[float],
    truth: list[bool],
) -> dict[str, Any]:
    predictions: list[bool] = []
    scores: list[float] = []
    thresholds: list[float] = []
    selected_weights: list[float] = []
    inner_minimum_metrics: list[float] = []
    for held_out in range(len(rows)):
        train = [index for index in range(len(rows)) if index != held_out]
        selection = _select_weight_nested(
            rows=rows,
            linearity=linearity,
            contrast=contrast,
            truth=truth,
            train_indices=train,
        )
        weight = selection["selected_weight"]
        threshold, _ = _best_threshold(
            _candidate_scores(rows, linearity, contrast, train, train, weight),
            [truth[index] for index in train],
        )
        score = _candidate_scores(
            rows, linearity, contrast, train, [held_out], weight
        )[0]
        predictions.append(score >= threshold)
        scores.append(float(score))
        thresholds.append(float(threshold))
        selected_weights.append(float(weight))
        inner_minimum_metrics.append(
            float(selection["selected_inner_metrics"]["minimum_gate_metric"])
        )
    return {
        **_binary_metrics(truth, predictions),
        "scores": scores,
        "thresholds": thresholds,
        "predictions": predictions,
        "selected_weights": selected_weights,
        "inner_minimum_gate_metrics": inner_minimum_metrics,
    }


def _nested_repeated_stratified(
    rows: list[dict[str, Any]],
    linearity: list[float],
    contrast: list[float],
    truth: list[bool],
) -> dict[str, Any]:
    positive = [index for index, value in enumerate(truth) if value]
    negative = [index for index, value in enumerate(truth) if not value]
    if min(len(positive), len(negative)) < FOLDS:
        raise PipelineError("Coorte v24 insuficiente para validação estratificada.")
    outcomes: list[dict[str, Any]] = []
    selected_weight_counts = {str(weight): 0 for weight in WEIGHT_GRID}
    for repeat in range(REPEATS):
        rng = random.Random(RANDOM_SEED + repeat)
        pos, neg = positive[:], negative[:]
        rng.shuffle(pos)
        rng.shuffle(neg)
        groups: list[list[int]] = [[] for _ in range(FOLDS)]
        for index, item in enumerate(pos):
            groups[index % FOLDS].append(item)
        for index, item in enumerate(neg):
            groups[index % FOLDS].append(item)
        predicted = [False] * len(rows)
        for test_indices in groups:
            test = set(test_indices)
            train = [index for index in range(len(rows)) if index not in test]
            selection = _select_weight_nested(
                rows=rows,
                linearity=linearity,
                contrast=contrast,
                truth=truth,
                train_indices=train,
            )
            weight = selection["selected_weight"]
            selected_weight_counts[str(weight)] += 1
            threshold, _ = _best_threshold(
                _candidate_scores(rows, linearity, contrast, train, train, weight),
                [truth[index] for index in train],
            )
            test_scores = _candidate_scores(
                rows, linearity, contrast, train, test_indices, weight
            )
            for index, score in zip(test_indices, test_scores, strict=True):
                predicted[index] = score >= threshold
        outcomes.append(_binary_metrics(truth, predicted))
    return {
        "repeats": REPEATS,
        "folds": FOLDS,
        "seed": RANDOM_SEED,
        "feature_and_weight_selection_nested_inside_training_only": True,
        "runs_passing_75_75": sum(
            bool(item["passed_75_75"]) for item in outcomes
        ),
        "median_sensitivity": float(
            statistics.median(item["sensitivity"] for item in outcomes)
        ),
        "median_specificity": float(
            statistics.median(item["specificity"] for item in outcomes)
        ),
        "minimum_sensitivity": float(
            min(item["sensitivity"] for item in outcomes)
        ),
        "minimum_specificity": float(
            min(item["specificity"] for item in outcomes)
        ),
        "selected_weight_counts_across_outer_folds": selected_weight_counts,
    }


def _workspace_path(workspace: Path, relative: str) -> Path:
    raw = Path(relative)
    if raw.is_absolute() or ".." in raw.parts:
        raise PipelineError("Protocolo v24 contém caminho inseguro.")
    root = workspace.resolve()
    value = (root / raw).resolve()
    try:
        value.relative_to(root)
    except ValueError as exc:
        raise PipelineError("Protocolo v24 aponta para fora do workspace.") from exc
    return value


def _code_path(workspace: Path) -> Path:
    relative = Path("dtwin/benchmark/openswisshcc_v24_planarity_contrast.py")
    path = _workspace_path(workspace, str(relative))
    if not path.is_file():
        raise PipelineError("Código v24 não está no workspace esperado.")
    return path


def freeze_v24_planarity_protocol(
    *,
    baseline_lock_path: Path,
    audit_summary_path: Path,
    workspace_root: Path,
    output_path: Path,
) -> dict[str, Any]:
    """Freeze hypothesis, code and sources before calculating v24 metrics."""

    baseline = verify_v23_baseline_lock(
        lock_path=baseline_lock_path,
        workspace_root=workspace_root,
    )
    audit = _load_json(Path(audit_summary_path).resolve(), "Auditoria v23")
    if (
        audit.get("schema")
        != "argos-openswisshcc-v23-development-error-audit-v1"
        or audit.get("status") != "complete_retrospective_development_error_audit"
        or audit.get("error_case_count") != 17
        or audit.get("baseline_modified") is not False
        or audit.get("lesion_masks_read") is not False
        or audit.get("holdout_v21_opened_or_reused") is not False
    ):
        raise PipelineError("Auditoria v23 não é válida para congelar a hipótese v24.")
    base = {
        "schema": PROTOCOL_SCHEMA,
        "status": "frozen_after_v23_error_audit_before_v24_metrics",
        "case_count": baseline["case_count"],
        "anchor": "frozen_v23_80_percent_v11_20_percent_weighted_linearity",
        "feature_name": FEATURE_NAME,
        "feature_definition": FEATURE_DEFINITION,
        "feature_direction": FEATURE_DIRECTION,
        "weight_grid": list(WEIGHT_GRID),
        "weight_selection": (
            "inner_loocv_maximize_minimum_metric_then_balanced_accuracy_"
            "then_sensitivity_then_smallest_weight"
        ),
        "outer_validation": {
            "primary": "nested_loocv",
            "robustness": "nested_repeated_stratified_5fold",
            "repeats": REPEATS,
            "folds": FOLDS,
            "seed": RANDOM_SEED,
        },
        "success_gate": {
            "minimum_sensitivity": 0.75,
            "minimum_specificity": 0.75,
            "required_repeated_runs_passing": REPEATS,
            "inconclusive_counts_as_error": True,
            "technical_failure_counts_as_error": True,
        },
        "source_hashes": {
            "baseline_lock": _sha256(Path(baseline_lock_path).resolve()),
            "v23_error_audit_summary": _sha256(Path(audit_summary_path).resolve()),
            "implementation": _sha256(_code_path(Path(workspace_root))),
        },
        "hypothesis_predeclared_after_development_labels": True,
        "selection_bias_possible": True,
        "development_only": True,
        "independent_balanced_validation_required": True,
        "holdout_v21_reuse_forbidden": True,
        "lesion_masks_forbidden": True,
        "qualified": False,
        "research_only": True,
        "clinical_use_allowed": False,
        "requires_human_review": True,
    }
    protocol = {**base, "protocol_signature": _canonical_sha(base)}
    destination = Path(output_path).resolve()
    if destination.exists():
        existing = _load_json(destination, "Protocolo v24 existente")
        if existing != protocol:
            raise PipelineError("Protocolo v24 existente diverge; sobrescrita recusada.")
        return existing
    destination.parent.mkdir(parents=True, exist_ok=True)
    _write_json(destination, protocol)
    return protocol


def _verify_protocol(
    *,
    protocol_path: Path,
    baseline_lock_path: Path,
    audit_summary_path: Path,
    workspace_root: Path,
) -> dict[str, Any]:
    protocol = _load_json(Path(protocol_path).resolve(), "Protocolo v24")
    signature = protocol.get("protocol_signature")
    unsigned = dict(protocol)
    unsigned.pop("protocol_signature", None)
    expected_hashes = {
        "baseline_lock": _sha256(Path(baseline_lock_path).resolve()),
        "v23_error_audit_summary": _sha256(Path(audit_summary_path).resolve()),
        "implementation": _sha256(_code_path(Path(workspace_root))),
    }
    if (
        protocol.get("schema") != PROTOCOL_SCHEMA
        or protocol.get("status")
        != "frozen_after_v23_error_audit_before_v24_metrics"
        or signature != _canonical_sha(unsigned)
        or protocol.get("feature_name") != FEATURE_NAME
        or protocol.get("feature_definition") != FEATURE_DEFINITION
        or protocol.get("feature_direction") != FEATURE_DIRECTION
        or protocol.get("weight_grid") != list(WEIGHT_GRID)
        or protocol.get("source_hashes") != expected_hashes
        or protocol.get("development_only") is not True
        or protocol.get("holdout_v21_reuse_forbidden") is not True
        or protocol.get("lesion_masks_forbidden") is not True
        or protocol.get("qualified") is not False
    ):
        raise PipelineError("Protocolo v24 ausente, adulterado ou divergente.")
    return protocol


def _load_development_matrix(
    *,
    baseline_lock_path: Path,
    workspace_root: Path,
) -> tuple[list[str], list[dict[str, Any]], list[float], list[float], list[bool], dict[str, str]]:
    baseline = verify_v23_baseline_lock(
        lock_path=baseline_lock_path,
        workspace_root=workspace_root,
    )
    lock = _load_json(Path(baseline_lock_path).resolve(), "Lock v23")
    roles = lock.get("artifact_roles", {})
    required = {"case_scores", "v20_signals", "shape_features", "development_labels"}
    if not isinstance(roles, dict) or not required.issubset(roles):
        raise PipelineError("Lock v23 incompleto para avaliação v24.")
    workspace = Path(workspace_root).resolve()
    paths = {name: _workspace_path(workspace, roles[name]) for name in required}
    label_path = paths["development_labels"]
    if label_path.name != "development_labels.jsonl" or any(
        "holdout" in part.lower() for part in label_path.parts
    ):
        raise PipelineError("Avaliação v24 aceita somente labels de desenvolvimento.")
    try:
        with paths["case_scores"].open("r", encoding="utf-8", newline="") as stream:
            score_rows = list(csv.DictReader(stream))
    except OSError as exc:
        raise PipelineError("Scores v23 ausentes para v24.") from exc
    signal_rows = _load_jsonl(paths["v20_signals"], "Sinais v20")
    shape_rows = _load_jsonl(paths["shape_features"], "Features v23")
    label_rows = _load_jsonl(paths["development_labels"], "Labels de desenvolvimento")
    case_ids = [str(row.get("case_id")) for row in score_rows]
    signal_by_id = {str(row.get("case_id")): row for row in signal_rows}
    shape_by_id = {str(row.get("case_id")): row for row in shape_rows}
    label_by_id = {str(row.get("case_id")): row for row in label_rows}
    if (
        len(case_ids) != baseline["case_count"]
        or len(set(case_ids)) != len(case_ids)
        or set(case_ids) != set(signal_by_id)
        or set(case_ids) != set(shape_by_id)
        or not set(case_ids).issubset(label_by_id)
    ):
        raise PipelineError("Coortes v20/v23/v24 não correspondem.")
    ordered_signals: list[dict[str, Any]] = []
    linearity: list[float] = []
    contrast: list[float] = []
    truth: list[bool] = []
    for case_id in case_ids:
        signal = signal_by_id[case_id]
        shape = shape_by_id[case_id]
        label = label_by_id[case_id].get("label")
        if (
            signal.get("schema") != BLIND_SIGNAL_SCHEMA
            or signal.get("ground_truth_read") is not False
            or signal.get("holdout_opened") is not False
            or shape.get("schema") != CASE_SCHEMA
            or shape.get("ground_truth_read") is not False
            or shape.get("ground_truth_lesion_mask_used") is not False
            or shape.get("inference_executed") is not False
            or label not in {"POSITIVE", "NEGATIVE"}
        ):
            raise PipelineError(f"Entrada insegura ou inválida para v24: {case_id}.")
        features = shape.get("features")
        if not isinstance(features, dict):
            raise PipelineError(f"Features v24 ausentes: {case_id}.")
        ordered_signals.append(signal)
        linearity.append(
            _finite(features.get("candidate_weighted_linearity"), "Linearidade v24")
        )
        contrast.append(planarity_contrast(features))
        truth.append(label == "POSITIVE")
    return (
        case_ids,
        ordered_signals,
        linearity,
        contrast,
        truth,
        {name: _sha256(path) for name, path in paths.items()},
    )


def evaluate_v24_planarity_contrast(
    *,
    protocol_path: Path,
    baseline_lock_path: Path,
    audit_summary_path: Path,
    workspace_root: Path,
    output_dir: Path,
    allow_protected_development_labels: bool = False,
) -> dict[str, Any]:
    """Run nested development evaluation after the protocol is frozen."""

    if allow_protected_development_labels is not True:
        raise PipelineError("Abertura dos labels de desenvolvimento v24 não autorizada.")
    protocol = _verify_protocol(
        protocol_path=protocol_path,
        baseline_lock_path=baseline_lock_path,
        audit_summary_path=audit_summary_path,
        workspace_root=workspace_root,
    )
    (
        case_ids,
        rows,
        linearity,
        contrast,
        truth,
        source_hashes,
    ) = _load_development_matrix(
        baseline_lock_path=baseline_lock_path,
        workspace_root=workspace_root,
    )
    started = time.perf_counter()
    primary = _nested_loocv(rows, linearity, contrast, truth)
    repeated = _nested_repeated_stratified(
        rows, linearity, contrast, truth
    )
    elapsed = time.perf_counter() - started
    point_gate = bool(
        primary["sensitivity"] >= 0.75 and primary["specificity"] >= 0.75
    )
    robustness_gate = repeated["runs_passing_75_75"] == REPEATS
    result = {
        "schema": EVALUATION_SCHEMA,
        "status": "complete_retrospective_nested_development_evaluation",
        "protocol_signature": protocol["protocol_signature"],
        "case_count": len(case_ids),
        "positive_count": sum(truth),
        "negative_count": len(truth) - sum(truth),
        "feature_name": FEATURE_NAME,
        "feature_definition": FEATURE_DEFINITION,
        "feature_direction": FEATURE_DIRECTION,
        "weight_grid": list(WEIGHT_GRID),
        "primary_nested_loocv_metrics": {
            key: value
            for key, value in primary.items()
            if key not in {
                "scores",
                "thresholds",
                "predictions",
                "selected_weights",
                "inner_minimum_gate_metrics",
            }
        },
        "selected_weight_counts_loocv": {
            str(weight): primary["selected_weights"].count(weight)
            for weight in WEIGHT_GRID
        },
        "repeated_nested_stratified_5fold": repeated,
        "development_point_gate_passed": point_gate,
        "development_robustness_gate_passed": robustness_gate,
        "eligible_to_freeze_for_new_external_cohort": bool(
            point_gate and robustness_gate
        ),
        "evaluation_seconds": elapsed,
        "source_hashes": {
            **source_hashes,
            "protocol": _sha256(Path(protocol_path).resolve()),
            "baseline_lock": _sha256(Path(baseline_lock_path).resolve()),
            "v23_error_audit_summary": _sha256(Path(audit_summary_path).resolve()),
        },
        "baseline_v23_modified": False,
        "ground_truth_read": True,
        "lesion_masks_read": False,
        "holdout_v21_opened_or_reused": False,
        "hypothesis_predeclared_after_development_labels": True,
        "selection_bias_possible": True,
        "development_only": True,
        "qualified": False,
        "independent_balanced_validation_required": True,
        "research_only": True,
        "clinical_use_allowed": False,
        "requires_human_review": True,
    }

    destination = Path(output_dir).resolve()
    if destination.exists():
        raise PipelineError("Avaliação v24 existente; sobrescrita recusada.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = destination.parent / f"._v24_eval_{uuid.uuid4().hex[:8]}"
    staging.mkdir()
    try:
        _write_json(staging / "evaluation.json", result)
        with (staging / "case_scores.csv").open(
            "w", encoding="utf-8", newline=""
        ) as stream:
            columns = [
                "case_id", "label", FEATURE_NAME, "selected_weight",
                "inner_minimum_gate_metric", "nested_loocv_score",
                "nested_loocv_threshold", "prediction",
            ]
            writer = csv.DictWriter(stream, fieldnames=columns)
            writer.writeheader()
            for index, case_id in enumerate(case_ids):
                writer.writerow({
                    "case_id": case_id,
                    "label": "POSITIVE" if truth[index] else "NEGATIVE",
                    FEATURE_NAME: contrast[index],
                    "selected_weight": primary["selected_weights"][index],
                    "inner_minimum_gate_metric": primary[
                        "inner_minimum_gate_metrics"
                    ][index],
                    "nested_loocv_score": primary["scores"][index],
                    "nested_loocv_threshold": primary["thresholds"][index],
                    "prediction": (
                        "POSITIVE" if primary["predictions"][index] else "NEGATIVE"
                    ),
                })
        _publish_directory(staging, destination)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return result


__all__ = [
    "EVALUATION_SCHEMA",
    "FEATURE_DEFINITION",
    "FEATURE_DIRECTION",
    "FEATURE_NAME",
    "FOLDS",
    "PROTOCOL_SCHEMA",
    "RANDOM_SEED",
    "REPEATS",
    "WEIGHT_GRID",
    "evaluate_v24_planarity_contrast",
    "freeze_v24_planarity_protocol",
    "planarity_contrast",
]
