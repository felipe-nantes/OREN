"""Protected positive-only external evaluation for LiverHccSeg v21."""
from __future__ import annotations

import json
import math
import shutil
import statistics
import uuid
from pathlib import Path
from typing import Any

from dtwin.benchmark.liverhccseg_preparation import COHORT_SCHEMA as PREPARED_COHORT_SCHEMA
from dtwin.benchmark.openswisshcc_alignment import _publish_directory, _sha256
from dtwin.benchmark.openswisshcc_localizer_roi_evaluation import _wilson
from dtwin.benchmark.public_independent_v21_calibrator import (
    SCORE_SCHEMA,
    SCORE_SUMMARY_SCHEMA,
    _canonical_sha,
    _load_calibrator,
)
from dtwin.core import PipelineError
from dtwin.datasets.liverhccseg_labels import AUDIT_SCHEMA
from dtwin.medgemma_screening import _write_json_atomic


EVALUATION_SCHEMA = "argos-public-independent-v21-positive-only-evaluation-v1"
PROTOCOL_SCHEMA = "argos-liverhccseg-v21-positive-evaluation-authorization-v1"


def _load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PipelineError(f"JSON de avaliacao v21 invalido: {path}") from exc
    if not isinstance(value, dict):
        raise PipelineError("JSON de avaliacao v21 deve ser objeto.")
    return value


def _jsonl(path: Path) -> list[dict[str, Any]]:
    try:
        rows = [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]
    except (OSError, json.JSONDecodeError) as exc:
        raise PipelineError(f"Predicoes v21 invalidas: {path}") from exc
    if not rows or any(not isinstance(row, dict) for row in rows):
        raise PipelineError("Predicoes v21 vazias ou invalidas.")
    return rows


def freeze_liverhccseg_v21_evaluation_protocol(
    *,
    scored_root: Path,
    calibrator_path: Path,
    prepared_root: Path,
    output_path: Path,
    expected_case_count: int = 14,
) -> dict[str, Any]:
    """Bind the still-blind predictions to one future protected evaluation."""

    scored_root = Path(scored_root).resolve()
    calibrator_path = Path(calibrator_path).resolve()
    prepared_root = Path(prepared_root).resolve()
    summary_path = scored_root / "summary.json"
    scores_path = scored_root / "scores.jsonl"
    prepared_path = prepared_root / "cohort_manifest.json"
    summary = _load(summary_path)
    scores = _jsonl(scores_path)
    calibrator = _load_calibrator(calibrator_path)
    prepared = _load(prepared_path)
    if (
        summary.get("schema") != SCORE_SUMMARY_SCHEMA
        or summary.get("status") != "complete_predictions_frozen_labels_still_closed"
        or summary.get("case_count") != expected_case_count
        or summary.get("scores_sha256") != _sha256(scores_path)
        or summary.get("calibrator_sha256") != _sha256(calibrator_path)
        or summary.get("calibrator_signature") != calibrator["calibrator_signature"]
        or summary.get("ground_truth_read") is not False
        or summary.get("metrics_calculated") is not False
        or summary.get("holdout_opened") is not False
        or len(scores) != expected_case_count
    ):
        raise PipelineError("Predicoes v21 nao estao completas, congeladas e cegas para o protocolo.")
    if (
        prepared.get("schema") != PREPARED_COHORT_SCHEMA
        or prepared.get("case_count") != expected_case_count
        or prepared.get("lesion_masks_copied") is not False
        or prepared.get("pathology_labels_copied") is not False
        or prepared.get("holdout_opened") is not False
        or not isinstance(prepared.get("selection_audit_sha256"), str)
        or len(prepared["selection_audit_sha256"]) != 64
    ):
        raise PipelineError("Coorte preparada LiverHccSeg invalida para congelar o protocolo.")
    case_ids = [str(item.get("case_id", "")) for item in prepared.get("cases", [])]
    if (
        len(case_ids) != expected_case_count
        or summary.get("case_ids") != case_ids
        or [row.get("case_id") for row in scores] != case_ids
    ):
        raise PipelineError("Casos da coorte e das predicoes divergem no protocolo v21.")
    payload = {
        "schema": PROTOCOL_SCHEMA,
        "score_summary_sha256": _sha256(summary_path),
        "scores_sha256": _sha256(scores_path),
        "calibrator_sha256": _sha256(calibrator_path),
        "calibrator_signature": calibrator["calibrator_signature"],
        "prepared_cohort_sha256": _sha256(prepared_path),
        "protected_selection_audit_sha256": prepared["selection_audit_sha256"],
        "case_count": expected_case_count,
        "holdout_must_remain_closed": True,
        "evaluation_scope": "positive_only_external_sensitivity_stress",
    }
    payload["protocol_signature"] = _canonical_sha(payload)
    destination = Path(output_path).resolve()
    if destination.exists():
        raise PipelineError("Protocolo de avaliacao v21 ja existe; recuso sobrescrever.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    _write_json_atomic(destination, payload)
    return payload


def _verify_evaluation_protocol(
    *,
    protocol_path: Path,
    authorized_signature: str,
    summary_path: Path,
    scores_path: Path,
    calibrator_path: Path,
    prepared_path: Path,
    prepared: dict[str, Any],
    expected_case_count: int,
) -> dict[str, Any]:
    protocol_path = Path(protocol_path).resolve()
    protocol = _load(protocol_path)
    signed = {key: value for key, value in protocol.items() if key != "protocol_signature"}
    expected = {
        "schema": PROTOCOL_SCHEMA,
        "score_summary_sha256": _sha256(summary_path),
        "scores_sha256": _sha256(scores_path),
        "calibrator_sha256": _sha256(calibrator_path),
        "calibrator_signature": protocol.get("calibrator_signature"),
        "prepared_cohort_sha256": _sha256(prepared_path),
        "protected_selection_audit_sha256": prepared.get("selection_audit_sha256"),
        "case_count": expected_case_count,
        "holdout_must_remain_closed": True,
        "evaluation_scope": "positive_only_external_sensitivity_stress",
    }
    signature = protocol.get("protocol_signature")
    if (
        signed != expected
        or signature != _canonical_sha(signed)
        or signature != str(authorized_signature)
    ):
        raise PipelineError("Protocolo de avaliacao v21 invalido, adulterado ou nao autorizado.")
    return protocol


def evaluate_liverhccseg_v21_positive_arm(
    *,
    scored_root: Path,
    calibrator_path: Path,
    prepared_root: Path,
    protocol_path: Path,
    authorized_protocol_signature: str,
    protected_selection_audit_path: Path,
    output_dir: Path,
    allow_protected_public_ground_truth: bool = False,
    expected_case_count: int = 14,
) -> dict[str, Any]:
    """Evaluate sensitivity only after predictions are complete and frozen."""

    if allow_protected_public_ground_truth is not True:
        raise PipelineError("Abertura do ground truth publico LiverHccSeg nao foi autorizada.")
    scored_root = Path(scored_root).resolve()
    calibrator_path = Path(calibrator_path).resolve()
    prepared_root = Path(prepared_root).resolve()
    audit_path = Path(protected_selection_audit_path).resolve()
    summary_path = scored_root / "summary.json"
    scores_path = scored_root / "scores.jsonl"
    summary = _load(summary_path)
    scores = _jsonl(scores_path)
    calibrator = _load_calibrator(calibrator_path)
    prepared_path = prepared_root / "cohort_manifest.json"
    prepared = _load(prepared_path)
    if (
        summary.get("schema") != SCORE_SUMMARY_SCHEMA
        or summary.get("status") != "complete_predictions_frozen_labels_still_closed"
        or summary.get("case_count") != expected_case_count
        or summary.get("scores_sha256") != _sha256(scores_path)
        or summary.get("calibrator_sha256") != _sha256(calibrator_path)
        or summary.get("calibrator_signature") != calibrator["calibrator_signature"]
        or summary.get("ground_truth_read") is not False
        or summary.get("metrics_calculated") is not False
        or summary.get("holdout_opened") is not False
        or len(scores) != expected_case_count
    ):
        raise PipelineError("Predicoes v21 nao estao completas, congeladas e cegas.")
    if (
        prepared.get("schema") != PREPARED_COHORT_SCHEMA
        or prepared.get("case_count") != expected_case_count
        or prepared.get("lesion_masks_copied") is not False
        or prepared.get("pathology_labels_copied") is not False
        or prepared.get("holdout_opened") is not False
    ):
        raise PipelineError("Coorte preparada LiverHccSeg invalida para avaliacao.")
    case_ids = [str(item["case_id"]) for item in prepared["cases"]]
    if summary.get("case_ids") != case_ids or [row.get("case_id") for row in scores] != case_ids:
        raise PipelineError("Predicoes e coorte LiverHccSeg possuem casos ou ordem divergentes.")
    for row in scores:
        if (
            row.get("schema") != SCORE_SCHEMA
            or row.get("decision") not in {"POSITIVE", "NEGATIVE"}
            or row.get("calibrator_signature") != calibrator["calibrator_signature"]
            or row.get("ground_truth_read") is not False
            or row.get("metrics_calculated") is not False
            or row.get("holdout_opened") is not False
        ):
            raise PipelineError("Predicao v21 individual invalida.")

    protocol = _verify_evaluation_protocol(
        protocol_path=protocol_path,
        authorized_signature=authorized_protocol_signature,
        summary_path=summary_path,
        scores_path=scores_path,
        calibrator_path=calibrator_path,
        prepared_path=prepared_path,
        prepared=prepared,
        expected_case_count=expected_case_count,
    )

    # This is the only protected artifact parsed here, after all blind gates.
    audit = _load(audit_path)
    if (
        audit.get("schema") != AUDIT_SCHEMA
        or audit.get("status") != "tumor_positive_registry_filtered"
        or audit.get("included_tumor_subject_count") != expected_case_count
        or audit.get("excluded_subjects_not_assumed_negative") is not True
        or audit.get("ground_truth_available_to_inference") is not False
        or audit.get("research_only") is not True
        or audit.get("clinical_use_allowed") is not False
        or prepared.get("selection_audit_sha256") != _sha256(audit_path)
    ):
        raise PipelineError("Auditoria protegida LiverHccSeg nao comprova os 14 positivos.")

    true_positive = sum(row["decision"] == "POSITIVE" for row in scores)
    false_negative = expected_case_count - true_positive
    sensitivity = true_positive / expected_case_count
    times = [float(row.get("total_component_seconds", math.inf)) for row in scores]
    if any(not math.isfinite(value) or value < 0 for value in times):
        raise PipelineError("Tempo de predicao v21 invalido.")
    ordered_times = sorted(times)
    p95 = ordered_times[max(0, math.ceil(0.95 * len(ordered_times)) - 1)]
    time_passed = all(row.get("time_gate_180_seconds_passed") is True for row in scores) and max(times) <= 180.0
    sensitivity_passed = sensitivity >= 0.75
    result = {
        "schema": EVALUATION_SCHEMA,
        "status": "external_positive_arm_evaluated_holdout_still_closed",
        "evaluation_scope": "positive_only_external_sensitivity_stress",
        "case_count": expected_case_count,
        "positive_count": expected_case_count,
        "negative_count": 0,
        "confusion_matrix_positive_arm": {"tp": true_positive, "fn": false_negative},
        "sensitivity": sensitivity,
        "sensitivity_95_wilson": _wilson(true_positive, expected_case_count),
        "specificity": None,
        "specificity_status": "not_estimable_no_negative_cases_in_this_arm",
        "roc_auc": None,
        "roc_auc_status": "not_estimable_single_class",
        "sensitivity_gate_75_passed": sensitivity_passed,
        "simultaneous_75_75_gate_evaluated": False,
        "simultaneous_75_75_gate_passed": False,
        "timing_seconds": {
            "mean": statistics.fmean(times),
            "median": statistics.median(times),
            "p95_nearest_rank": p95,
            "maximum": max(times),
        },
        "time_gate_180_seconds_passed": time_passed,
        "qualified": False,
        "qualification_reason": "positive-only arm cannot establish specificity or simultaneous 75/75",
        "authorized_protocol_signature": protocol["protocol_signature"],
        "source_hashes": {
            "evaluation_protocol_sha256": _sha256(Path(protocol_path).resolve()),
            "score_summary_sha256": _sha256(summary_path),
            "scores_sha256": _sha256(scores_path),
            "calibrator_sha256": _sha256(calibrator_path),
            "prepared_cohort_sha256": _sha256(prepared_path),
            "protected_selection_audit_sha256": _sha256(audit_path),
        },
        "protected_public_ground_truth_read": True,
        "holdout_opened": False,
        "research_only": True,
        "clinical_use_allowed": False,
        "requires_human_review": True,
    }
    output_dir = Path(output_dir).resolve()
    if output_dir.exists():
        raise PipelineError("Avaliacao positiva v21 ja existe; recuso sobrescrever.")
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    staging = output_dir.parent / f"._v21eval_{uuid.uuid4().hex[:8]}"
    staging.mkdir()
    try:
        _write_json_atomic(staging / "evaluation.json", result)
        report = (
            "# Avaliação externa v21 — braço positivo LiverHccSeg\n\n"
            f"- Casos positivos: {expected_case_count}\n"
            f"- TP/FN: {true_positive}/{false_negative}\n"
            f"- Sensibilidade: {100*sensitivity:.2f}%\n"
            f"- IC95% Wilson: {100*result['sensitivity_95_wilson'][0]:.2f}%–{100*result['sensitivity_95_wilson'][1]:.2f}%\n"
            f"- Tempo maximo: {max(times):.2f} s\n"
            f"- Gate de 180 s: {'PASS' if time_passed else 'FAIL'}\n\n"
            "Especificidade e ROC-AUC não são estimáveis neste braço de classe única. "
            "Este resultado não qualifica o ARGOS em 75%/75%. O holdout permanece fechado.\n"
        )
        (staging / "report.md").write_text(report, encoding="utf-8")
        _publish_directory(staging, output_dir)
        return result
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
