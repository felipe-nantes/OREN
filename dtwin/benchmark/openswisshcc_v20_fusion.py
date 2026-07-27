"""Fusão cega v20 entre o melhor candidato v11 e o leitor RAG v19."""
from __future__ import annotations

import csv
import json
import random
import shutil
import statistics
import uuid
from pathlib import Path
from typing import Any

from dtwin.benchmark.openswisshcc_alignment import _publish_directory, _sha256
from dtwin.benchmark.openswisshcc_axial_atlas_evaluation import (
    _canonical_sha,
    _contains_forbidden_key,
    _finite,
)
from dtwin.benchmark.openswisshcc_axial_atlas_rag_evaluation import (
    validate_blind_scores as validate_v19_scores,
)
from dtwin.benchmark.openswisshcc_lesion_localizer_evaluation import (
    _load_development_labels,
)
from dtwin.benchmark.openswisshcc_localizer_roi_evaluation import _wilson
from dtwin.benchmark.openswisshcc_v11_fusion import (
    WEIGHTS as V11_WEIGHTS,
    verify_fusion_protocol as verify_v11_protocol,
)
from dtwin.benchmark.openswisshcc_volumetric_evaluation import (
    _best_threshold,
    _binary_metrics,
)
from dtwin.core import PipelineError
from dtwin.medgemma_screening import _write_json_atomic


BLIND_BUNDLE_SCHEMA = "argos-openswisshcc-v20-blind-fusion-bundle-v1"
BLIND_SIGNAL_SCHEMA = "argos-openswisshcc-v20-blind-fusion-signal-v1"
PROTOCOL_SCHEMA = "argos-openswisshcc-v20-fusion-protocol-v1"
EVALUATION_SCHEMA = "argos-openswisshcc-v20-development-evaluation-v1"
V19_SIGNAL = "v19_rag_atlas_log_odds"
WEIGHTS = {
    "medgemma_v4_uncertainty_margin": 0.32,
    "medsiglip_v5_inverse_sagittal": 0.32,
    "localizer_v10_log_volume": 0.16,
    V19_SIGNAL: 0.20,
}
REPEATS = 50
FOLDS = 5
RANDOM_SEED = 20260717
TIME_GATE_SECONDS = 180.0


def _load_json(path: Path, description: str) -> dict[str, Any]:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PipelineError(f"{description} ausente ou inválido.") from exc
    if not isinstance(value, dict):
        raise PipelineError(f"{description} deve ser objeto JSON.")
    return value


def _load_jsonl(path: Path, description: str) -> list[dict[str, Any]]:
    try:
        rows = [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]
    except (OSError, json.JSONDecodeError) as exc:
        raise PipelineError(f"{description} ausente ou inválido.") from exc
    if not all(isinstance(row, dict) for row in rows):
        raise PipelineError(f"{description} contém registro inválido.")
    return rows


