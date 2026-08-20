"""Nested evaluation of the predeclared v26 bounding-box-fill extension.

The v26 hypothesis adds candidate-weighted bounding-box fill to the frozen
v23 anchor. Feature weight and decision threshold are fitted only inside
training folds.
"""
from __future__ import annotations

import csv
import shutil
import time
import uuid
from pathlib import Path
from typing import Any

from dtwin.benchmark.openswisshcc_alignment import _publish_directory
from dtwin.benchmark.openswisshcc_candidate_shape import CASE_SCHEMA
from dtwin.benchmark.openswisshcc_v20_fusion import BLIND_SIGNAL_SCHEMA, _canonical_sha
from dtwin.benchmark.openswisshcc_v23_baseline import verify_v23_baseline_lock
from dtwin.benchmark.openswisshcc_v24_planarity_contrast import (
    FOLDS,
    RANDOM_SEED,
    REPEATS,
    WEIGHT_GRID,
    _finite,
    _load_json,
    _load_jsonl,
    _nested_loocv,
    _nested_repeated_stratified,
    _sha256,
    _workspace_path,
    _write_json,
)
from dtwin.core import PipelineError

PROTOCOL_SCHEMA = "argos-openswisshcc-v26-bbox-fill-protocol-v1"
EVALUATION_SCHEMA = "argos-openswisshcc-v26-bbox-fill-evaluation-v1"
FEATURE_NAME = "candidate_weighted_bbox_fill"
FEATURE_DEFINITION = "candidate_weighted_bbox_fill"
FEATURE_DIRECTION = "higher_is_more_positive"
EVALUATION_CORE_RELATIVE_PATH = (
    "dtwin/benchmark/openswisshcc_v24_planarity_contrast.py"
)


def bbox_fill(features: dict[str, Any]) -> float:
    """Return the predeclared label-blind v26 morphology feature."""

    value = _finite(features.get(FEATURE_NAME), "Preenchimento ponderado da bbox")
    if not 0.0 <= value <= 1.0:
        raise PipelineError("Preenchimento da bbox fora de [0, 1].")
    return float(value)


def _code_path(workspace: Path) -> Path:
    path = _workspace_path(
        workspace,
        "dtwin/benchmark/openswisshcc_v26_bbox_fill.py",
    )
    if not path.is_file():
        raise PipelineError("Código v26 não está no workspace esperado.")
    return path


def _evaluation_core_path(workspace: Path) -> Path:
    path = _workspace_path(workspace, EVALUATION_CORE_RELATIVE_PATH)
    if not path.is_file():
        raise PipelineError("Núcleo estatístico v26 não está no workspace esperado.")
    return path


def _source_hashes(
    *,
    baseline_lock_path: Path,
    audit_summary_path: Path,
    workspace_root: Path,
) -> dict[str, str]:
    workspace = Path(workspace_root)
    return {
        "baseline_lock": _sha256(Path(baseline_lock_path).resolve()),
        "v23_error_audit_summary": _sha256(Path(audit_summary_path).resolve()),
        "implementation": _sha256(_code_path(workspace)),
        "nested_evaluation_core": _sha256(_evaluation_core_path(workspace)),
    }


