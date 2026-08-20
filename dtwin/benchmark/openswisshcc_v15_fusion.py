"""Blind v15 fusion and protected OpenSwissHCC development evaluation.

The primary hypothesis is declared before protected labels are opened. It gives
equal reader-level weight to the already frozen v11 fusion and the v15 native
volumetric score. All ECDF transforms and thresholds are fitted on training
folds only.
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
)
from dtwin.benchmark.openswisshcc_localizer_roi_evaluation import _wilson
from dtwin.benchmark.openswisshcc_v11_fusion import (
    WEIGHTS as V11_WEIGHTS,
)
from dtwin.benchmark.openswisshcc_v11_fusion import (
    verify_fusion_protocol as verify_v11_fusion_protocol,
)
from dtwin.benchmark.openswisshcc_volume_score import (
    CHOICES,
    PREDICTION_SCHEMA,
    PROGRESS_SCHEMA,
)
from dtwin.benchmark.openswisshcc_volume_score import (
    SUMMARY_SCHEMA as VOLUME_SUMMARY_SCHEMA,
)
from dtwin.benchmark.openswisshcc_volume_score import (
    _load_protocol as _load_volume_protocol,
)
from dtwin.benchmark.openswisshcc_volumetric_evaluation import (
    _best_threshold,
    _binary_metrics,
)
from dtwin.core import PipelineError
from dtwin.medgemma_screening import _write_json_atomic

BLIND_BUNDLE_SCHEMA = "argos-openswisshcc-v15-blind-fusion-bundle-v1"
BLIND_SIGNAL_SCHEMA = "argos-openswisshcc-v15-blind-fusion-signal-v1"
PROTOCOL_SCHEMA = "argos-openswisshcc-v15-fusion-protocol-v1"
EVALUATION_SCHEMA = "argos-openswisshcc-v15-development-evaluation-v1"
V15_SIGNAL = "v15_volume_positive_negative_log_odds"
PRIMARY_READERS = {
    "v11_fold_local_weighted_ecdf": 0.5,
    "v15_volume_log_odds_fold_local_ecdf": 0.5,
}
LOG_ODDS_EPSILON = 1e-8
REPEATS = 50
FOLDS = 5
RANDOM_SEED = 20260716
TIME_GATE_SECONDS = 180.0
FORBIDDEN_BLIND_KEYS = {
    "label",
    "ground_truth",
    "expected",
    "negative_subtype",
    "positive_subtype",
    "phenotype_tags",
    "target_condition",
}


def _load_json(path: Path, description: str) -> dict[str, Any]:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PipelineError(f"{description} ausente ou invalido.") from exc
    if not isinstance(value, dict):
        raise PipelineError(f"{description} deve ser um objeto JSON.")
    return value


def _load_jsonl(path: Path, description: str) -> list[dict[str, Any]]:
    try:
        rows = [
            json.loads(line)
            for line in Path(path).read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    except (OSError, json.JSONDecodeError) as exc:
        raise PipelineError(f"{description} ausente ou invalido.") from exc
    if not all(isinstance(row, dict) for row in rows):
        raise PipelineError(f"{description} contem registro invalido.")
    return rows


def _canonical_sha(value: Any) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _finite(value: Any, *, minimum: float | None = None, maximum: float | None = None) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise PipelineError("Sinal v15 deve ser numerico.")
    result = float(value)
    if not math.isfinite(result):
        raise PipelineError("Sinal v15 deve ser finito.")
    if minimum is not None and result < minimum:
        raise PipelineError("Sinal v15 abaixo do minimo permitido.")
    if maximum is not None and result > maximum:
        raise PipelineError("Sinal v15 acima do maximo permitido.")
    return result


def _contains_forbidden_key(value: Any) -> bool:
    if isinstance(value, dict):
        if any(str(key).lower() in FORBIDDEN_BLIND_KEYS for key in value):
            return True
        return any(_contains_forbidden_key(item) for item in value.values())
    if isinstance(value, list):
        return any(_contains_forbidden_key(item) for item in value)
    return False


def _validate_volume_score_run(
    *, run_root: Path, protocol_path: Path, expected_case_count: int
) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    """Validate every persisted v15 score without reading protected labels."""

    root = Path(run_root).resolve()
    protocol = _load_volume_protocol(protocol_path)
    progress_path = root / "progress.json"
    summary_path = root / "summary.json"
    progress = _load_json(progress_path, "Progresso cego v15")
    summary = _load_json(summary_path, "Resumo cego v15")
    if (
        progress.get("schema") != PROGRESS_SCHEMA
        or progress.get("status") != "complete"
        or progress.get("case_count") != expected_case_count
        or progress.get("completed_case_count") != expected_case_count
        or progress.get("pending_case_count") != 0
        or progress.get("protocol_signature") != protocol["protocol_signature"]
        or summary.get("schema") != VOLUME_SUMMARY_SCHEMA
        or summary.get("status") != "blind_scores_complete"
        or summary.get("case_count") != expected_case_count
        or summary.get("protocol_signature") != protocol["protocol_signature"]
        or summary.get("progress_sha256") != _sha256(progress_path)
        or summary.get("all_time_gates_passed") is not True
    ):
        raise PipelineError("Execucao cega v15 incompleta ou divergente do protocolo.")
    for payload in (progress, summary):
        if (
            payload.get("ground_truth_read") is not False
            or payload.get("metrics_calculated") is not False
            or payload.get("holdout_opened") is not False
            or payload.get("research_only") is not True
            or payload.get("clinical_use_allowed") is not False
            or payload.get("requires_human_review") is not True
            or _contains_forbidden_key(payload)
        ):
            raise PipelineError("Execucao v15 violou cegamento ou salvaguardas.")
    records = progress.get("predictions")
    if not isinstance(records, list) or len(records) != expected_case_count:
        raise PipelineError("Indice de predicoes v15 incompleto.")
    predictions: list[dict[str, Any]] = []
    seen: set[str] = set()
    for record in records:
        case_id = str(record.get("case_id", ""))
        path = root / "predictions" / f"{case_id}.json"
        if not case_id or case_id in seen or record.get("prediction_sha256") != _sha256(path):
            raise PipelineError("Indice de predicoes v15 duplicado ou com hash divergente.")
        prediction = _load_json(path, f"Predicao v15 {case_id}")
        probabilities = prediction.get("choice_probabilities")
        if (
            prediction.get("schema") != PREDICTION_SCHEMA
            or prediction.get("status") != "technical_passed"
            or prediction.get("case_id") != case_id
            or prediction.get("protocol_signature") != protocol["protocol_signature"]
            or prediction.get("time_gate_passed") is not True
            or prediction.get("classification") not in CHOICES
            or not isinstance(probabilities, dict)
            or set(probabilities) != set(CHOICES)
            or prediction.get("ground_truth_read") is not False
            or prediction.get("metrics_calculated") is not False
            or prediction.get("holdout_opened") is not False
            or prediction.get("research_only") is not True
            or prediction.get("clinical_use_allowed") is not False
            or prediction.get("requires_human_review") is not True
            or _contains_forbidden_key(prediction)
        ):
            raise PipelineError(f"Predicao cega v15 invalida: {case_id}.")
        values = {name: _finite(probabilities[name], minimum=0.0, maximum=1.0) for name in CHOICES}
        if abs(sum(values.values()) - 1.0) > 1e-6:
            raise PipelineError(f"Probabilidades v15 nao somam um: {case_id}.")
        expected_class = max(CHOICES, key=lambda name: values[name])
        elapsed = _finite(prediction.get("request_elapsed_seconds"), minimum=0.0)
        if prediction["classification"] != expected_class or elapsed > TIME_GATE_SECONDS:
            raise PipelineError(f"Classe ou tempo v15 divergente: {case_id}.")
        seen.add(case_id)
        predictions.append(prediction)
    if seen != set(protocol.get("case_ids", [])):
        raise PipelineError("Casos v15 nao correspondem ao protocolo congelado.")
    return protocol, summary, predictions


def build_blind_fusion_bundle(
    *,
    v11_bundle_root: Path,
    v11_protocol_path: Path,
    v15_run_root: Path,
    v15_protocol_path: Path,
    output_root: Path,
    expected_case_count: int = 87,
) -> dict[str, Any]:
    """Join v11 and v15 blind signals without labels, decisions, or metrics."""

    v11_protocol, v11_rows = verify_v11_fusion_protocol(
        bundle_root=v11_bundle_root,
        protocol_path=v11_protocol_path,
        expected_case_count=expected_case_count,
    )
    v15_protocol, v15_summary, predictions = _validate_volume_score_run(
        run_root=v15_run_root,
        protocol_path=v15_protocol_path,
        expected_case_count=expected_case_count,
    )
    v11_by_id = {str(row["case_id"]): row for row in v11_rows}
    v15_by_id = {str(row["case_id"]): row for row in predictions}
    case_ids = sorted(v11_by_id)
    if set(case_ids) != set(v15_by_id):
        raise PipelineError("Coortes cegas v11 e v15 nao correspondem.")
    rows: list[dict[str, Any]] = []
    for case_id in case_ids:
        probabilities = v15_by_id[case_id]["choice_probabilities"]
        positive = float(probabilities["POSITIVA"])
        negative = float(probabilities["NEGATIVA"])
        log_odds = math.log((positive + LOG_ODDS_EPSILON) / (negative + LOG_ODDS_EPSILON))
        row = {
            "schema": BLIND_SIGNAL_SCHEMA,
            "case_id": case_id,
            "signals": {
                **{name: float(v11_by_id[case_id]["signals"][name]) for name in V11_WEIGHTS},
                V15_SIGNAL: log_odds,
            },
            "v15_choice_probabilities": {name: float(probabilities[name]) for name in CHOICES},
            "v15_raw_classification": v15_by_id[case_id]["classification"],
            "v15_prediction_sha256": _sha256(
                Path(v15_run_root).resolve() / "predictions" / f"{case_id}.json"
            ),
            "ground_truth_read": False,
            "metrics_calculated": False,
            "holdout_opened": False,
            "research_only": True,
            "clinical_use_allowed": False,
            "requires_human_review": True,
        }
        if _contains_forbidden_key(row):
            raise PipelineError("Bundle combinado v15 contem campo protegido.")
        rows.append(row)
    output = Path(output_root).resolve()
    if output.exists():
        raise PipelineError("Bundle combinado v15 ja existe.")
    output.parent.mkdir(parents=True, exist_ok=True)
    staging = output.parent / f"._v15bundle_{uuid.uuid4().hex[:8]}"
    staging.mkdir()
    try:
        signals_path = staging / "signals.jsonl"
        with signals_path.open("w", encoding="utf-8", newline="\n") as handle:
            for row in rows:
                handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
        conservative_seconds = float(v11_protocol["observed_conservative_seconds"]) + float(
            v15_summary["request_seconds_max"]
        )
        summary = {
            "schema": BLIND_BUNDLE_SCHEMA,
            "status": "complete_blind_signals_no_decision",
            "case_count": expected_case_count,
            "case_ids": case_ids,
            "signals": [*V11_WEIGHTS, V15_SIGNAL],
            "signals_sha256": _sha256(signals_path),
            "source_hashes": {
                "v11_bundle_summary_sha256": _sha256(Path(v11_bundle_root).resolve() / "summary.json"),
                "v11_protocol_sha256": _sha256(Path(v11_protocol_path).resolve()),
                "v15_progress_sha256": _sha256(Path(v15_run_root).resolve() / "progress.json"),
                "v15_summary_sha256": _sha256(Path(v15_run_root).resolve() / "summary.json"),
                "v15_protocol_sha256": _sha256(Path(v15_protocol_path).resolve()),
            },
            "v11_protocol_signature": v11_protocol["protocol_signature"],
            "v15_protocol_signature": v15_protocol["protocol_signature"],
            "log_odds_epsilon": LOG_ODDS_EPSILON,
            "v11_conservative_seconds": v11_protocol["observed_conservative_seconds"],
            "v15_observed_max_seconds": v15_summary["request_seconds_max"],
            "combined_conservative_seconds": conservative_seconds,
            "time_gate_180_seconds_passed": conservative_seconds <= TIME_GATE_SECONDS,
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


def _validate_blind_bundle(
    bundle_root: Path, expected_case_count: int
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    root = Path(bundle_root).resolve()
    summary = _load_json(root / "summary.json", "Resumo do bundle combinado v15")
    rows = _load_jsonl(root / "signals.jsonl", "Sinais do bundle combinado v15")
    if (
        summary.get("schema") != BLIND_BUNDLE_SCHEMA
        or summary.get("status") != "complete_blind_signals_no_decision"
        or summary.get("case_count") != expected_case_count
        or len(rows) != expected_case_count
        or summary.get("signals_sha256") != _sha256(root / "signals.jsonl")
        or summary.get("signals") != [*V11_WEIGHTS, V15_SIGNAL]
        or summary.get("time_gate_180_seconds_passed") is not True
        or summary.get("combined_conservative_seconds", TIME_GATE_SECONDS + 1) > TIME_GATE_SECONDS
        or summary.get("ground_truth_read") is not False
        or summary.get("metrics_calculated") is not False
        or summary.get("final_decision") is not None
        or summary.get("holdout_opened") is not False
        or summary.get("research_only") is not True
        or summary.get("clinical_use_allowed") is not False
        or summary.get("requires_human_review") is not True
        or _contains_forbidden_key(summary)
    ):
        raise PipelineError("Bundle combinado v15 invalido ou nao cego.")
    case_ids: list[str] = []
    expected_signals = {*V11_WEIGHTS, V15_SIGNAL}
    for row in rows:
        case_id = str(row.get("case_id", ""))
        signals = row.get("signals")
        probabilities = row.get("v15_choice_probabilities")
        if (
            row.get("schema") != BLIND_SIGNAL_SCHEMA
            or not case_id
            or not isinstance(signals, dict)
            or set(signals) != expected_signals
            or not isinstance(probabilities, dict)
            or set(probabilities) != set(CHOICES)
            or row.get("v15_raw_classification") not in CHOICES
            or row.get("ground_truth_read") is not False
            or row.get("metrics_calculated") is not False
            or row.get("holdout_opened") is not False
            or row.get("research_only") is not True
            or row.get("clinical_use_allowed") is not False
            or row.get("requires_human_review") is not True
            or _contains_forbidden_key(row)
        ):
            raise PipelineError(f"Registro combinado v15 invalido: {case_id}.")
        for value in signals.values():
            _finite(value)
        for value in probabilities.values():
            _finite(value, minimum=0.0, maximum=1.0)
        if abs(sum(float(value) for value in probabilities.values()) - 1.0) > 1e-6:
            raise PipelineError(f"Probabilidades combinadas v15 invalidas: {case_id}.")
        case_ids.append(case_id)
    if len(set(case_ids)) != expected_case_count or case_ids != summary.get("case_ids"):
        raise PipelineError("IDs do bundle combinado v15 duplicados ou fora de ordem.")
    return summary, rows


def create_fusion_protocol(
    *, bundle_root: Path, output_path: Path, expected_case_count: int = 87
) -> dict[str, Any]:
    summary, rows = _validate_blind_bundle(bundle_root, expected_case_count)
    output = Path(output_path).resolve()
    if output.exists():
        raise PipelineError("Protocolo de avaliacao v15 ja existe.")
    raw_vector = [
        [row["case_id"], *[row["signals"][name] for name in V11_WEIGHTS], row["signals"][V15_SIGNAL]]
        for row in rows
    ]
    payload = {
        "schema": PROTOCOL_SCHEMA,
        "status": "frozen_before_protected_labels",
        "case_count": expected_case_count,
        "case_ids": summary["case_ids"],
        "blind_bundle_summary_sha256": _sha256(Path(bundle_root).resolve() / "summary.json"),
        "blind_signals_sha256": summary["signals_sha256"],
        "raw_feature_vector_sha256": _canonical_sha(raw_vector),
        "single_predeclared_primary_fusion": True,
        "primary_feature": "equal_reader_weight_v11_v15_fold_local_ecdf_fusion",
        "primary_readers": PRIMARY_READERS,
        "v11_components": V11_WEIGHTS,
        "v15_signal": V15_SIGNAL,
        "component_directions": "higher_is_positive",
        "transform": "training_only_empirical_cdf_midrank_n_denominator",
        "fusion": "weighted_arithmetic_mean",
        "threshold_selection": "maximize_minimum_sensitivity_specificity_then_balanced_accuracy_on_training_only",
        "primary_estimator": "leave_one_out_with_transform_and_threshold_fit_on_training_only",
        "robustness_estimator": f"repeated_stratified_{FOLDS}fold_{REPEATS}_repeats_seed_{RANDOM_SEED}_fully_nested",
        "secondary_diagnostics": [
            "v11_only_nested_loocv_not_eligible_for_model_selection",
            "v15_only_nested_loocv_not_eligible_for_model_selection",
            "v15_raw_categorical_with_inconclusive_counted_as_error",
        ],
        "secondary_diagnostics_cannot_replace_primary": True,
        "confidence_intervals": "wilson_95_percent_on_primary_loocv_confusion_matrix",
        "development_gate": {
            "minimum_loocv_sensitivity": 0.75,
            "minimum_loocv_specificity": 0.75,
            "required_repeated_runs_passing_75_75": REPEATS,
            "inconclusive_is_error_for_raw_categorical_diagnostic": True,
        },
        "time_gate_seconds": TIME_GATE_SECONDS,
        "observed_conservative_seconds": summary["combined_conservative_seconds"],
        "source_hashes": summary["source_hashes"],
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


def verify_fusion_protocol(
    *, bundle_root: Path, protocol_path: Path, expected_case_count: int = 87
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    summary, rows = _validate_blind_bundle(bundle_root, expected_case_count)
    protocol = _load_json(protocol_path, "Protocolo de avaliacao v15")
    signed = {key: value for key, value in protocol.items() if key != "protocol_signature"}
    raw_vector = [
        [row["case_id"], *[row["signals"][name] for name in V11_WEIGHTS], row["signals"][V15_SIGNAL]]
        for row in rows
    ]
    if (
        protocol.get("schema") != PROTOCOL_SCHEMA
        or protocol.get("status") != "frozen_before_protected_labels"
        or protocol.get("protocol_signature") != _canonical_sha(signed)
        or protocol.get("case_count") != expected_case_count
        or protocol.get("case_ids") != summary["case_ids"]
        or protocol.get("blind_bundle_summary_sha256") != _sha256(Path(bundle_root).resolve() / "summary.json")
        or protocol.get("blind_signals_sha256") != summary["signals_sha256"]
        or protocol.get("raw_feature_vector_sha256") != _canonical_sha(raw_vector)
        or protocol.get("single_predeclared_primary_fusion") is not True
        or protocol.get("primary_readers") != PRIMARY_READERS
        or protocol.get("v11_components") != V11_WEIGHTS
        or protocol.get("v15_signal") != V15_SIGNAL
        or protocol.get("secondary_diagnostics_cannot_replace_primary") is not True
        or protocol.get("ground_truth_read") is not False
        or protocol.get("metrics_calculated") is not False
        or protocol.get("holdout_opened") is not False
    ):
        raise PipelineError("Protocolo v15 invalido ou divergente do bundle cego.")
    return protocol, rows


def _ecdf(value: float, reference: list[float]) -> float:
    if not reference:
        raise PipelineError("Referencia ECDF v15 vazia.")
    lower = sum(item < value for item in reference)
    equal = sum(item == value for item in reference)
    return (lower + 0.5 * equal) / len(reference)


def _fold_scores(
    rows: list[dict[str, Any]], train_indices: list[int], score_indices: list[int], *, mode: str
) -> list[float]:
    if mode not in {"primary", "v11", "v15"}:
        raise PipelineError("Modo de score v15 invalido.")
    references = {
        name: [float(rows[index]["signals"][name]) for index in train_indices]
        for name in [*V11_WEIGHTS, V15_SIGNAL]
    }
    scores: list[float] = []
    for index in score_indices:
        v11 = sum(
            V11_WEIGHTS[name]
            * _ecdf(float(rows[index]["signals"][name]), references[name])
            for name in V11_WEIGHTS
        )
        v15 = _ecdf(float(rows[index]["signals"][V15_SIGNAL]), references[V15_SIGNAL])
        if mode == "v11":
            scores.append(v11)
        elif mode == "v15":
            scores.append(v15)
        else:
            scores.append(
                PRIMARY_READERS["v11_fold_local_weighted_ecdf"] * v11
                + PRIMARY_READERS["v15_volume_log_odds_fold_local_ecdf"] * v15
            )
    return scores


def _loocv(rows: list[dict[str, Any]], truth: list[bool], *, mode: str) -> dict[str, Any]:
    predicted: list[bool] = []
    thresholds: list[float] = []
    scores: list[float] = []
    for test_index in range(len(rows)):
        train = [index for index in range(len(rows)) if index != test_index]
        train_scores = _fold_scores(rows, train, train, mode=mode)
        threshold, _ = _best_threshold(train_scores, [truth[index] for index in train])
        score = _fold_scores(rows, train, [test_index], mode=mode)[0]
        predicted.append(score >= threshold)
        thresholds.append(threshold)
        scores.append(score)
    return {**_binary_metrics(truth, predicted), "thresholds": thresholds, "scores": scores}


def _repeated_nested_primary(
    rows: list[dict[str, Any]], truth: list[bool], *, repeats: int = REPEATS, folds: int = FOLDS
) -> dict[str, Any]:
    positive = [index for index, value in enumerate(truth) if value]
    negative = [index for index, value in enumerate(truth) if not value]
    if min(len(positive), len(negative)) < folds:
        raise PipelineError("Coorte insuficiente para validacao estratificada v15.")
    outcomes: list[dict[str, Any]] = []
    for repeat in range(repeats):
        rng = random.Random(RANDOM_SEED + repeat)
        pos, neg = positive[:], negative[:]
        rng.shuffle(pos)
        rng.shuffle(neg)
        groups: list[list[int]] = [[] for _ in range(folds)]
        for index, item in enumerate(pos):
            groups[index % folds].append(item)
        for index, item in enumerate(neg):
            groups[index % folds].append(item)
        predicted = [False] * len(rows)
        for test_indices in groups:
            test = set(test_indices)
            train = [index for index in range(len(rows)) if index not in test]
            train_scores = _fold_scores(rows, train, train, mode="primary")
            threshold, _ = _best_threshold(train_scores, [truth[index] for index in train])
            test_scores = _fold_scores(rows, train, test_indices, mode="primary")
            for index, score in zip(test_indices, test_scores, strict=True):
                predicted[index] = score >= threshold
        outcomes.append(_binary_metrics(truth, predicted))
    return {
        "repeats": repeats,
        "folds": folds,
        "seed": RANDOM_SEED,
        "transform_and_threshold_fit_inside_each_training_fold": True,
        "runs_passing_75_75": sum(item["passed_75_75"] for item in outcomes),
        "median_sensitivity": statistics.median(item["sensitivity"] for item in outcomes),
        "median_specificity": statistics.median(item["specificity"] for item in outcomes),
        "minimum_sensitivity": min(item["sensitivity"] for item in outcomes),
        "minimum_specificity": min(item["specificity"] for item in outcomes),
    }


def _raw_categorical_metrics(rows: list[dict[str, Any]], truth: list[bool]) -> dict[str, Any]:
    tp = tn = fp = fn = inconclusive = 0
    for row, expected_positive in zip(rows, truth, strict=True):
        classification = row["v15_raw_classification"]
        inconclusive += int(classification == "INCONCLUSIVA")
        if expected_positive:
            tp += int(classification == "POSITIVA")
            fn += int(classification != "POSITIVA")
        else:
            tn += int(classification == "NEGATIVA")
            fp += int(classification != "NEGATIVA")
    sensitivity = tp / (tp + fn) if tp + fn else None
    specificity = tn / (tn + fp) if tn + fp else None
    return {
        "tp": tp,
        "tn": tn,
        "fp": fp,
        "fn": fn,
        "sensitivity": sensitivity,
        "specificity": specificity,
        "inconclusive_count": inconclusive,
        "inconclusive_counted_as_error": True,
        "passed_75_75": bool(sensitivity is not None and specificity is not None and sensitivity >= 0.75 and specificity >= 0.75),
    }


def evaluate_fusion_development(
    *,
    bundle_root: Path,
    protocol_path: Path,
    labels_path: Path,
    output_dir: Path,
    allow_protected_development_labels: bool = False,
    expected_case_count: int = 87,
) -> dict[str, Any]:
    """Evaluate only after a new explicit v15 development-label authorization."""

    protocol, rows = verify_fusion_protocol(
        bundle_root=bundle_root,
        protocol_path=protocol_path,
        expected_case_count=expected_case_count,
    )
    if allow_protected_development_labels is not True:
        raise PipelineError("Abertura dos labels protegidos para a v15 nao foi autorizada explicitamente.")
    output = Path(output_dir).resolve()
    if output.exists():
        raise PipelineError("Avaliacao v15 ja existe.")
    case_ids = [str(row["case_id"]) for row in rows]
    labels, labels_hash = _load_development_labels(labels_path, case_ids)
    truth = [labels[case_id]["label"] == "POSITIVE" for case_id in case_ids]
    if min(sum(truth), len(truth) - sum(truth)) < FOLDS:
        raise PipelineError("Coorte de desenvolvimento v15 invalida.")
    all_indices = list(range(len(rows)))
    apparent_scores = _fold_scores(rows, all_indices, all_indices, mode="primary")
    apparent_threshold, apparent = _best_threshold(apparent_scores, truth)
    primary = _loocv(rows, truth, mode="primary")
    v11_only = _loocv(rows, truth, mode="v11")
    v15_only = _loocv(rows, truth, mode="v15")
    repeated = _repeated_nested_primary(rows, truth)
    raw = _raw_categorical_metrics(rows, truth)
    gate = bool(
        primary["sensitivity"] >= protocol["development_gate"]["minimum_loocv_sensitivity"]
        and primary["specificity"] >= protocol["development_gate"]["minimum_loocv_specificity"]
        and repeated["runs_passing_75_75"]
        == protocol["development_gate"]["required_repeated_runs_passing_75_75"]
        and protocol["observed_conservative_seconds"] <= protocol["time_gate_seconds"]
    )
    result = {
        "schema": EVALUATION_SCHEMA,
        "status": "development_gate_passed_holdout_still_closed" if gate else "development_only_not_qualified",
        "case_count": len(rows),
        "positive_count": sum(truth),
        "negative_count": len(truth) - sum(truth),
        "primary_feature": protocol["primary_feature"],
        "primary_readers": PRIMARY_READERS,
        "apparent_threshold_for_future_calibrator_freeze": apparent_threshold,
        "apparent_metrics": apparent,
        "primary_loocv_metrics": {key: value for key, value in primary.items() if key != "scores"},
        "primary_loocv_confidence_intervals": {
            "sensitivity_95": _wilson(primary["tp"], primary["tp"] + primary["fn"]),
            "specificity_95": _wilson(primary["tn"], primary["tn"] + primary["fp"]),
        },
        "repeated_stratified_5fold": repeated,
        "secondary_diagnostics_not_eligible_for_selection": {
            "v11_only_nested_loocv": {key: value for key, value in v11_only.items() if key != "scores"},
            "v15_only_nested_loocv": {key: value for key, value in v15_only.items() if key != "scores"},
            "v15_raw_categorical": raw,
        },
        "development_gate_passed": gate,
        "time_gate_180_seconds_passed": protocol["observed_conservative_seconds"] <= TIME_GATE_SECONDS,
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
    staging = output.parent / f"._v15eval_{uuid.uuid4().hex[:8]}"
    staging.mkdir()
    try:
        _write_json_atomic(staging / "evaluation.json", result)
        with (staging / "case_features.csv").open("w", encoding="utf-8", newline="") as handle:
            fields = [
                "case_id",
                "label",
                *V11_WEIGHTS,
                V15_SIGNAL,
                "v15_raw_classification",
                "full_development_primary_score",
            ]
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            for index, row in enumerate(rows):
                writer.writerow(
                    {
                        "case_id": row["case_id"],
                        "label": labels[row["case_id"]]["label"],
                        **row["signals"],
                        "v15_raw_classification": row["v15_raw_classification"],
                        "full_development_primary_score": apparent_scores[index],
                    }
                )
        _publish_directory(staging, output)
        return result
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise

