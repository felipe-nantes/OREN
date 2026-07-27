"""Out-of-fold evaluation of the frozen v24 liver-enriched signal."""
from __future__ import annotations

import json
import math
import shutil
import statistics
import uuid
from pathlib import Path
from typing import Any

from dtwin.benchmark.openswisshcc_alignment import _publish_directory
from dtwin.benchmark.openswisshcc_v20_fusion import _canonical_sha, _ecdf
from dtwin.benchmark.openswisshcc_volumetric_evaluation import _best_threshold
from dtwin.benchmark.v23_retrospective_multicohort_phase2 import FOLDS, REPEATS
from dtwin.benchmark.v23_retrospective_multicohort_phase4 import (
    _bootstrap,
    _confusion,
    _fold_rows,
    _phase3_inputs,
    _references,
    _roc_auc,
    _score,
    verify_phase4_evaluation,
)
from dtwin.benchmark.v23_retrospective_multicohort_phase3 import (
    verify_phase3_exact_v23_signals,
)
from dtwin.benchmark.v24_liver_enriched_inference import (
    SIGNAL_RULE,
    verify_v24_liver_enriched_inference_run,
)
from dtwin.core import PipelineError


PREDICTION_SCHEMA = "argos-openswisshcc-v24-liver-enriched-oof-prediction-v1"
PREDICTION_FREEZE_SCHEMA = (
    "argos-openswisshcc-v24-liver-enriched-prediction-freeze-v1"
)
EVALUATION_SCHEMA = "argos-openswisshcc-v24-liver-enriched-evaluation-v1"
V23_WEIGHT = 0.80
LIVER_ENRICHED_WEIGHT = 0.20


def _load(path: Path, description: str) -> dict[str, Any]:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PipelineError(f"{description} ausente ou inválido.") from exc
    if not isinstance(value, dict):
        raise PipelineError(f"{description} deve ser objeto JSON.")
    return value


