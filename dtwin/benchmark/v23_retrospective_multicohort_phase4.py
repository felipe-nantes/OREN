"""Patient-level out-of-fold scoring and evaluation for retrospective v23.

The prediction freeze fits ECDF references and the decision threshold only on
each outer training partition.  Technical failures receive no fabricated score
and are converted to errors only by the subsequent protected evaluator.
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
import random
import shutil
import statistics
import uuid
from pathlib import Path
from typing import Any

from dtwin.benchmark.openswisshcc_alignment import _publish_directory
from dtwin.benchmark.openswisshcc_localizer_roi_evaluation import _wilson
from dtwin.benchmark.openswisshcc_v20_fusion import V11_WEIGHTS, _canonical_sha, _ecdf
from dtwin.benchmark.openswisshcc_v23_shape_fusion import (
    PRIMARY_SHAPE_FEATURE,
    SHAPE_WEIGHT,
    V11_WEIGHT,
    _validated_calibrator,
    score_with_frozen_calibrator,
)
from dtwin.benchmark.openswisshcc_volumetric_evaluation import _best_threshold
from dtwin.benchmark.v23_retrospective_multicohort_phase2 import (
    FOLDS,
    REPEATS,
    _load_jsonl,
)
from dtwin.benchmark.v23_retrospective_multicohort_phase3 import (
    verify_phase3_exact_v23_signals,
)
from dtwin.core import PipelineError


PREDICTION_SUMMARY_SCHEMA = "argos-v23-retrospective-phase4-prediction-freeze-v1"
LOOCV_SCHEMA = "argos-v23-retrospective-phase4-loocv-prediction-v1"
REPEATED_SCHEMA = "argos-v23-retrospective-phase4-repeated-prediction-v1"
FROZEN_SCHEMA = "argos-v23-retrospective-phase4-frozen-calibrator-prediction-v1"
EVALUATION_SCHEMA = "argos-v23-retrospective-phase4-evaluation-v1"
BOOTSTRAP_REPLICATES = 10_000
BOOTSTRAP_SEED = 20260723


def _load(path: Path, description: str) -> dict[str, Any]:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PipelineError(f"{description} ausente ou inválido.") from exc
    if not isinstance(value, dict):
        raise PipelineError(f"{description} deve ser objeto JSON.")
    return value


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with Path(path).open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
    except OSError as exc:
        raise PipelineError(f"Artefato ausente: {path}.") from exc
    return digest.hexdigest()


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(
            json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n"
            for row in rows
        ),
        encoding="utf-8",
    )


def _index(rows: list[dict[str, Any]], description: str) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        case_id = row.get("case_id")
        if not isinstance(case_id, str) or case_id in result:
            raise PipelineError(f"{description} contém caso inválido ou duplicado.")
        result[case_id] = row
    return result


def _phase3_inputs(
    root: Path, summary: dict[str, Any]
) -> tuple[dict[str, dict[str, Any]], set[str]]:
    artifacts = summary["artifacts"]
    signals = _index(
        _load_jsonl(root / artifacts["exact_v23_signals"], "Sinais exatos v23"),
        "Sinais exatos v23",
    )
    failures = _index(
        _load_jsonl(root / artifacts["technical_failures"], "Falhas técnicas v23"),
        "Falhas técnicas v23",
    )
    if set(signals) & set(failures):
        raise PipelineError("Caso aparece como sinal completo e falha técnica.")
    return signals, set(failures)


def _fold_rows(phase2_root: Path, expected_cases: int) -> dict[str, dict[str, Any]]:
    rows = _load_jsonl(
        phase2_root / "protected_ground_truth/fold_assignments.jsonl",
        "Folds protegidos da Fase 2",
    )
    indexed = _index(rows, "Folds protegidos")
    if len(indexed) != expected_cases:
        raise PipelineError("Folds protegidos não cobrem a coorte.")
    for row in indexed.values():
        assignments = row.get("repeated_5fold_outer_assignments")
        if (
            row.get("label") not in {"POSITIVE", "NEGATIVE"}
            or not isinstance(assignments, list)
            or len(assignments) != REPEATS
            or any(not isinstance(value, int) or isinstance(value, bool) or not 0 <= value < FOLDS for value in assignments)
        ):
            raise PipelineError("Label ou atribuição protegida inválida.")
    return indexed


def _references(
    signals: dict[str, dict[str, Any]], training_ids: list[str]
) -> dict[str, list[float]]:
    if not training_ids:
        raise PipelineError("Treino externo sem casos computáveis.")
    references = {
        name: sorted(
            float(signals[case_id]["v11_signals"][name])
            for case_id in training_ids
        )
        for name in V11_WEIGHTS
    }
    references[PRIMARY_SHAPE_FEATURE] = sorted(
        float(signals[case_id][PRIMARY_SHAPE_FEATURE])
        for case_id in training_ids
    )
    return references


def _score(row: dict[str, Any], references: dict[str, list[float]]) -> float:
    v11 = sum(
        V11_WEIGHTS[name]
        * _ecdf(float(row["v11_signals"][name]), references[name])
        for name in V11_WEIGHTS
    )
    shape = _ecdf(
        float(row[PRIMARY_SHAPE_FEATURE]), references[PRIMARY_SHAPE_FEATURE]
    )
    value = V11_WEIGHT * v11 + SHAPE_WEIGHT * shape
    if not math.isfinite(value):
        raise PipelineError("Score v23 out-of-fold não finito.")
    return float(value)


def _fit_threshold(
    *,
    signals: dict[str, dict[str, Any]],
    folds: dict[str, dict[str, Any]],
    training_ids: list[str],
    references: dict[str, list[float]],
) -> float:
    scores = [_score(signals[case_id], references) for case_id in training_ids]
    truth = [folds[case_id]["label"] == "POSITIVE" for case_id in training_ids]
    if len(set(truth)) != 2:
        raise PipelineError("Treino externo não contém as duas classes.")
    threshold, _ = _best_threshold(scores, truth)
    if not math.isfinite(float(threshold)):
        raise PipelineError("Limiar externo v23 não finito.")
    return float(threshold)


def _prediction(
    *,
    schema: str,
    case_id: str,
    score: float | None,
    threshold: float | None,
    status: str,
    extra: dict[str, Any],
) -> dict[str, Any]:
    return {
        "schema": schema,
        "case_id": case_id,
        "status": status,
        "score": score,
        "threshold": threshold,
        "prediction": (
            "POSITIVE"
            if score is not None and threshold is not None and score >= threshold
            else "NEGATIVE"
            if score is not None and threshold is not None
            else "TECHNICAL_FAILURE"
        ),
        **extra,
        "held_out_label_used_for_transform": False,
        "held_out_label_used_for_threshold": False,
        "lesion_masks_read": 0,
        "research_only": True,
        "clinical_use_allowed": False,
    }


def freeze_phase4_oof_predictions(
    *,
    phase3_root: Path,
    phase2_root: Path,
    contract_path: Path,
    baseline_lock_path: Path,
    workspace_root: Path,
    calibrator_path: Path,
    output_dir: Path,
    expected_cases: int = 132,
) -> dict[str, Any]:
    phase3_root = Path(phase3_root).resolve()
    phase2_root = Path(phase2_root).resolve()
    phase3 = verify_phase3_exact_v23_signals(
        phase3_root=phase3_root,
        phase2_root=phase2_root,
        contract_path=contract_path,
        baseline_lock_path=baseline_lock_path,
        workspace_root=workspace_root,
        expected_cases=expected_cases,
    )
    signals, failures = _phase3_inputs(phase3_root, phase3)
    folds = _fold_rows(phase2_root, expected_cases)
    if set(signals) | failures != set(folds):
        raise PipelineError("Sinais, falhas e folds não cobrem os mesmos casos.")
    computable = sorted(signals)
    all_ids = sorted(folds)

    loocv: list[dict[str, Any]] = []
    for held_out in all_ids:
        if held_out in failures:
            loocv.append(
                _prediction(
                    schema=LOOCV_SCHEMA,
                    case_id=held_out,
                    score=None,
                    threshold=None,
                    status="technical_failure_count_as_error",
                    extra={
                        "outer_fold_id": held_out,
                        "training_case_count": expected_cases - 1,
                        "training_computable_count": len(computable),
                    },
                )
            )
            continue
        training_ids = [case_id for case_id in computable if case_id != held_out]
        references = _references(signals, training_ids)
        threshold = _fit_threshold(
            signals=signals,
            folds=folds,
            training_ids=training_ids,
            references=references,
        )
        loocv.append(
            _prediction(
                schema=LOOCV_SCHEMA,
                case_id=held_out,
                score=_score(signals[held_out], references),
                threshold=threshold,
                status="complete_out_of_fold_prediction",
                extra={
                    "outer_fold_id": held_out,
                    "training_case_count": expected_cases - 1,
                    "training_computable_count": len(training_ids),
                },
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
            training_ids = [
                case_id
                for case_id in computable
                if folds[case_id]["repeated_5fold_outer_assignments"][repeat] != fold
            ]
            references = _references(signals, training_ids)
            threshold = _fit_threshold(
                signals=signals,
                folds=folds,
                training_ids=training_ids,
                references=references,
            )
            for case_id in test_ids:
                failed = case_id in failures
                repeated.append(
                    _prediction(
                        schema=REPEATED_SCHEMA,
                        case_id=case_id,
                        score=None if failed else _score(signals[case_id], references),
                        threshold=None if failed else threshold,
                        status=(
                            "technical_failure_count_as_error"
                            if failed
                            else "complete_out_of_fold_prediction"
                        ),
                        extra={
                            "repeat": repeat,
                            "outer_fold": fold,
                            "training_case_count": expected_cases - len(test_ids),
                            "training_computable_count": len(training_ids),
                        },
                    )
                )
    if len(repeated) != expected_cases * REPEATS:
        raise PipelineError("Predições repetidas não cobrem 50× a coorte.")

    calibrator = _validated_calibrator(_load(calibrator_path, "Calibrador v23"))
    frozen: list[dict[str, Any]] = []
    for case_id in all_ids:
        if case_id in failures:
            frozen.append(
                _prediction(
                    schema=FROZEN_SCHEMA,
                    case_id=case_id,
                    score=None,
                    threshold=None,
                    status="technical_failure_count_as_error",
                    extra={
                        "calibrator_signature": calibrator["calibrator_signature"],
                        "secondary_estimand_only": True,
                    },
                )
            )
            continue
        scored = score_with_frozen_calibrator(
            calibrator,
            signals=signals[case_id]["v11_signals"],
            weighted_linearity=float(signals[case_id][PRIMARY_SHAPE_FEATURE]),
        )
        frozen.append(
            _prediction(
                schema=FROZEN_SCHEMA,
                case_id=case_id,
                score=float(scored["score"]),
                threshold=float(scored["threshold"]),
                status="complete_frozen_calibrator_prediction",
                extra={
                    "calibrator_signature": scored["calibrator_signature"],
                    "secondary_estimand_only": True,
                },
            )
        )

    destination = Path(output_dir).resolve()
    if destination.exists():
        raise PipelineError("Freeze de predições da Fase 4 já existe.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = destination.parent / f"._v23_phase4_predictions_{uuid.uuid4().hex[:8]}"
    staging.mkdir()
    try:
        _write_jsonl(staging / "loocv_predictions.jsonl", loocv)
        _write_jsonl(staging / "repeated_5fold_predictions.jsonl", repeated)
        _write_jsonl(staging / "frozen_calibrator_predictions.jsonl", frozen)
        artifacts = {}
        for key, filename in (
            ("loocv_predictions", "loocv_predictions.jsonl"),
            ("repeated_5fold_predictions", "repeated_5fold_predictions.jsonl"),
            ("frozen_calibrator_predictions", "frozen_calibrator_predictions.jsonl"),
        ):
            artifacts[key] = filename
            artifacts[f"{key}_sha256"] = _sha256(staging / filename)
        body = {
            "schema": PREDICTION_SUMMARY_SCHEMA,
            "status": "phase4_patient_level_oof_predictions_frozen",
            "case_count": expected_cases,
            "computable_case_count": len(signals),
            "technical_failure_count": len(failures),
            "loocv_prediction_count": len(loocv),
            "repeated_prediction_count": len(repeated),
            "frozen_calibrator_prediction_count": len(frozen),
            "repeats": REPEATS,
            "folds": FOLDS,
            "weights": {"v11": V11_WEIGHT, PRIMARY_SHAPE_FEATURE: SHAPE_WEIGHT},
            "ecdf_fit_on_outer_training_only": True,
            "threshold_fit_on_outer_training_only": True,
            "technical_failures_scored": False,
            "technical_failures_must_count_as_errors_during_evaluation": True,
            "phase3_signature": phase3["phase3_signature"],
            "source_hashes": {
                "phase3_summary": _sha256(phase3_root / "summary.json"),
                "protected_fold_assignments": _sha256(
                    phase2_root / "protected_ground_truth/fold_assignments.jsonl"
                ),
                "split_protocol": _sha256(phase2_root / "split_protocol.json"),
                "frozen_calibrator": _sha256(Path(calibrator_path)),
            },
            "artifacts": artifacts,
            "metrics_calculated": False,
            "research_only": True,
            "clinical_use_allowed": False,
        }
        summary = {**body, "prediction_freeze_signature": _canonical_sha(body)}
        _write_json(staging / "summary.json", summary)
        _publish_directory(staging, destination)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return summary


def verify_phase4_prediction_freeze(
    *,
    prediction_root: Path,
    phase3_root: Path,
    phase2_root: Path,
    contract_path: Path,
    baseline_lock_path: Path,
    workspace_root: Path,
    expected_cases: int = 132,
) -> tuple[dict[str, Any], dict[str, list[dict[str, Any]]]]:
    phase3 = verify_phase3_exact_v23_signals(
        phase3_root=phase3_root,
        phase2_root=phase2_root,
        contract_path=contract_path,
        baseline_lock_path=baseline_lock_path,
        workspace_root=workspace_root,
        expected_cases=expected_cases,
    )
    root = Path(prediction_root).resolve()
    summary = _load(root / "summary.json", "Freeze de predições da Fase 4")
    unsigned = dict(summary)
    signature = unsigned.pop("prediction_freeze_signature", None)
    artifacts = summary.get("artifacts")
    if (
        summary.get("schema") != PREDICTION_SUMMARY_SCHEMA
        or summary.get("status") != "phase4_patient_level_oof_predictions_frozen"
        or signature != _canonical_sha(unsigned)
        or summary.get("phase3_signature") != phase3["phase3_signature"]
        or summary.get("case_count") != expected_cases
        or summary.get("metrics_calculated") is not False
        or summary.get("ecdf_fit_on_outer_training_only") is not True
        or summary.get("threshold_fit_on_outer_training_only") is not True
        or not isinstance(artifacts, dict)
    ):
        raise PipelineError("Freeze de predições da Fase 4 adulterado.")
    loaded: dict[str, list[dict[str, Any]]] = {}
    for key in (
        "loocv_predictions",
        "repeated_5fold_predictions",
        "frozen_calibrator_predictions",
    ):
        relative = artifacts.get(key)
        if (
            not isinstance(relative, str)
            or Path(relative).is_absolute()
            or ".." in Path(relative).parts
            or _sha256(root / relative) != artifacts.get(f"{key}_sha256")
        ):
            raise PipelineError("Arquivo de predição da Fase 4 adulterado.")
        loaded[key] = _load_jsonl(root / relative, key)
    expected_lengths = {
        "loocv_predictions": expected_cases,
        "repeated_5fold_predictions": expected_cases * REPEATS,
        "frozen_calibrator_predictions": expected_cases,
    }
    for key, rows in loaded.items():
        if len(rows) != expected_lengths[key] or any("label" in row for row in rows):
            raise PipelineError("Predições da Fase 4 têm cobertura ou vazamento inválido.")
        for row in rows:
            if (
                row.get("prediction") not in {"POSITIVE", "NEGATIVE", "TECHNICAL_FAILURE"}
                or row.get("held_out_label_used_for_transform") is not False
                or row.get("held_out_label_used_for_threshold") is not False
                or row.get("lesion_masks_read") != 0
            ):
                raise PipelineError("Registro de predição da Fase 4 inválido.")
    if len({row["case_id"] for row in loaded["loocv_predictions"]}) != expected_cases:
        raise PipelineError("LOOCV não contém uma predição por caso.")
    repeated_keys = {
        (row["case_id"], row.get("repeat")) for row in loaded["repeated_5fold_predictions"]
    }
    if len(repeated_keys) != expected_cases * REPEATS:
        raise PipelineError("Predições repetidas contêm duplicação ou ausência.")
    return summary, loaded


def _confusion(
    rows: list[dict[str, Any]], labels: dict[str, str]
) -> dict[str, Any]:
    tp = tn = fp = fn = failures = 0
    for row in rows:
        label = labels[row["case_id"]]
        prediction = row["prediction"]
        if prediction == "TECHNICAL_FAILURE":
            failures += 1
            if label == "POSITIVE":
                fn += 1
            else:
                fp += 1
        elif label == "POSITIVE":
            tp += int(prediction == "POSITIVE")
            fn += int(prediction != "POSITIVE")
        else:
            tn += int(prediction == "NEGATIVE")
            fp += int(prediction != "NEGATIVE")
    sensitivity = tp / (tp + fn)
    specificity = tn / (tn + fp)
    return {
        "tp": tp,
        "tn": tn,
        "fp": fp,
        "fn": fn,
        "technical_failures_counted_as_errors": failures,
        "sensitivity": sensitivity,
        "specificity": specificity,
        "balanced_accuracy": (sensitivity + specificity) / 2.0,
        "passed_75_75": sensitivity >= 0.75 and specificity >= 0.75,
    }


def _roc_auc(rows: list[dict[str, Any]], labels: dict[str, str]) -> dict[str, Any]:
    values = [
        (float(row["score"]), labels[row["case_id"]] == "POSITIVE")
        for row in rows
        if row["score"] is not None
    ]
    positive = [score for score, truth in values if truth]
    negative = [score for score, truth in values if not truth]
    if not positive or not negative:
        raise PipelineError("AUC sem as duas classes computáveis.")
    wins = sum(
        1.0 if p > n else 0.5 if p == n else 0.0
        for p in positive
        for n in negative
    )
    return {
        "roc_auc": wins / (len(positive) * len(negative)),
        "computable_case_count": len(values),
        "positive_count": len(positive),
        "negative_count": len(negative),
        "technical_failures_excluded_because_score_is_undefined": True,
        "secondary_only": True,
    }


def _bootstrap(
    rows: list[dict[str, Any]], labels: dict[str, str]
) -> dict[str, Any]:
    by_label = {
        label: [row for row in rows if labels[row["case_id"]] == label]
        for label in ("POSITIVE", "NEGATIVE")
    }
    rng = random.Random(BOOTSTRAP_SEED)
    sensitivities: list[float] = []
    specificities: list[float] = []
    for _ in range(BOOTSTRAP_REPLICATES):
        sampled = [
            rng.choice(by_label[label])
            for label in ("POSITIVE", "NEGATIVE")
            for _ in range(len(by_label[label]))
        ]
        metric = _confusion(sampled, labels)
        sensitivities.append(float(metric["sensitivity"]))
        specificities.append(float(metric["specificity"]))

    def interval(values: list[float]) -> dict[str, float]:
        ordered = sorted(values)
        return {
            "low": ordered[int(0.025 * (len(ordered) - 1))],
            "high": ordered[int(0.975 * (len(ordered) - 1))],
        }

    return {
        "method": "patient_level_stratified_percentile_bootstrap",
        "replicates": BOOTSTRAP_REPLICATES,
        "seed": BOOTSTRAP_SEED,
        "sensitivity_95": interval(sensitivities),
        "specificity_95": interval(specificities),
    }


def evaluate_phase4_predictions(
    *,
    prediction_root: Path,
    phase3_root: Path,
    phase2_root: Path,
    contract_path: Path,
    baseline_lock_path: Path,
    workspace_root: Path,
    output_dir: Path,
    expected_cases: int = 132,
    expected_positive: int = 63,
    expected_negative: int = 69,
) -> dict[str, Any]:
    prediction_summary, predictions = verify_phase4_prediction_freeze(
        prediction_root=prediction_root,
        phase3_root=phase3_root,
        phase2_root=phase2_root,
        contract_path=contract_path,
        baseline_lock_path=baseline_lock_path,
        workspace_root=workspace_root,
        expected_cases=expected_cases,
    )
    fold_rows = _fold_rows(Path(phase2_root), expected_cases)
    labels = {case_id: row["label"] for case_id, row in fold_rows.items()}
    if (
        sum(label == "POSITIVE" for label in labels.values()) != expected_positive
        or sum(label == "NEGATIVE" for label in labels.values()) != expected_negative
    ):
        raise PipelineError("Contagens protegidas divergiram na avaliação.")
    loocv = predictions["loocv_predictions"]
    primary = _confusion(loocv, labels)
    repeated_metrics = []
    repeated_rows = predictions["repeated_5fold_predictions"]
    for repeat in range(REPEATS):
        metric = _confusion(
            [row for row in repeated_rows if row["repeat"] == repeat], labels
        )
        repeated_metrics.append({"repeat": repeat, **metric})
    frozen = _confusion(predictions["frozen_calibrator_predictions"], labels)
    result_body = {
        "schema": EVALUATION_SCHEMA,
        "status": (
            "phase4_statistical_gate_passed_time_gate_pending"
            if primary["passed_75_75"]
            else "phase4_statistical_gate_failed"
        ),
        "case_count": expected_cases,
        "positive_count": expected_positive,
        "negative_count": expected_negative,
        "primary_estimand": "patient_level_leave_one_out_v23_family",
        "primary_loocv": {
            **primary,
            "wilson_95": {
                "sensitivity": _wilson(primary["tp"], primary["tp"] + primary["fn"]),
                "specificity": _wilson(primary["tn"], primary["tn"] + primary["fp"]),
            },
            "bootstrap_95": _bootstrap(loocv, labels),
            "roc_auc": _roc_auc(loocv, labels),
        },
        "repeated_stratified_5fold": {
            "repeats": REPEATS,
            "folds": FOLDS,
            "runs_passing_75_75": sum(
                bool(row["passed_75_75"]) for row in repeated_metrics
            ),
            "median_sensitivity": statistics.median(
                float(row["sensitivity"]) for row in repeated_metrics
            ),
            "median_specificity": statistics.median(
                float(row["specificity"]) for row in repeated_metrics
            ),
            "minimum_sensitivity": min(
                float(row["sensitivity"]) for row in repeated_metrics
            ),
            "minimum_specificity": min(
                float(row["specificity"]) for row in repeated_metrics
            ),
            "all_predictions_out_of_fold": True,
        },
        "secondary_frozen_calibrator_not_primary": frozen,
        "statistical_75_75_gate_passed": bool(primary["passed_75_75"]),
        "raw_dicom_end_to_end_180_second_gate_evaluated": False,
        "final_pipeline_success_claimed": False,
        "claim_scope": "retrospective_multicohort_available_project_data",
        "limitations": [
            "OpenSwissHCC was previously exposed during project development.",
            "This is retrospective out-of-fold evidence, not independent external validation.",
            "ROC-AUC excludes technical failures because they have no defined score.",
            "The raw-DICOM end-to-end 180-second gate remains pending.",
        ],
        "source_hashes": {
            "prediction_summary": _sha256(Path(prediction_root) / "summary.json"),
            "prediction_freeze_signature": prediction_summary[
                "prediction_freeze_signature"
            ],
            "protected_fold_assignments": _sha256(
                Path(phase2_root) / "protected_ground_truth/fold_assignments.jsonl"
            ),
        },
        "lesion_masks_read": 0,
        "research_only": True,
        "clinical_use_allowed": False,
    }
    result = {**result_body, "evaluation_signature": _canonical_sha(result_body)}

    destination = Path(output_dir).resolve()
    if destination.exists():
        raise PipelineError("Avaliação da Fase 4 já existe.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = destination.parent / f"._v23_phase4_evaluation_{uuid.uuid4().hex[:8]}"
    staging.mkdir()
    try:
        _write_json(staging / "evaluation.json", result)
        with (staging / "case_results.csv").open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=[
                    "case_id",
                    "label",
                    "status",
                    "score",
                    "threshold",
                    "prediction",
                    "correct",
                ],
            )
            writer.writeheader()
            for row in loocv:
                label = labels[row["case_id"]]
                writer.writerow(
                    {
                        "case_id": row["case_id"],
                        "label": label,
                        "status": row["status"],
                        "score": row["score"],
                        "threshold": row["threshold"],
                        "prediction": row["prediction"],
                        "correct": row["prediction"] == label,
                    }
                )
        with (staging / "repeat_metrics.csv").open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(repeated_metrics[0]))
            writer.writeheader()
            writer.writerows(repeated_metrics)
        _publish_directory(staging, destination)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return result


def verify_phase4_evaluation(
    *,
    evaluation_root: Path,
    prediction_root: Path,
    phase3_root: Path,
    phase2_root: Path,
    contract_path: Path,
    baseline_lock_path: Path,
    workspace_root: Path,
    expected_cases: int = 132,
) -> dict[str, Any]:
    prediction_summary, _ = verify_phase4_prediction_freeze(
        prediction_root=prediction_root,
        phase3_root=phase3_root,
        phase2_root=phase2_root,
        contract_path=contract_path,
        baseline_lock_path=baseline_lock_path,
        workspace_root=workspace_root,
        expected_cases=expected_cases,
    )
    root = Path(evaluation_root).resolve()
    result = _load(root / "evaluation.json", "Avaliação da Fase 4")
    unsigned = dict(result)
    signature = unsigned.pop("evaluation_signature", None)
    if (
        result.get("schema") != EVALUATION_SCHEMA
        or signature != _canonical_sha(unsigned)
        or result.get("case_count") != expected_cases
        or result.get("source_hashes", {}).get("prediction_freeze_signature")
        != prediction_summary["prediction_freeze_signature"]
        or result.get("lesion_masks_read") != 0
        or result.get("final_pipeline_success_claimed") is not False
        or not (root / "case_results.csv").is_file()
        or not (root / "repeat_metrics.csv").is_file()
    ):
        raise PipelineError("Avaliação da Fase 4 adulterada ou incompleta.")
    return result


__all__ = [
    "EVALUATION_SCHEMA",
    "PREDICTION_SUMMARY_SCHEMA",
    "evaluate_phase4_predictions",
    "freeze_phase4_oof_predictions",
    "verify_phase4_evaluation",
    "verify_phase4_prediction_freeze",
]