def build_blind_fusion_bundle(
    *,
    v11_bundle_root: Path,
    v11_protocol_path: Path,
    v19_score_root: Path,
    v19_score_protocol_path: Path,
    output_root: Path,
    expected_case_count: int = 87,
) -> dict[str, Any]:
    v11_protocol, v11_rows = verify_v11_protocol(
        bundle_root=v11_bundle_root,
        protocol_path=v11_protocol_path,
        expected_case_count=expected_case_count,
    )
    v19_summary, v19_rows = validate_v19_scores(
        score_root=v19_score_root,
        score_protocol_path=v19_score_protocol_path,
        expected_case_count=expected_case_count,
    )
    v11_by_id = {str(row["case_id"]): row for row in v11_rows}
    v19_by_id = {str(row["case_id"]): row for row in v19_rows}
    case_ids = [str(row["case_id"]) for row in v11_rows]
    if case_ids != [str(row["case_id"]) for row in v19_rows] or set(v11_by_id) != set(v19_by_id):
        raise PipelineError("Coortes cegas v11 e v19 não correspondem exatamente.")
    rows = []
    for case_id in case_ids:
        row = {
            "schema": BLIND_SIGNAL_SCHEMA,
            "case_id": case_id,
            "signals": {
                **{
                    name: float(v11_by_id[case_id]["signals"][name])
                    for name in V11_WEIGHTS
                },
                V19_SIGNAL: float(v19_by_id[case_id]["score"]),
            },
            "v19_raw_classification": v19_by_id[case_id]["classification"],
            "v19_prediction_sha256": v19_by_id[case_id]["prediction_sha256"],
            "ground_truth_read": False,
            "metrics_calculated": False,
            "final_decision": None,
            "holdout_opened": False,
            "research_only": True,
            "clinical_use_allowed": False,
            "requires_human_review": True,
        }
        if _contains_forbidden_key(row):
            raise PipelineError("Bundle v20 contém campo protegido.")
        rows.append(row)
    conservative_seconds = float(v11_protocol["observed_conservative_seconds"]) + float(
        v19_summary["request_timing_seconds"]["maximum"]
    )
    if conservative_seconds > TIME_GATE_SECONDS:
        raise PipelineError("Fusão v20 excede o teto conservador de 180 segundos.")
    output = Path(output_root).resolve()
    if output.exists():
        raise PipelineError("Bundle cego v20 já existe.")
    output.parent.mkdir(parents=True, exist_ok=True)
    staging = output.parent / f"._v20bundle_{uuid.uuid4().hex[:8]}"
    staging.mkdir()
    try:
        signals_path = staging / "signals.jsonl"
        with signals_path.open("w", encoding="utf-8", newline="\n") as handle:
            for row in rows:
                handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
        summary = {
            "schema": BLIND_BUNDLE_SCHEMA,
            "status": "complete_blind_signals_no_decision",
            "case_count": expected_case_count,
            "case_ids": case_ids,
            "signals": list(WEIGHTS),
            "signals_sha256": _sha256(signals_path),
            "source_hashes": {
                "v11_summary_sha256": _sha256(Path(v11_bundle_root).resolve() / "summary.json"),
                "v11_protocol_sha256": _sha256(Path(v11_protocol_path).resolve()),
                "v19_summary_sha256": _sha256(Path(v19_score_root).resolve() / "summary.json"),
                "v19_protocol_sha256": _sha256(Path(v19_score_protocol_path).resolve()),
            },
            "v11_protocol_signature": v11_protocol["protocol_signature"],
            "v19_protocol_signature": v19_summary["protocol_signature"],
            "v19_rag_context_sha256": v19_summary["rag_context_sha256"],
            "v11_conservative_seconds": v11_protocol["observed_conservative_seconds"],
            "v19_observed_max_seconds": v19_summary["request_timing_seconds"]["maximum"],
            "combined_conservative_seconds": conservative_seconds,
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


def _validate_blind_bundle(
    bundle_root: Path, expected_case_count: int
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    root = Path(bundle_root).resolve()
    summary = _load_json(root / "summary.json", "Resumo cego v20")
    rows = _load_jsonl(root / "signals.jsonl", "Sinais cegos v20")
    if (
        summary.get("schema") != BLIND_BUNDLE_SCHEMA
        or summary.get("status") != "complete_blind_signals_no_decision"
        or summary.get("case_count") != expected_case_count
        or summary.get("signals") != list(WEIGHTS)
        or summary.get("signals_sha256") != _sha256(root / "signals.jsonl")
        or summary.get("time_gate_180_seconds_passed") is not True
        or float(summary.get("combined_conservative_seconds", 181)) > TIME_GATE_SECONDS
        or summary.get("ground_truth_read") is not False
        or summary.get("metrics_calculated") is not False
        or summary.get("final_decision") is not None
        or summary.get("holdout_opened") is not False
        or len(rows) != expected_case_count
        or _contains_forbidden_key(summary)
    ):
        raise PipelineError("Bundle cego v20 inválido ou adulterado.")
    case_ids = summary.get("case_ids")
    if not isinstance(case_ids, list) or [row.get("case_id") for row in rows] != case_ids:
        raise PipelineError("Ordem dos casos v20 diverge.")
    for row in rows:
        signals = row.get("signals")
        if (
            row.get("schema") != BLIND_SIGNAL_SCHEMA
            or not isinstance(signals, dict)
            or set(signals) != set(WEIGHTS)
            or row.get("v19_raw_classification") not in {"POSITIVA", "NEGATIVA", "INCONCLUSIVA"}
            or row.get("ground_truth_read") is not False
            or row.get("metrics_calculated") is not False
            or row.get("final_decision") is not None
            or row.get("holdout_opened") is not False
            or _contains_forbidden_key(row)
        ):
            raise PipelineError(f"Registro cego v20 inválido: {row.get('case_id')}.")
        for value in signals.values():
            _finite(value)
    return summary, rows


def create_fusion_protocol(
    *, bundle_root: Path, output_path: Path, expected_case_count: int = 87
) -> dict[str, Any]:
    summary, rows = _validate_blind_bundle(bundle_root, expected_case_count)
    vector = [[row["case_id"], *[row["signals"][name] for name in WEIGHTS]] for row in rows]
    base = {
        "schema": PROTOCOL_SCHEMA,
        "status": "frozen_before_protected_labels",
        "case_count": expected_case_count,
        "case_ids": summary["case_ids"],
        "blind_bundle_summary_sha256": _sha256(Path(bundle_root).resolve() / "summary.json"),
        "blind_signals_sha256": summary["signals_sha256"],
        "raw_feature_vector_sha256": _canonical_sha(vector),
        "primary_feature": "v20_fold_local_weighted_ecdf_fusion",
        "components": WEIGHTS,
        "weight_rationale": "preserve_v11_component_ratio_at_80_percent_plus_new_v19_reader_at_20_percent",
        "component_directions": {name: "higher_is_positive" for name in WEIGHTS},
        "transform": "training_only_empirical_cdf_midrank_n_denominator",
        "fusion": "weighted_arithmetic_mean",
        "threshold_selection": "maximize_minimum_sensitivity_specificity_then_balanced_accuracy_on_training_only",
        "primary_estimator": "leave_one_out_with_transform_and_threshold_fit_on_training_only",
        "robustness_estimator": "repeated_stratified_5fold_50_repeats_seed_20260717_fully_nested",
        "development_gate": {
            "minimum_loocv_sensitivity": 0.75,
            "minimum_loocv_specificity": 0.75,
            "required_repeated_runs_passing_75_75": 50,
        },
        "time_gate_seconds": TIME_GATE_SECONDS,
        "observed_conservative_seconds": summary["combined_conservative_seconds"],
        "single_predeclared_primary_fusion": True,
        "ground_truth_read": False,
        "metrics_calculated": False,
        "holdout_opened": False,
        "research_only": True,
        "clinical_use_allowed": False,
        "requires_human_review": True,
    }
    protocol = {**base, "protocol_signature": _canonical_sha(base)}
    output = Path(output_path).resolve()
    if output.exists():
        if _load_json(output, "Protocolo v20") != protocol:
            raise PipelineError("Protocolo v20 existente diverge.")
        return protocol
    output.parent.mkdir(parents=True, exist_ok=True)
    _write_json_atomic(output, protocol)
    return protocol


def verify_fusion_protocol(
    *, bundle_root: Path, protocol_path: Path, expected_case_count: int = 87
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    summary, rows = _validate_blind_bundle(bundle_root, expected_case_count)
    protocol = _load_json(protocol_path, "Protocolo v20")
    signature = protocol.pop("protocol_signature", None)
    if signature != _canonical_sha(protocol):
        raise PipelineError("Assinatura do protocolo v20 diverge.")
    protocol["protocol_signature"] = signature
    vector = [[row["case_id"], *[row["signals"][name] for name in WEIGHTS]] for row in rows]
    if (
        protocol.get("schema") != PROTOCOL_SCHEMA
        or protocol.get("status") != "frozen_before_protected_labels"
        or protocol.get("case_ids") != summary["case_ids"]
        or protocol.get("components") != WEIGHTS
        or protocol.get("blind_bundle_summary_sha256")
        != _sha256(Path(bundle_root).resolve() / "summary.json")
        or protocol.get("blind_signals_sha256") != summary["signals_sha256"]
        or protocol.get("raw_feature_vector_sha256") != _canonical_sha(vector)
        or protocol.get("single_predeclared_primary_fusion") is not True
        or protocol.get("ground_truth_read") is not False
        or protocol.get("metrics_calculated") is not False
        or protocol.get("holdout_opened") is not False
    ):
        raise PipelineError("Protocolo v20 não corresponde ao bundle cego.")
    return protocol, rows


def _ecdf(value: float, reference: list[float]) -> float:
    if not reference:
        raise PipelineError("Referência ECDF v20 vazia.")
    lower = sum(item < value for item in reference)
    equal = sum(item == value for item in reference)
    return (lower + 0.5 * equal) / len(reference)


def _fold_scores(
    rows: list[dict[str, Any]], train: list[int], score_indices: list[int], weights: dict[str, float]
) -> list[float]:
    references = {name: [float(rows[index]["signals"][name]) for index in train] for name in weights}
    return [
        sum(weights[name] * _ecdf(float(rows[index]["signals"][name]), references[name]) for name in weights)
        for index in score_indices
    ]


def _loocv(rows: list[dict[str, Any]], truth: list[bool], weights: dict[str, float]) -> dict[str, Any]:
    predicted, thresholds, scores = [], [], []
    for held_out in range(len(rows)):
        train = [index for index in range(len(rows)) if index != held_out]
        threshold, _ = _best_threshold(
            _fold_scores(rows, train, train, weights), [truth[index] for index in train]
        )
        score = _fold_scores(rows, train, [held_out], weights)[0]
        predicted.append(score >= threshold)
        thresholds.append(threshold)
        scores.append(score)
    return {**_binary_metrics(truth, predicted), "thresholds": thresholds, "scores": scores}


def _repeated(rows: list[dict[str, Any]], truth: list[bool]) -> dict[str, Any]:
    positive = [index for index, value in enumerate(truth) if value]
    negative = [index for index, value in enumerate(truth) if not value]
    if min(len(positive), len(negative)) < FOLDS:
        raise PipelineError("Coorte v20 insuficiente para validação estratificada.")
    outcomes = []
    for repeat in range(REPEATS):
        rng = random.Random(RANDOM_SEED + repeat)
        pos, neg = positive[:], negative[:]
        rng.shuffle(pos)
        rng.shuffle(neg)
        groups = [[] for _ in range(FOLDS)]
        for index, item in enumerate(pos):
            groups[index % FOLDS].append(item)
        for index, item in enumerate(neg):
            groups[index % FOLDS].append(item)
        predicted = [False] * len(rows)
        for test_indices in groups:
            test = set(test_indices)
            train = [index for index in range(len(rows)) if index not in test]
            threshold, _ = _best_threshold(
                _fold_scores(rows, train, train, WEIGHTS), [truth[index] for index in train]
            )
            for index, score in zip(test_indices, _fold_scores(rows, train, test_indices, WEIGHTS), strict=True):
                predicted[index] = score >= threshold
        outcomes.append(_binary_metrics(truth, predicted))
    return {
        "repeats": REPEATS,
        "folds": FOLDS,
        "transform_and_threshold_fit_inside_each_training_fold": True,
        "runs_passing_75_75": sum(item["passed_75_75"] for item in outcomes),
        "median_sensitivity": statistics.median(item["sensitivity"] for item in outcomes),
        "median_specificity": statistics.median(item["specificity"] for item in outcomes),
        "minimum_sensitivity": min(item["sensitivity"] for item in outcomes),
        "minimum_specificity": min(item["specificity"] for item in outcomes),
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
    protocol, rows = verify_fusion_protocol(
        bundle_root=bundle_root, protocol_path=protocol_path, expected_case_count=expected_case_count
    )
    if allow_protected_development_labels is not True:
        raise PipelineError("Abertura dos labels protegidos para v20 não foi autorizada.")
    labels_path = Path(labels_path).resolve()
    if labels_path.name != "development_labels.jsonl" or any("holdout" in part.lower() for part in labels_path.parts):
        raise PipelineError("Avaliador v20 aceita somente development_labels.jsonl, nunca holdout.")
    output = Path(output_dir).resolve()
    if output.exists():
        raise PipelineError("Avaliação v20 já existe.")
    case_ids = [str(row["case_id"]) for row in rows]
    labels, labels_hash = _load_development_labels(labels_path, case_ids)
    truth = [labels[case_id]["label"] == "POSITIVE" for case_id in case_ids]
    all_indices = list(range(len(rows)))
    apparent_scores = _fold_scores(rows, all_indices, all_indices, WEIGHTS)
    apparent_threshold, apparent = _best_threshold(apparent_scores, truth)
    primary = _loocv(rows, truth, WEIGHTS)
    v11_only = _loocv(rows, truth, V11_WEIGHTS)
    v19_only = _loocv(rows, truth, {V19_SIGNAL: 1.0})
    repeated = _repeated(rows, truth)
    gate = bool(
        primary["sensitivity"] >= 0.75
        and primary["specificity"] >= 0.75
        and repeated["runs_passing_75_75"] == REPEATS
        and protocol["observed_conservative_seconds"] <= TIME_GATE_SECONDS
    )
    result = {
        "schema": EVALUATION_SCHEMA,
        "status": "development_gate_passed_holdout_still_closed" if gate else "development_only_not_qualified",
        "case_count": len(rows),
        "positive_count": sum(truth),
        "negative_count": len(truth) - sum(truth),
        "primary_feature": protocol["primary_feature"],
        "components": WEIGHTS,
        "apparent_threshold_for_future_calibrator_freeze": apparent_threshold,
        "apparent_metrics": apparent,
        "primary_loocv_metrics": {key: value for key, value in primary.items() if key != "scores"},
        "primary_loocv_confidence_intervals": {
            "sensitivity_95": _wilson(primary["tp"], primary["tp"] + primary["fn"]),
            "specificity_95": _wilson(primary["tn"], primary["tn"] + primary["fp"]),
        },
        "repeated_stratified_5fold": repeated,
        "secondary_diagnostics_not_eligible_for_selection": {
            "v11_only_loocv": {key: value for key, value in v11_only.items() if key != "scores"},
            "v19_only_loocv": {key: value for key, value in v19_only.items() if key != "scores"},
        },
        "development_gate_passed": gate,
        "time_gate_180_seconds_passed": protocol["observed_conservative_seconds"] <= TIME_GATE_SECONDS,
        "end_to_end_180_seconds_proven": False,
        "protocol_signature": protocol["protocol_signature"],
        "protected_development_labels_sha256": labels_hash,
        "ground_truth_read": True,
        "metrics_calculated": True,
        "holdout_opened": False,
        "qualified": False,
        "research_only": True,
        "clinical_use_allowed": False,
        "requires_human_review": True,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    staging = output.parent / f"._v20eval_{uuid.uuid4().hex[:8]}"
    staging.mkdir()
    try:
        _write_json_atomic(staging / "evaluation.json", result)
        with (staging / "case_features.csv").open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=["case_id", "label", *WEIGHTS, "full_development_primary_score"])
            writer.writeheader()
            for index, row in enumerate(rows):
                writer.writerow(
                    {
                        "case_id": row["case_id"],
                        "label": labels[row["case_id"]]["label"],
                        **row["signals"],
                        "full_development_primary_score": apparent_scores[index],
                    }
                )
        _publish_directory(staging, output)
        return result
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