def freeze_v26_bbox_fill_protocol(
    *,
    baseline_lock_path: Path,
    audit_summary_path: Path,
    workspace_root: Path,
    output_path: Path,
) -> dict[str, Any]:
    """Freeze hypothesis, implementation and statistical core before metrics."""

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
        raise PipelineError("Auditoria v23 não é válida para congelar a hipótese v26.")
    base = {
        "schema": PROTOCOL_SCHEMA,
        "status": "frozen_after_v25_rejection_before_v26_metrics",
        "case_count": baseline["case_count"],
        "anchor": "frozen_v23_80_percent_v11_20_percent_weighted_linearity",
        "feature_name": FEATURE_NAME,
        "feature_definition": FEATURE_DEFINITION,
        "feature_direction": FEATURE_DIRECTION,
        "clinical_morphology_intent": (
            "testar candidato compacto versus ocupacao esparsa sem alterar v23"
        ),
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
            "must_improve_primary_balanced_accuracy_vs_v23": True,
            "inconclusive_counts_as_error": True,
            "technical_failure_counts_as_error": True,
        },
        "source_hashes": _source_hashes(
            baseline_lock_path=baseline_lock_path,
            audit_summary_path=audit_summary_path,
            workspace_root=workspace_root,
        ),
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
        existing = _load_json(destination, "Protocolo v26 existente")
        if existing != protocol:
            raise PipelineError("Protocolo v26 existente diverge; sobrescrita recusada.")
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
    protocol = _load_json(Path(protocol_path).resolve(), "Protocolo v26")
    signature = protocol.get("protocol_signature")
    unsigned = dict(protocol)
    unsigned.pop("protocol_signature", None)
    expected_hashes = _source_hashes(
        baseline_lock_path=baseline_lock_path,
        audit_summary_path=audit_summary_path,
        workspace_root=workspace_root,
    )
    if (
        protocol.get("schema") != PROTOCOL_SCHEMA
        or protocol.get("status")
        != "frozen_after_v25_rejection_before_v26_metrics"
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
        raise PipelineError("Protocolo v26 ausente, adulterado ou divergente.")
    return protocol


def _load_development_matrix(
    *,
    baseline_lock_path: Path,
    workspace_root: Path,
) -> tuple[
    list[str],
    list[dict[str, Any]],
    list[float],
    list[float],
    list[bool],
    dict[str, str],
]:
    baseline = verify_v23_baseline_lock(
        lock_path=baseline_lock_path,
        workspace_root=workspace_root,
    )
    lock = _load_json(Path(baseline_lock_path).resolve(), "Lock v23")
    roles = lock.get("artifact_roles", {})
    required = {"case_scores", "v20_signals", "shape_features", "development_labels"}
    if not isinstance(roles, dict) or not required.issubset(roles):
        raise PipelineError("Lock v23 incompleto para avaliação v26.")
    workspace = Path(workspace_root).resolve()
    paths = {name: _workspace_path(workspace, roles[name]) for name in required}
    label_path = paths["development_labels"]
    if label_path.name != "development_labels.jsonl" or any(
        "holdout" in part.lower() for part in label_path.parts
    ):
        raise PipelineError("Avaliação v26 aceita somente labels de desenvolvimento.")
    try:
        with paths["case_scores"].open("r", encoding="utf-8", newline="") as stream:
            score_rows = list(csv.DictReader(stream))
    except OSError as exc:
        raise PipelineError("Scores v23 ausentes para v26.") from exc
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
        raise PipelineError("Coortes v20/v23/v26 não correspondem.")

    ordered_signals: list[dict[str, Any]] = []
    linearity: list[float] = []
    fill_values: list[float] = []
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
            raise PipelineError(f"Entrada insegura ou inválida para v26: {case_id}.")
        features = shape.get("features")
        if not isinstance(features, dict):
            raise PipelineError(f"Features v26 ausentes: {case_id}.")
        ordered_signals.append(signal)
        linearity.append(
            _finite(features.get("candidate_weighted_linearity"), "Linearidade v26")
        )
        fill_values.append(bbox_fill(features))
        truth.append(label == "POSITIVE")
    return (
        case_ids,
        ordered_signals,
        linearity,
        fill_values,
        truth,
        {name: _sha256(path) for name, path in paths.items()},
    )


def evaluate_v26_bbox_fill(
    *,
    protocol_path: Path,
    baseline_lock_path: Path,
    audit_summary_path: Path,
    workspace_root: Path,
    output_dir: Path,
    allow_protected_development_labels: bool = False,
) -> dict[str, Any]:
    """Run the nested development evaluation after freezing the protocol."""

    if allow_protected_development_labels is not True:
        raise PipelineError("Abertura dos labels de desenvolvimento v26 não autorizada.")
    protocol = _verify_protocol(
        protocol_path=protocol_path,
        baseline_lock_path=baseline_lock_path,
        audit_summary_path=audit_summary_path,
        workspace_root=workspace_root,
    )
    case_ids, rows, linearity, fill_values, truth, source_hashes = (
        _load_development_matrix(
            baseline_lock_path=baseline_lock_path,
            workspace_root=workspace_root,
        )
    )
    started = time.perf_counter()
    primary = _nested_loocv(rows, linearity, fill_values, truth)
    repeated = _nested_repeated_stratified(
        rows,
        linearity,
        fill_values,
        truth,
    )
    elapsed = time.perf_counter() - started
    point_gate = bool(
        primary["sensitivity"] >= 0.75 and primary["specificity"] >= 0.75
    )
    robustness_gate = repeated["runs_passing_75_75"] == REPEATS
    v23_balanced_accuracy = float(
        verify_v23_baseline_lock(
            lock_path=baseline_lock_path,
            workspace_root=workspace_root,
        )["primary_loocv_metrics"]["balanced_accuracy"]
    )
    improvement_gate = (
        float(primary["balanced_accuracy"]) > v23_balanced_accuracy
    )
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
            if key
            not in {
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
        "v23_balanced_accuracy": v23_balanced_accuracy,
        "development_improvement_vs_v23_passed": improvement_gate,
        "eligible_to_freeze_for_new_external_cohort": bool(
            point_gate and robustness_gate and improvement_gate
        ),
        "evaluation_seconds": elapsed,
        "source_hashes": {
            **source_hashes,
            "protocol": _sha256(Path(protocol_path).resolve()),
            "baseline_lock": _sha256(Path(baseline_lock_path).resolve()),
            "v23_error_audit_summary": _sha256(Path(audit_summary_path).resolve()),
            "nested_evaluation_core": _sha256(
                _evaluation_core_path(Path(workspace_root))
            ),
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
        raise PipelineError("Avaliação v26 existente; sobrescrita recusada.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = destination.parent / f"._v26_eval_{uuid.uuid4().hex[:8]}"
    staging.mkdir()
    try:
        _write_json(staging / "evaluation.json", result)
        with (staging / "case_scores.csv").open(
            "w",
            encoding="utf-8",
            newline="",
        ) as stream:
            columns = [
                "case_id",
                "label",
                FEATURE_NAME,
                "selected_weight",
                "inner_minimum_gate_metric",
                "nested_loocv_score",
                "nested_loocv_threshold",
                "prediction",
            ]
            writer = csv.DictWriter(stream, fieldnames=columns)
            writer.writeheader()
            for index, case_id in enumerate(case_ids):
                writer.writerow(
                    {
                        "case_id": case_id,
                        "label": "POSITIVE" if truth[index] else "NEGATIVE",
                        FEATURE_NAME: fill_values[index],
                        "selected_weight": primary["selected_weights"][index],
                        "inner_minimum_gate_metric": primary[
                            "inner_minimum_gate_metrics"
                        ][index],
                        "nested_loocv_score": primary["scores"][index],
                        "nested_loocv_threshold": primary["thresholds"][index],
                        "prediction": (
                            "POSITIVE"
                            if primary["predictions"][index]
                            else "NEGATIVE"
                        ),
                    }
                )
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
    "PROTOCOL_SCHEMA",
    "bbox_fill",
    "evaluate_v26_bbox_fill",
    "freeze_v26_bbox_fill_protocol",
]
