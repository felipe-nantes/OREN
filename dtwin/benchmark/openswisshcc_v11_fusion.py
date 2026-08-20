"""Blind, pre-declared OpenSwissHCC v11 fusion and protected evaluation.

The v11 hypothesis combines three already persisted, label-blind signals:

* balanced MedGemma choice uncertainty (v4);
* inverse sagittal MedSigLIP score (v5);
* log lesion-localizer volume (v10).

No label, decision, threshold, or metric is written while the blind bundle and
protocol are created.  The protected evaluator is a separate, explicit action.
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

from dtwin.benchmark.openswisshcc_alignment import _publish_directory, _sha256
from dtwin.benchmark.openswisshcc_lesion_localizer_evaluation import (
    _load_development_labels,
    _validate_blind_localizer_run,
)
from dtwin.benchmark.openswisshcc_localizer_roi_evaluation import _wilson
from dtwin.benchmark.openswisshcc_volumetric_evaluation import (
    _best_threshold,
    _binary_metrics,
)
from dtwin.core import PipelineError
from dtwin.medgemma_screening import _write_json_atomic

BLIND_BUNDLE_SCHEMA = "argos-openswisshcc-v11-blind-fusion-bundle-v1"
BLIND_SIGNAL_SCHEMA = "argos-openswisshcc-v11-blind-fusion-signal-v1"
PROTOCOL_SCHEMA = "argos-openswisshcc-v11-fusion-protocol-v1"
EVALUATION_SCHEMA = "argos-openswisshcc-v11-development-evaluation-v1"
EXCLUDED_TECHNICAL_CASE = "anon-openswiss-cb2c5c63fc28b8ee"
WEIGHTS = {
    "medgemma_v4_uncertainty_margin": 0.40,
    "medsiglip_v5_inverse_sagittal": 0.40,
    "localizer_v10_log_volume": 0.20,
}


def _load_json(path: Path) -> Any:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PipelineError(f"JSON v11 invalido: {path}") from exc


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    try:
        rows = [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]
    except (OSError, json.JSONDecodeError) as exc:
        raise PipelineError(f"JSONL v11 invalido: {path}") from exc
    if not all(isinstance(row, dict) for row in rows):
        raise PipelineError(f"JSONL v11 contem registro nao-objeto: {path}")
    return rows


def _canonical_sha(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _finite(value: Any, *, minimum: float | None = None, maximum: float | None = None) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        raise PipelineError("Sinal v11 nao e numerico finito.")
    result = float(value)
    if minimum is not None and result < minimum:
        raise PipelineError("Sinal v11 abaixo do limite permitido.")
    if maximum is not None and result > maximum:
        raise PipelineError("Sinal v11 acima do limite permitido.")
    return result


def _rows_by_id(rows: list[dict[str, Any]], *, expected_ids: set[str], excluded_case_id: str) -> dict[str, dict[str, Any]]:
    by_id: dict[str, dict[str, Any]] = {}
    for row in rows:
        case_id = str(row.get("case_id", ""))
        if not case_id.startswith("anon-") or case_id in by_id:
            raise PipelineError("Lote v11 possui case_id invalido ou duplicado.")
        by_id[case_id] = row
    if set(by_id) != expected_ids | {excluded_case_id}:
        raise PipelineError("Lote legado v11 nao cobre exatamente a coorte e a exclusao tecnica pre-declarada.")
    return {case_id: by_id[case_id] for case_id in sorted(expected_ids)}


def _load_v4(root: Path, *, expected_ids: set[str], excluded_case_id: str) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    root = Path(root).resolve()
    summary_path, scores_path = root / "summary.json", root / "scores.jsonl"
    summary = _load_json(summary_path)
    if (
        not isinstance(summary, dict)
        or summary.get("schema") != "argos-openswisshcc-choice-score-batch-v1"
        or summary.get("case_count") != len(expected_ids) + 1
        or summary.get("scores_sha256") != _sha256(scores_path)
        or summary.get("ground_truth_read") is not False
        or summary.get("metrics_calculated") is not False
        or summary.get("research_only") is not True
        or summary.get("clinical_use_allowed") is not False
    ):
        raise PipelineError("Lote MedGemma v4 nao esta completo, integro e cego.")
    rows = _rows_by_id(_load_jsonl(scores_path), expected_ids=expected_ids, excluded_case_id=excluded_case_id)
    values: dict[str, dict[str, Any]] = {}
    for case_id, row in rows.items():
        probabilities = row.get("choice_probabilities")
        if (
            row.get("schema") != "argos-openswisshcc-choice-score-v1"
            or row.get("ground_truth_read") is not False
            or row.get("research_only") is not True
            or row.get("clinical_use_allowed") is not False
            or "label" in row
            or not isinstance(probabilities, dict)
            or set(probabilities) != {"NEGATIVA", "INCONCLUSIVA", "POSITIVA"}
        ):
            raise PipelineError(f"Registro MedGemma v4 invalido: {case_id}.")
        probs = {key: _finite(value, minimum=0.0, maximum=1.0) for key, value in probabilities.items()}
        if not math.isclose(sum(probs.values()), 1.0, abs_tol=2e-5):
            raise PipelineError(f"Probabilidades MedGemma v4 nao somam 1: {case_id}.")
        values[case_id] = {
            "value": probs["INCONCLUSIVA"] - probs["NEGATIVA"],
            "panel_sha256": str(row.get("panel_sha256", "")),
            "elapsed_seconds": _finite(row.get("elapsed_seconds"), minimum=0.0),
        }
    return values, {"summary_sha256": _sha256(summary_path), "scores_sha256": _sha256(scores_path)}


def _load_v5(root: Path, *, expected_ids: set[str], excluded_case_id: str) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    root = Path(root).resolve()
    summary_path, scores_path = root / "summary.json", root / "scores.jsonl"
    summary = _load_json(summary_path)
    if (
        not isinstance(summary, dict)
        or summary.get("schema") != "argos-openswisshcc-medsiglip-score-batch-v1"
        or summary.get("case_count") != len(expected_ids) + 1
        or summary.get("scores_sha256") != _sha256(scores_path)
        or summary.get("ground_truth_read") is not False
        or summary.get("metrics_calculated") is not False
        or summary.get("final_decision") is not None
        or summary.get("research_only") is not True
        or summary.get("clinical_use_allowed") is not False
    ):
        raise PipelineError("Lote MedSigLIP v5 nao esta completo, integro e cego.")
    rows = _rows_by_id(_load_jsonl(scores_path), expected_ids=expected_ids, excluded_case_id=excluded_case_id)
    values: dict[str, dict[str, Any]] = {}
    for case_id, row in rows.items():
        score = row.get("score")
        scores = score.get("scores") if isinstance(score, dict) else None
        views = score.get("view_order") if isinstance(score, dict) else None
        if (
            row.get("schema") != "argos-openswisshcc-medsiglip-score-v1"
            or row.get("ground_truth_read") is not False
            or row.get("research_only") is not True
            or row.get("clinical_use_allowed") is not False
            or "label" in row
            or not isinstance(score, dict)
            or score.get("final_decision") is not None
            or score.get("research_only") is not True
            or score.get("clinical_use_allowed") is not False
            or not isinstance(scores, list)
            or len(scores) != 11
            or not isinstance(views, list)
            or len(views) != 11
            or views[-1] != "sagittal"
        ):
            raise PipelineError(f"Registro MedSigLIP v5 invalido: {case_id}.")
        sagittal = scores[-1]
        probability = sagittal.get("positive_probability") if isinstance(sagittal, dict) else None
        values[case_id] = {
            "value": -_finite(probability, minimum=0.0, maximum=1.0),
            "panel_sha256": str(row.get("panel_sha256", "")),
            "elapsed_seconds": _finite(row.get("elapsed_seconds"), minimum=0.0),
        }
    return values, {"summary_sha256": _sha256(summary_path), "scores_sha256": _sha256(scores_path)}


def build_blind_signal_bundle(
    *,
    medgemma_v4_root: Path,
    medsiglip_v5_root: Path,
    localizer_v10_root: Path,
    output_dir: Path,
    expected_case_count: int = 87,
    excluded_case_id: str = EXCLUDED_TECHNICAL_CASE,
) -> dict[str, Any]:
    """Build an atomic, label-free signal bundle for the v11 hypothesis."""
    localizer_summary, localizer = _validate_blind_localizer_run(localizer_v10_root, expected_case_count)
    case_ids = list(localizer_summary["case_ids"])
    expected_ids = set(case_ids)
    if excluded_case_id in expected_ids:
        raise PipelineError("A exclusao tecnica pre-declarada ainda aparece na coorte v11.")
    v4, v4_hashes = _load_v4(medgemma_v4_root, expected_ids=expected_ids, excluded_case_id=excluded_case_id)
    v5, v5_hashes = _load_v5(medsiglip_v5_root, expected_ids=expected_ids, excluded_case_id=excluded_case_id)
    rows = []
    for case_id in case_ids:
        if v4[case_id]["panel_sha256"] != v5[case_id]["panel_sha256"] or len(v4[case_id]["panel_sha256"]) != 64:
            raise PipelineError(f"Painel de origem v4/v5 divergiu: {case_id}.")
        rows.append({
            "schema": BLIND_SIGNAL_SCHEMA,
            "case_id": case_id,
            "signals": {
                "medgemma_v4_uncertainty_margin": v4[case_id]["value"],
                "medsiglip_v5_inverse_sagittal": v5[case_id]["value"],
                "localizer_v10_log_volume": localizer[case_id],
            },
            "ground_truth_read": False,
            "metrics_calculated": False,
            "final_decision": None,
            "research_only": True,
            "clinical_use_allowed": False,
            "requires_human_review": True,
        })
    observed_maxima = {
        "medgemma_v4_seconds": max(item["elapsed_seconds"] for item in v4.values()),
        "medsiglip_v5_seconds": max(item["elapsed_seconds"] for item in v5.values()),
        "localizer_v10_seconds": _finite(localizer_summary.get("max_case_seconds"), minimum=0.0),
    }
    conservative_seconds = sum(observed_maxima.values())
    if conservative_seconds > 180.0:
        raise PipelineError("Hipotese v11 excede o teto conservador de 180 segundos.")
    output = Path(output_dir).resolve()
    if output.exists():
        raise PipelineError("Bundle cego v11 ja existe.")
    output.parent.mkdir(parents=True, exist_ok=True)
    staging = output.parent / f"._v11blind_{uuid.uuid4().hex[:8]}"
    staging.mkdir()
    try:
        signals_path = staging / "signals.jsonl"
        signals_path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")
        summary = {
            "schema": BLIND_BUNDLE_SCHEMA,
            "status": "complete_blind_signals_no_decision",
            "case_count": expected_case_count,
            "case_ids": case_ids,
            "excluded_technical_case_id": excluded_case_id,
            "signals": list(WEIGHTS),
            "signals_sha256": _sha256(signals_path),
            "source_hashes": {
                "medgemma_v4": v4_hashes,
                "medsiglip_v5": v5_hashes,
                "localizer_v10_summary_sha256": _sha256(Path(localizer_v10_root).resolve() / "summary.json"),
            },
            "observed_component_max_seconds": observed_maxima,
            "conservative_sum_of_component_max_seconds": conservative_seconds,
            "time_gate_180_seconds_passed": True,
            "ground_truth_read": False,
            "metrics_calculated": False,
            "final_decision": None,
            "holdout_opened": False,
            "research_only": True,
            "clinical_use_allowed": False,
            "requires_human_review": True,
        }
        _write_json_atomic(staging / "summary.json", summary)
        _publish_directory(staging, output)
        return summary
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def _validate_blind_bundle(bundle_root: Path, expected_case_count: int) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    root = Path(bundle_root).resolve()
    summary = _load_json(root / "summary.json")
    signals_path = root / "signals.jsonl"
    rows = _load_jsonl(signals_path)
    if (
        not isinstance(summary, dict)
        or summary.get("schema") != BLIND_BUNDLE_SCHEMA
        or summary.get("status") != "complete_blind_signals_no_decision"
        or summary.get("case_count") != expected_case_count
        or summary.get("signals") != list(WEIGHTS)
        or summary.get("signals_sha256") != _sha256(signals_path)
        or summary.get("time_gate_180_seconds_passed") is not True
        or summary.get("ground_truth_read") is not False
        or summary.get("metrics_calculated") is not False
        or summary.get("final_decision") is not None
        or summary.get("holdout_opened") is not False
        or summary.get("research_only") is not True
        or summary.get("clinical_use_allowed") is not False
        or len(rows) != expected_case_count
    ):
        raise PipelineError("Bundle cego v11 invalido ou adulterado.")
    case_ids = summary.get("case_ids")
    if not isinstance(case_ids, list) or len(case_ids) != len(set(case_ids)) or [row.get("case_id") for row in rows] != case_ids:
        raise PipelineError("Ordem ou identificadores do bundle v11 divergiram.")
    for row in rows:
        values = row.get("signals")
        if (
            row.get("schema") != BLIND_SIGNAL_SCHEMA
            or not isinstance(values, dict)
            or list(values) != list(WEIGHTS)
            or row.get("ground_truth_read") is not False
            or row.get("metrics_calculated") is not False
            or row.get("final_decision") is not None
            or row.get("research_only") is not True
            or row.get("clinical_use_allowed") is not False
            or "label" in row
        ):
            raise PipelineError(f"Registro cego v11 invalido: {row.get('case_id')}.")
        for value in values.values():
            _finite(value)
    return summary, rows


def create_fusion_protocol(*, bundle_root: Path, output_path: Path, expected_case_count: int = 87) -> dict[str, Any]:
    summary, rows = _validate_blind_bundle(bundle_root, expected_case_count)
    output = Path(output_path).resolve()
    if output.exists():
        raise PipelineError("Protocolo v11 ja existe.")
    feature_vector = [[row["case_id"], *[row["signals"][name] for name in WEIGHTS]] for row in rows]
    payload = {
        "schema": PROTOCOL_SCHEMA,
        "status": "frozen_before_protected_labels",
        "case_count": expected_case_count,
        "case_ids": summary["case_ids"],
        "blind_bundle_summary_sha256": _sha256(Path(bundle_root).resolve() / "summary.json"),
        "blind_signals_sha256": summary["signals_sha256"],
        "primary_feature": "v11_fold_local_weighted_ecdf_fusion",
        "components": WEIGHTS,
        "component_directions": {name: "higher_is_positive" for name in WEIGHTS},
        "transform": "training_only_empirical_cdf_midrank_n_denominator",
        "fusion": "weighted_arithmetic_mean",
        "threshold_selection": "maximize_minimum_sensitivity_specificity_then_balanced_accuracy_on_training_only",
        "primary_estimator": "leave_one_out_with_transform_and_threshold_fit_on_training_only",
        "robustness_estimator": "repeated_stratified_5fold_50_repeats_seed_20260716_fully_nested",
        "confidence_intervals": "wilson_95_percent_on_loocv_confusion_matrix",
        "development_gate": {
            "minimum_loocv_sensitivity": 0.75,
            "minimum_loocv_specificity": 0.75,
            "required_repeated_runs_passing_75_75": 50,
        },
        "time_gate_seconds": 180.0,
        "observed_conservative_seconds": summary["conservative_sum_of_component_max_seconds"],
        "raw_feature_vector_sha256": _canonical_sha(feature_vector),
        "single_predeclared_primary_fusion": True,
        "ground_truth_read": False,
        "metrics_calculated": False,
        "holdout_opened": False,
        "research_only": True,
        "clinical_use_allowed": False,
        "requires_human_review": True,
    }
    payload["protocol_signature"] = _canonical_sha(payload)
    output.parent.mkdir(parents=True, exist_ok=True)
    _write_json_atomic(output, payload)
    return payload


def verify_fusion_protocol(*, bundle_root: Path, protocol_path: Path, expected_case_count: int = 87) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    summary, rows = _validate_blind_bundle(bundle_root, expected_case_count)
    protocol = _load_json(protocol_path)
    signed = {key: value for key, value in protocol.items() if key != "protocol_signature"} if isinstance(protocol, dict) else {}
    feature_vector = [[row["case_id"], *[row["signals"][name] for name in WEIGHTS]] for row in rows]
    if (
        not isinstance(protocol, dict)
        or protocol.get("schema") != PROTOCOL_SCHEMA
        or protocol.get("status") != "frozen_before_protected_labels"
        or protocol.get("protocol_signature") != _canonical_sha(signed)
        or protocol.get("case_count") != expected_case_count
        or protocol.get("case_ids") != summary["case_ids"]
        or protocol.get("blind_bundle_summary_sha256") != _sha256(Path(bundle_root).resolve() / "summary.json")
        or protocol.get("blind_signals_sha256") != summary["signals_sha256"]
        or protocol.get("components") != WEIGHTS
        or protocol.get("raw_feature_vector_sha256") != _canonical_sha(feature_vector)
        or protocol.get("single_predeclared_primary_fusion") is not True
        or protocol.get("ground_truth_read") is not False
        or protocol.get("metrics_calculated") is not False
        or protocol.get("holdout_opened") is not False
    ):
        raise PipelineError("Protocolo v11 invalido ou divergente do bundle cego.")
    return protocol, rows


def _ecdf(value: float, reference: list[float]) -> float:
    if not reference:
        raise PipelineError("Referencia ECDF v11 vazia.")
    lower = sum(item < value for item in reference)
    equal = sum(item == value for item in reference)
    return (lower + 0.5 * equal) / len(reference)


def _fold_scores(rows: list[dict[str, Any]], train_indices: list[int], score_indices: list[int]) -> list[float]:
    references = {
        name: [float(rows[index]["signals"][name]) for index in train_indices]
        for name in WEIGHTS
    }
    return [
        sum(WEIGHTS[name] * _ecdf(float(rows[index]["signals"][name]), references[name]) for name in WEIGHTS)
        for index in score_indices
    ]


def _loocv_fusion(rows: list[dict[str, Any]], truth: list[bool]) -> dict[str, Any]:
    predicted: list[bool] = []
    thresholds: list[float] = []
    scores: list[float] = []
    for test_index in range(len(rows)):
        train = [index for index in range(len(rows)) if index != test_index]
        train_truth = [truth[index] for index in train]
        train_scores = _fold_scores(rows, train, train)
        threshold, _ = _best_threshold(train_scores, train_truth)
        score = _fold_scores(rows, train, [test_index])[0]
        predicted.append(score >= threshold)
        thresholds.append(threshold)
        scores.append(score)
    return {**_binary_metrics(truth, predicted), "thresholds": thresholds, "scores": scores}


def _repeated_nested_fusion(rows: list[dict[str, Any]], truth: list[bool], *, repeats: int = 50, folds: int = 5) -> dict[str, Any]:
    positive = [index for index, value in enumerate(truth) if value]
    negative = [index for index, value in enumerate(truth) if not value]
    if min(len(positive), len(negative)) < folds:
        raise PipelineError("Coorte insuficiente para validacao estratificada v11.")
    outcomes = []
    for repeat in range(repeats):
        rng = random.Random(20260716 + repeat)
        pos, neg = positive[:], negative[:]
        rng.shuffle(pos)
        rng.shuffle(neg)
        groups = [[] for _ in range(folds)]
        for index, item in enumerate(pos):
            groups[index % folds].append(item)
        for index, item in enumerate(neg):
            groups[index % folds].append(item)
        predicted = [False] * len(rows)
        for test_indices in groups:
            test = set(test_indices)
            train = [index for index in range(len(rows)) if index not in test]
            train_scores = _fold_scores(rows, train, train)
            threshold, _ = _best_threshold(train_scores, [truth[index] for index in train])
            for index, score in zip(test_indices, _fold_scores(rows, train, test_indices), strict=True):
                predicted[index] = score >= threshold
        outcomes.append(_binary_metrics(truth, predicted))
    return {
        "repeats": repeats,
        "folds": folds,
        "transform_and_threshold_fit_inside_each_training_fold": True,
        "runs_passing_75_75": sum(item["passed_75_75"] for item in outcomes),
        "median_sensitivity": statistics.median(item["sensitivity"] for item in outcomes),
        "median_specificity": statistics.median(item["specificity"] for item in outcomes),
        "minimum_sensitivity": min(item["sensitivity"] for item in outcomes),
        "minimum_specificity": min(item["specificity"] for item in outcomes),
    }


def evaluate_fusion_development(
    *, bundle_root: Path, protocol_path: Path, labels_path: Path, output_dir: Path,
    allow_protected_development_labels: bool = False, expected_case_count: int = 87,
) -> dict[str, Any]:
    """Evaluate v11 only after a new, explicit protected-label authorization."""
    protocol, rows = verify_fusion_protocol(
        bundle_root=bundle_root, protocol_path=protocol_path, expected_case_count=expected_case_count
    )
    if allow_protected_development_labels is not True:
        raise PipelineError("Abertura dos labels protegidos para a v11 nao foi autorizada explicitamente.")
    output = Path(output_dir).resolve()
    if output.exists():
        raise PipelineError("Avaliacao v11 ja existe.")
    case_ids = [str(row["case_id"]) for row in rows]
    labels, labels_hash = _load_development_labels(labels_path, case_ids)
    truth = [labels[case_id]["label"] == "POSITIVE" for case_id in case_ids]
    if min(sum(truth), len(truth) - sum(truth)) < 5:
        raise PipelineError("Coorte de desenvolvimento v11 invalida.")
    all_indices = list(range(len(rows)))
    apparent_scores = _fold_scores(rows, all_indices, all_indices)
    apparent_threshold, apparent = _best_threshold(apparent_scores, truth)
    loocv = _loocv_fusion(rows, truth)
    repeated = _repeated_nested_fusion(rows, truth)
    development_gate = bool(
        loocv["sensitivity"] >= 0.75
        and loocv["specificity"] >= 0.75
        and repeated["runs_passing_75_75"] == 50
    )
    result = {
        "schema": EVALUATION_SCHEMA,
        "status": "development_gate_passed_holdout_still_closed" if development_gate else "development_only_not_qualified",
        "case_count": len(rows),
        "positive_count": sum(truth),
        "negative_count": len(truth) - sum(truth),
        "primary_feature": protocol["primary_feature"],
        "components": WEIGHTS,
        "apparent_threshold_for_future_calibrator_freeze": apparent_threshold,
        "apparent_metrics": apparent,
        "primary_loocv_metrics": {key: value for key, value in loocv.items() if key != "scores"},
        "repeated_stratified_5fold": repeated,
        "loocv_confidence_intervals": {
            "sensitivity_95": _wilson(loocv["tp"], loocv["tp"] + loocv["fn"]),
            "specificity_95": _wilson(loocv["tn"], loocv["tn"] + loocv["fp"]),
        },
        "development_gate_passed": development_gate,
        "time_gate_180_seconds_passed": protocol["observed_conservative_seconds"] <= 180.0,
        "protocol_signature": protocol["protocol_signature"],
        "protected_development_labels_sha256": labels_hash,
        "holdout_opened": False,
        "qualified": False,
        "ground_truth_read": True,
        "metrics_calculated": True,
        "research_only": True,
        "clinical_use_allowed": False,
        "requires_human_review": True,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    staging = output.parent / f"._v11eval_{uuid.uuid4().hex[:8]}"
    staging.mkdir()
    try:
        _write_json_atomic(staging / "evaluation.json", result)
        with (staging / "case_features.csv").open("w", encoding="utf-8", newline="") as handle:
            fields = ["case_id", "label", *WEIGHTS, "full_development_ecdf_fusion"]
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            for index, row in enumerate(rows):
                writer.writerow({
                    "case_id": row["case_id"],
                    "label": labels[row["case_id"]]["label"],
                    **row["signals"],
                    "full_development_ecdf_fusion": apparent_scores[index],
                })
        _publish_directory(staging, output)
        return result
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
