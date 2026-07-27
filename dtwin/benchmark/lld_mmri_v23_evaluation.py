"""Protected post-freeze evaluation for the independent LLD-MMRI v23 cohort."""
from __future__ import annotations

import json
import math
import shutil
import uuid
from pathlib import Path
from typing import Any

from dtwin.benchmark.lld_mmri_v23_download import _load_and_validate_protocol
from dtwin.benchmark.lld_mmri_v23_predictions import PREDICTION_SCHEMA, RUN_SCHEMA
from dtwin.benchmark.metrics import wilson_interval
from dtwin.benchmark.openswisshcc_alignment import _publish_directory, _sha256
from dtwin.benchmark.openswisshcc_v20_fusion import _canonical_sha
from dtwin.core import PipelineError
from dtwin.medgemma_screening import _write_json_atomic


LABEL_SCHEMA = "argos-lld-mmri-v23-protected-label-v1"
EVALUATION_SCHEMA = "argos-lld-mmri-v23-external-evaluation-v1"
TIMING_SCHEMA = "argos-lld-mmri-v23-end-to-end-timing-v1"


def _load(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PipelineError(f"{label} ausente ou invalido.") from exc
    if not isinstance(value, dict):
        raise PipelineError(f"{label} deve ser objeto.")
    return value


def _jsonl(path: Path, label: str) -> list[dict[str, Any]]:
    try:
        rows = [
            json.loads(line)
            for line in Path(path).read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    except (OSError, json.JSONDecodeError) as exc:
        raise PipelineError(f"{label} ausente ou invalido.") from exc
    if not rows or any(not isinstance(row, dict) for row in rows):
        raise PipelineError(f"{label} vazio ou invalido.")
    return rows


def _verify_predictions(
    prediction_root: Path, protocol: dict[str, Any]
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    root = Path(prediction_root).resolve()
    predictions_path = root / "predictions.jsonl"
    summary = _load(root / "summary.json", "Resumo de predicoes v23")
    rows = _jsonl(predictions_path, "Predicoes v23")
    unsigned = dict(summary)
    signature = unsigned.pop("run_signature", None)
    technical_failure_case_ids = summary.get("technical_failure_case_ids")
    if not isinstance(technical_failure_case_ids, list):
        raise PipelineError("Contrato de falhas tecnicas ausente nas predicoes v23.")
    technical_failure_set = set(technical_failure_case_ids)
    case_ids = [
        case_id for case_id in protocol["case_ids"] if case_id not in technical_failure_set
    ]
    if (
        summary.get("schema") != RUN_SCHEMA
        or summary.get("status") != "frozen_complete_predictions_before_labels"
        or signature != _canonical_sha(unsigned)
        or summary.get("protocol_case_count") != protocol["case_count"]
        or summary.get("case_count") != len(case_ids)
        or summary.get("case_ids") != case_ids
        or summary.get("technical_failure_case_count")
        != len(technical_failure_case_ids)
        or [case_id for case_id in protocol["case_ids"] if case_id in technical_failure_set]
        != technical_failure_case_ids
        or len(case_ids) + len(technical_failure_case_ids) != protocol["case_count"]
        or summary.get("technical_failures_excluded_from_inference") is not True
        or summary.get("technical_failures_count_as_primary_metric_errors") is not True
        or summary.get("predictions_sha256") != _sha256(predictions_path)
        or summary.get("protocol_signature") != protocol["protocol_signature"]
        or summary.get("calibrator_signature") != protocol["calibrator_signature"]
        or summary.get("predictions_frozen") is not True
        or summary.get("ground_truth_read") is not False
        or summary.get("metrics_calculated") is not False
        or summary.get("qualified") is not False
        or len(rows) != len(case_ids)
    ):
        raise PipelineError("Predicoes v23 nao foram congeladas validamente antes dos labels.")
    for case_id, row in zip(case_ids, rows, strict=True):
        unsigned_row = dict(row)
        row_signature = unsigned_row.pop("prediction_signature", None)
        score = row.get("score")
        if (
            row.get("schema") != PREDICTION_SCHEMA
            or row.get("case_id") != case_id
            or row_signature != _canonical_sha(unsigned_row)
            or row.get("prediction") not in {"POSITIVE", "NEGATIVE"}
            or isinstance(score, bool)
            or not isinstance(score, (int, float))
            or not math.isfinite(float(score))
            or row.get("protocol_signature") != protocol["protocol_signature"]
            or row.get("calibrator_signature") != protocol["calibrator_signature"]
            or row.get("ground_truth_read") is not False
            or row.get("metrics_calculated") is not False
        ):
            raise PipelineError("Predicao individual v23 invalida ou adulterada.")
    return summary, rows


def _auc(positive_scores: list[float], negative_scores: list[float]) -> float | None:
    if not positive_scores or not negative_scores:
        return None
    favorable = 0.0
    for positive in positive_scores:
        for negative in negative_scores:
            favorable += 1.0 if positive > negative else 0.5 if positive == negative else 0.0
    return favorable / (len(positive_scores) * len(negative_scores))


def _timing_gate(
    timing_path: Path | None,
    *,
    case_ids: list[str],
    protocol_case_count: int,
    technical_failure_case_ids: list[str],
    prediction_run_signature: str,
) -> tuple[bool, dict[str, Any] | None]:
    if timing_path is None:
        return False, None
    timing_path = Path(timing_path).resolve()
    value = _load(timing_path, "Medicao end-to-end v23")
    cases_path = timing_path.parent / "cases.jsonl"
    cases = _jsonl(cases_path, "Casos da medicao end-to-end v23")
    unsigned = dict(value)
    signature = unsigned.pop("timing_signature", None)
    required_stages = [
        "input_validation", "liver_segmentation", "panel_generation",
        "lesion_localizer", "candidate_shape", "medsiglip", "medgemma",
        "fusion_persistence",
    ]
    maximum = value.get("max_end_to_end_seconds")
    maximum_allowed = value.get("maximum_allowed_seconds")
    eligible_within_budget = value.get(
        "all_inference_eligible_cases_within_180_seconds"
    )
    expected_within_budget = (
        isinstance(maximum, (int, float))
        and not isinstance(maximum, bool)
        and math.isfinite(float(maximum))
        and isinstance(maximum_allowed, (int, float))
        and not isinstance(maximum_allowed, bool)
        and float(maximum_allowed) == 180.0
        and float(maximum) <= float(maximum_allowed)
    )
    valid = (
        value.get("schema") == TIMING_SCHEMA
        and value.get("status") == "complete_measured_end_to_end"
        and signature == _canonical_sha(unsigned)
        and value.get("case_ids") == case_ids
        and value.get("case_count") == len(case_ids)
        and value.get("protocol_case_count") == protocol_case_count
        and value.get("technical_failure_case_count")
        == len(technical_failure_case_ids)
        and value.get("technical_failure_case_ids") == technical_failure_case_ids
        and value.get("technical_failures_count_as_primary_metric_errors") is True
        and value.get("prediction_run_signature") == prediction_run_signature
        and value.get("runner_id") == "argos-lld-mmri-v23-direct-case-runner-v1"
        and value.get("required_stages") == required_stages
        and value.get("continuous_wall_clock") is True
        and value.get("component_sum_only") is False
        and value.get("all_predictions_exactly_reproduced") is True
        and value.get("ground_truth_read") is False
        and value.get("lesion_masks_read") == 0
        and value.get("cases_sha256") == _sha256(cases_path)
        and len(cases) == len(case_ids)
        and isinstance(eligible_within_budget, bool)
        and eligible_within_budget is expected_within_budget
        and value.get("all_cases_within_180_seconds") is eligible_within_budget
        and isinstance(maximum, (int, float))
        and not isinstance(maximum, bool)
        and math.isfinite(float(maximum))
        and float(maximum) >= 0
        and isinstance(maximum_allowed, (int, float))
        and not isinstance(maximum_allowed, bool)
        and float(maximum_allowed) == 180.0
    )
    if not valid:
        raise PipelineError("Medicao end-to-end v23 invalida ou insuficiente para o gate.")
    elapsed_values = []
    for case_id, row in zip(case_ids, cases, strict=True):
        unsigned_row = dict(row)
        row_signature = unsigned_row.pop("case_timing_signature", None)
        elapsed = row.get("elapsed_seconds")
        stages = row.get("stages")
        if (
            row.get("schema") != "argos-lld-mmri-v23-direct-case-timing-v1"
            or row.get("case_id") != case_id
            or row_signature != _canonical_sha(unsigned_row)
            or row.get("runner_id") != "argos-lld-mmri-v23-direct-case-runner-v1"
            or row.get("continuous_wall_clock") is not True
            or row.get("component_sum_only") is not False
            or isinstance(elapsed, bool)
            or not isinstance(elapsed, (int, float))
            or not math.isfinite(float(elapsed))
            or row.get("within_budget") is not (float(elapsed) <= 180.0)
            or row.get("maximum_seconds") != 180.0
            or row.get("ground_truth_read") is not False
            or row.get("lesion_masks_read") != 0
            or not isinstance(stages, dict)
            or set(stages) != set(required_stages)
            or any(not isinstance(item, dict) or item.get("status") != "complete" for item in stages.values())
            or float(elapsed) < 0
        ):
            raise PipelineError("Registro individual de tempo v23 invalido ou adulterado.")
        elapsed_values.append(float(elapsed))
    if not math.isclose(max(elapsed_values), float(value["max_end_to_end_seconds"]), rel_tol=0, abs_tol=1e-9):
        raise PipelineError("Maximo end-to-end v23 divergiu dos registros individuais.")
    return eligible_within_budget, value


def evaluate_lld_mmri_v23_after_prediction_freeze(
    *,
    protocol_root: Path,
    prediction_root: Path,
    protected_labels_path: Path,
    output_root: Path,
    allow_protected_public_labels: bool = False,
    end_to_end_timing_path: Path | None = None,
) -> dict[str, Any]:
    """Open public labels only after predictions are frozen and calculate final metrics."""

    if allow_protected_public_labels is not True:
        raise PipelineError("Abertura dos labels publicos protegidos LLD-MMRI nao autorizada.")
    protocol, _ = _load_and_validate_protocol(protocol_root)
    prediction_summary, predictions = _verify_predictions(prediction_root, protocol)
    labels_path = Path(protected_labels_path).resolve()
    if _sha256(labels_path) != protocol.get("protected_labels_sha256"):
        raise PipelineError("Hash dos labels protegidos LLD-MMRI divergiu do protocolo.")

    # This is the only protected-label parse in the evaluator and occurs after freeze checks.
    labels = _jsonl(labels_path, "Labels protegidos LLD-MMRI")
    if len(labels) != protocol["case_count"]:
        raise PipelineError("Labels protegidos LLD-MMRI nao cobrem a coorte.")
    expected_counts = {
        "POSITIVE": int(protocol["positive_count"]),
        "NEGATIVE": int(protocol["negative_count"]),
    }
    subtype_counts: dict[str, dict[str, int]] = {}
    tp = tn = fp = fn = 0
    positive_scores: list[float] = []
    negative_scores: list[float] = []
    case_results = []
    predictions_by_id = {str(row["case_id"]): row for row in predictions}
    technical_failure_case_ids = list(
        prediction_summary["technical_failure_case_ids"]
    )
    technical_failure_set = set(technical_failure_case_ids)
    for case_id, label in zip(protocol["case_ids"], labels, strict=True):
        truth = label.get("label")
        subtype = str(label.get("subtype", ""))
        if (
            label.get("schema") != LABEL_SCHEMA
            or label.get("case_id") != case_id
            or truth not in {"POSITIVE", "NEGATIVE"}
            or not subtype
            or label.get("target_condition") != protocol["target_condition"]
            or label.get("research_only") is not True
            or label.get("clinical_use_allowed") is not False
        ):
            raise PipelineError("Registro protegido LLD-MMRI invalido ou fora de ordem.")
        prediction = predictions_by_id.get(case_id)
        is_technical_failure = case_id in technical_failure_set
        if is_technical_failure:
            if prediction is not None:
                raise PipelineError("Falha tecnica LLD-MMRI possui predicao indevida.")
            decision = "TECHNICAL_FAILURE"
            score = None
            fn += truth == "POSITIVE"
            fp += truth == "NEGATIVE"
        else:
            if prediction is None:
                raise PipelineError("Predicao elegivel LLD-MMRI ausente.")
            decision = prediction["prediction"]
            score = float(prediction["score"])
            tp += truth == "POSITIVE" and decision == "POSITIVE"
            fn += truth == "POSITIVE" and decision == "NEGATIVE"
            tn += truth == "NEGATIVE" and decision == "NEGATIVE"
            fp += truth == "NEGATIVE" and decision == "POSITIVE"
            (positive_scores if truth == "POSITIVE" else negative_scores).append(score)
        group = subtype_counts.setdefault(subtype, {"total": 0, "correct": 0})
        group["total"] += 1
        group["correct"] += decision == truth
        case_results.append(
            {"case_id": case_id, "truth": truth, "subtype": subtype,
             "prediction": decision, "score": score,
             "technical_failure": is_technical_failure}
        )
    observed = {"POSITIVE": tp + fn, "NEGATIVE": tn + fp}
    if observed != expected_counts:
        raise PipelineError("Distribuicao dos labels LLD-MMRI divergiu do protocolo.")
    sensitivity = tp / (tp + fn)
    specificity = tn / (tn + fp)
    accuracy_gate = sensitivity >= 0.75 and specificity >= 0.75
    roc_auc = _auc(positive_scores, negative_scores)
    roc_auc_available = roc_auc is not None
    timing_gate, timing = _timing_gate(
        end_to_end_timing_path,
        case_ids=list(prediction_summary["case_ids"]),
        protocol_case_count=protocol["case_count"],
        technical_failure_case_ids=technical_failure_case_ids,
        prediction_run_signature=prediction_summary["run_signature"],
    )
    output_root = Path(output_root).resolve()
    if output_root.exists():
        raise PipelineError("Avaliacao LLD-MMRI v23 existente; sobrescrita recusada.")
    output_root.parent.mkdir(parents=True, exist_ok=True)
    staging = output_root.parent / f"._lldv23eval_{uuid.uuid4().hex[:8]}"
    staging.mkdir()
    try:
        results_path = staging / "case_results.jsonl"
        results_path.write_text(
            "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in case_results),
            encoding="utf-8",
        )
        base = {
            "schema": EVALUATION_SCHEMA,
            "status": "complete_external_evaluation",
            "case_count": len(case_results),
            "inference_eligible_case_count": len(predictions),
            "technical_failure_case_count": len(technical_failure_case_ids),
            "technical_failure_case_ids": technical_failure_case_ids,
            "technical_failures_count_as_primary_metric_errors": True,
            "positive_count": tp + fn,
            "negative_count": tn + fp,
            "confusion_matrix": {"tp": tp, "tn": tn, "fp": fp, "fn": fn},
            "sensitivity": sensitivity,
            "sensitivity_95_wilson": wilson_interval(tp, tp + fn),
            "specificity": specificity,
            "specificity_95_wilson": wilson_interval(tn, tn + fp),
            "roc_auc": roc_auc,
            "roc_auc_available": roc_auc_available,
            "roc_auc_unavailable_reason": (
                None
                if roc_auc_available
                else "one_or_both_truth_classes_absent_after_technical_failure_exclusion"
            ),
            "roc_auc_scope": "inference_eligible_cases_only",
            "roc_auc_inference_eligible_positive_count": len(positive_scores),
            "roc_auc_inference_eligible_negative_count": len(negative_scores),
            "roc_auc_excluded_technical_failure_count": len(
                technical_failure_case_ids
            ),
            "subtype_metrics": {
                key: {**value, "accuracy_within_truth_subtype": value["correct"] / value["total"]}
                for key, value in sorted(subtype_counts.items())
            },
            "accuracy_gate_75_75_passed": accuracy_gate,
            "end_to_end_180_second_gate_passed": timing_gate,
            "qualified": accuracy_gate and timing_gate,
            "timing_evidence": timing,
            "protocol_signature": protocol["protocol_signature"],
            "prediction_run_signature": prediction_summary["run_signature"],
            "predictions_sha256": prediction_summary["predictions_sha256"],
            "protected_labels_sha256": _sha256(labels_path),
            "case_results_sha256": _sha256(results_path),
            "labels_opened_after_prediction_freeze": True,
            "lesion_masks_read": 0,
            "lesion_masks_used": False,
            "research_only": True,
            "clinical_use_allowed": False,
            "requires_human_review": True,
        }
        summary = dict(base)
        summary["evaluation_signature"] = _canonical_sha(base)
        _write_json_atomic(staging / "summary.json", summary)
        _publish_directory(staging, output_root)
        return summary
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise


__all__ = ["EVALUATION_SCHEMA", "TIMING_SCHEMA", "evaluate_lld_mmri_v23_after_prediction_freeze"]