def _jsonl(path: Path, description: str) -> list[dict[str, Any]]:
    try:
        rows = [
            json.loads(line)
            for line in Path(path).read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    except (OSError, json.JSONDecodeError) as exc:
        raise PipelineError(f"{description} ausente ou inválido.") from exc
    if any(not isinstance(row, dict) for row in rows):
        raise PipelineError(f"{description} deve conter objetos.")
    return rows


def _sha256(path: Path) -> str:
    import hashlib

    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text(
        "".join(
            json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n"
            for row in rows
        ),
        encoding="utf-8",
    )


def _new_signals(run_root: Path) -> dict[str, float]:
    result: dict[str, float] = {}
    for row in _jsonl(Path(run_root) / "cases.jsonl", "Sinais v24 congelados"):
        case_id = row.get("case_id")
        value = row.get("max_positive_probability")
        if (
            not isinstance(case_id, str)
            or case_id in result
            or isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(float(value))
            or not 0.0 <= float(value) <= 1.0
            or row.get("signal_rule") != SIGNAL_RULE
        ):
            raise PipelineError("Sinal liver-enriched v24 inválido.")
        result[case_id] = float(value)
    if len(result) != 130:
        raise PipelineError("Sinais liver-enriched não cobrem os 130 casos.")
    return result


def _combined_references(
    signals: dict[str, dict[str, Any]],
    new_signals: dict[str, float],
    training_ids: list[str],
) -> tuple[dict[str, list[float]], list[float]]:
    return (
        _references(signals, training_ids),
        sorted(new_signals[case_id] for case_id in training_ids),
    )


def _combined_score(
    row: dict[str, Any],
    new_signal: float,
    references: dict[str, list[float]],
    new_reference: list[float],
) -> float:
    value = V23_WEIGHT * _score(row, references) + LIVER_ENRICHED_WEIGHT * _ecdf(
        new_signal, new_reference
    )
    if not math.isfinite(value):
        raise PipelineError("Score combinado v24 não finito.")
    return float(value)


def _fit(
    *,
    signals: dict[str, dict[str, Any]],
    new_signals: dict[str, float],
    folds: dict[str, dict[str, Any]],
    training_ids: list[str],
) -> tuple[dict[str, list[float]], list[float], float]:
    references, new_reference = _combined_references(
        signals, new_signals, training_ids
    )
    scores = [
        _combined_score(
            signals[case_id],
            new_signals[case_id],
            references,
            new_reference,
        )
        for case_id in training_ids
    ]
    truth = [folds[case_id]["label"] == "POSITIVE" for case_id in training_ids]
    threshold, _metric = _best_threshold(scores, truth)
    return references, new_reference, float(threshold)


def _prediction(
    *,
    case_id: str,
    score: float | None,
    threshold: float | None,
    status: str,
    extra: dict[str, Any],
) -> dict[str, Any]:
    return {
        "schema": PREDICTION_SCHEMA,
        "case_id": case_id,
        "status": status,
        "score": score,
        "threshold": threshold,
        "prediction": (
            "TECHNICAL_FAILURE"
            if score is None or threshold is None
            else "POSITIVE"
            if score >= threshold
            else "NEGATIVE"
        ),
        **extra,
        "v23_weight": V23_WEIGHT,
        "liver_enriched_weight": LIVER_ENRICHED_WEIGHT,
        "held_out_label_used_for_transform": False,
        "held_out_label_used_for_threshold": False,
        "lesion_masks_read": 0,
    }


def freeze_v24_oof_predictions(
    *,
    phase3_root: Path,
    phase2_root: Path,
    contract_path: Path,
    baseline_lock_path: Path,
    workspace_root: Path,
    source_protocol_path: Path,
    review_path: Path,
    gallery_root: Path,
    config_path: Path,
    panel_root: Path,
    full_verification_path: Path,
    inference_protocol_path: Path,
    inference_root: Path,
    inference_verification_path: Path,
    output_root: Path,
    panel_config_path: Path | None = None,
    candidate_id: str = "v24_candidate_1_v23_plus_liver_enriched",
    predecessor_evaluation_path: Path | None = None,
) -> dict[str, Any]:
    inference_verification = verify_v24_liver_enriched_inference_run(
        source_protocol_path=source_protocol_path,
        review_path=review_path,
        gallery_root=gallery_root,
        config_path=config_path,
        panel_root=panel_root,
        full_verification_path=full_verification_path,
        inference_protocol_path=inference_protocol_path,
        output_root=inference_root,
        panel_config_path=panel_config_path,
        candidate_id=candidate_id,
        predecessor_evaluation_path=predecessor_evaluation_path,
    )
    if _load(inference_verification_path, "Verificação da inferência v24") != inference_verification:
        raise PipelineError("Verificação persistida da inferência v24 divergiu.")
    phase3 = verify_phase3_exact_v23_signals(
        phase3_root=phase3_root,
        phase2_root=phase2_root,
        contract_path=contract_path,
        baseline_lock_path=baseline_lock_path,
        workspace_root=workspace_root,
    )
    signals, failures = _phase3_inputs(Path(phase3_root), phase3)
    folds = _fold_rows(Path(phase2_root), 132)
    new_signals = _new_signals(inference_root)
    if set(signals) != set(new_signals) or set(signals) | failures != set(folds):
        raise PipelineError("Partição de sinais e falhas v24 divergiu.")
    computable = sorted(signals)
    all_ids = sorted(folds)
    loocv: list[dict[str, Any]] = []
    for held_out in all_ids:
        if held_out in failures:
            loocv.append(
                _prediction(
                    case_id=held_out,
                    score=None,
                    threshold=None,
                    status="technical_failure_count_as_error",
                    extra={"validation": "loocv", "outer_fold_id": held_out},
                )
            )
            continue
        training = [case_id for case_id in computable if case_id != held_out]
        references, new_reference, threshold = _fit(
            signals=signals,
            new_signals=new_signals,
            folds=folds,
            training_ids=training,
        )
        loocv.append(
            _prediction(
                case_id=held_out,
                score=_combined_score(
                    signals[held_out],
                    new_signals[held_out],
                    references,
                    new_reference,
                ),
                threshold=threshold,
                status="complete_out_of_fold_prediction",
                extra={"validation": "loocv", "outer_fold_id": held_out},
            )
        )
    repeated: list[dict[str, Any]] = []
    for repeat in range(REPEATS):
        for fold in range(FOLDS):
            test_ids = [
                case_id
                for case_id in all_ids
                if folds[case_id]["repeated_5fold_outer_assignments"][repeat] == fold
            ]
            training = [
                case_id
                for case_id in computable
                if folds[case_id]["repeated_5fold_outer_assignments"][repeat] != fold
            ]
            references, new_reference, threshold = _fit(
                signals=signals,
                new_signals=new_signals,
                folds=folds,
                training_ids=training,
            )
            for case_id in test_ids:
                failed = case_id in failures
                repeated.append(
                    _prediction(
                        case_id=case_id,
                        score=(
                            None
                            if failed
                            else _combined_score(
                                signals[case_id],
                                new_signals[case_id],
                                references,
                                new_reference,
                            )
                        ),
                        threshold=None if failed else threshold,
                        status=(
                            "technical_failure_count_as_error"
                            if failed
                            else "complete_out_of_fold_prediction"
                        ),
                        extra={
                            "validation": "repeated_5fold",
                            "repeat": repeat,
                            "outer_fold": fold,
                        },
                    )
                )
    destination = Path(output_root).resolve()
    if destination.exists():
        raise PipelineError("Freeze de predições v24 já existe.")
    staging = destination.parent / f"._v24_predictions_{uuid.uuid4().hex[:8]}"
    staging.mkdir()
    try:
        _write_jsonl(staging / "loocv_predictions.jsonl", loocv)
        _write_jsonl(staging / "repeated_5fold_predictions.jsonl", repeated)
        body = {
            "schema": PREDICTION_FREEZE_SCHEMA,
            "status": "v24_oof_predictions_frozen_before_metric_calculation",
            "candidate_id": candidate_id,
            "case_count": 132,
            "computable_case_count": 130,
            "technical_failure_count": 2,
            "loocv_prediction_count": len(loocv),
            "repeated_prediction_count": len(repeated),
            "weights": {
                "v23_family": V23_WEIGHT,
                "liver_enriched_max_positive_probability": LIVER_ENRICHED_WEIGHT,
            },
            "ecdf_fit_on_outer_training_only": True,
            "threshold_fit_on_outer_training_only": True,
            "inference_verification_signature": inference_verification[
                "verification_signature"
            ],
            "source_hashes": {
                "inference_cases": _sha256(Path(inference_root) / "cases.jsonl"),
                "phase3_summary": _sha256(Path(phase3_root) / "summary.json"),
            },
            "artifacts": {
                "loocv_predictions": "loocv_predictions.jsonl",
                "loocv_predictions_sha256": _sha256(
                    staging / "loocv_predictions.jsonl"
                ),
                "repeated_predictions": "repeated_5fold_predictions.jsonl",
                "repeated_predictions_sha256": _sha256(
                    staging / "repeated_5fold_predictions.jsonl"
                ),
            },
            "labels_used_only_for_outer_training_and_final_evaluation": True,
            "lesion_masks_read": 0,
            "metrics_calculated": False,
        }
        summary = {**body, "prediction_freeze_signature": _canonical_sha(body)}
        _write_json(staging / "summary.json", summary)
        _publish_directory(staging, destination)
        return summary
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def evaluate_v24_oof_predictions(
    *,
    prediction_root: Path,
    phase2_root: Path,
    v23_evaluation_root: Path,
    v23_prediction_root: Path,
    phase3_root: Path,
    contract_path: Path,
    baseline_lock_path: Path,
    workspace_root: Path,
    output_root: Path,
) -> dict[str, Any]:
    root = Path(prediction_root).resolve()
    summary = _load(root / "summary.json", "Freeze de predições v24")
    unsigned = dict(summary)
    signature = unsigned.pop("prediction_freeze_signature", None)
    artifacts = summary.get("artifacts", {})
    if (
        summary.get("schema") != PREDICTION_FREEZE_SCHEMA
        or summary.get("status")
        != "v24_oof_predictions_frozen_before_metric_calculation"
        or signature != _canonical_sha(unsigned)
        or summary.get("case_count") != 132
        or summary.get("metrics_calculated") is not False
        or _sha256(root / artifacts["loocv_predictions"])
        != artifacts["loocv_predictions_sha256"]
        or _sha256(root / artifacts["repeated_predictions"])
        != artifacts["repeated_predictions_sha256"]
    ):
        raise PipelineError("Freeze de predições v24 adulterado.")
    loocv = _jsonl(root / artifacts["loocv_predictions"], "LOOCV v24")
    repeated = _jsonl(root / artifacts["repeated_predictions"], "Repetições v24")
    folds = _fold_rows(Path(phase2_root), 132)
    labels = {case_id: row["label"] for case_id, row in folds.items()}
    loocv_metric = _confusion(loocv, labels)
    auc = _roc_auc(loocv, labels)
    bootstrap = _bootstrap(loocv, labels)
    repeat_metrics = []
    for repeat in range(REPEATS):
        rows = [row for row in repeated if row["repeat"] == repeat]
        metric = _confusion(rows, labels)
        repeat_metrics.append({"repeat": repeat, **metric})
    v23 = verify_phase4_evaluation(
        evaluation_root=v23_evaluation_root,
        prediction_root=v23_prediction_root,
        phase3_root=phase3_root,
        phase2_root=phase2_root,
        contract_path=contract_path,
        baseline_lock_path=baseline_lock_path,
        workspace_root=workspace_root,
    )
    v23_metric = v23["primary_loocv"]
    current_min = min(loocv_metric["sensitivity"], loocv_metric["specificity"])
    prior_min = min(v23_metric["sensitivity"], v23_metric["specificity"])
    body = {
        "schema": EVALUATION_SCHEMA,
        "status": (
            "v24_candidate_passed"
            if loocv_metric["passed_75_75"] and current_min > prior_min
            else "v24_candidate_failed"
        ),
        "candidate_id": summary.get(
            "candidate_id", "v24_candidate_1_v23_plus_liver_enriched"
        ),
        "primary_loocv": loocv_metric,
        "roc_auc_secondary": auc,
        "bootstrap_95": bootstrap,
        "repeated_5fold_50": {
            "repeat_count": len(repeat_metrics),
            "passes_75_75": sum(row["passed_75_75"] for row in repeat_metrics),
            "median_sensitivity": statistics.median(
                row["sensitivity"] for row in repeat_metrics
            ),
            "median_specificity": statistics.median(
                row["specificity"] for row in repeat_metrics
            ),
            "minimum_sensitivity": min(
                row["sensitivity"] for row in repeat_metrics
            ),
            "minimum_specificity": min(
                row["specificity"] for row in repeat_metrics
            ),
            "per_repeat": repeat_metrics,
        },
        "comparison_to_v23": {
            "v23_sensitivity": v23_metric["sensitivity"],
            "v23_specificity": v23_metric["specificity"],
            "v23_minimum_axis": prior_min,
            "v24_minimum_axis": current_min,
            "improved_minimum_axis": current_min > prior_min,
        },
        "acceptance": {
            "sensitivity_at_least_75": loocv_metric["sensitivity"] >= 0.75,
            "specificity_at_least_75": loocv_metric["specificity"] >= 0.75,
            "improved_minimum_axis_over_v23": current_min > prior_min,
            "passed": loocv_metric["passed_75_75"] and current_min > prior_min,
        },
        "prediction_freeze_signature": summary["prediction_freeze_signature"],
        "technical_failures_counted_as_errors": True,
        "lesion_masks_read": 0,
        "research_only": True,
        "clinical_use_allowed": False,
    }
    evaluation = {**body, "evaluation_signature": _canonical_sha(body)}
    destination = Path(output_root).resolve()
    if destination.exists():
        raise PipelineError("Avaliação v24 já existe.")
    staging = destination.parent / f"._v24_evaluation_{uuid.uuid4().hex[:8]}"
    staging.mkdir()
    try:
        _write_json(staging / "evaluation.json", evaluation)
        _publish_directory(staging, destination)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return evaluation


__all__ = ["evaluate_v24_oof_predictions", "freeze_v24_oof_predictions"]
