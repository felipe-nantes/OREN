"""Protected negative-only evaluation for the CHAOS v21 specificity stress arm."""
from __future__ import annotations

import json
import math
import shutil
import statistics
import uuid
from pathlib import Path
from typing import Any

from dtwin.benchmark.chaos_v21_preparation import COHORT_SCHEMA as PREPARED_COHORT_SCHEMA
from dtwin.benchmark.openswisshcc_alignment import _publish_directory, _sha256
from dtwin.benchmark.openswisshcc_localizer_roi_evaluation import _wilson
from dtwin.benchmark.public_independent_cohort import (
    LABELS_SCHEMA,
    PROTOCOL_SCHEMA as PUBLIC_PROTOCOL_SCHEMA,
    _canonical_hash as _public_canonical_hash,
)
from dtwin.benchmark.public_independent_v21_calibrator import (
    SCORE_SCHEMA,
    SCORE_SUMMARY_SCHEMA,
    _canonical_sha,
    _load_calibrator,
)
from dtwin.core import PipelineError
from dtwin.medgemma_screening import _write_json_atomic


EVALUATION_SCHEMA = "argos-public-independent-v21-negative-only-evaluation-v1"
PROTOCOL_SCHEMA = "argos-chaos-v21-negative-evaluation-authorization-v1"


def _load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PipelineError(f"JSON de avaliacao negativa v21 invalido: {path}") from exc
    if not isinstance(value, dict):
        raise PipelineError("JSON de avaliacao negativa v21 deve ser objeto.")
    return value


def _jsonl(path: Path) -> list[dict[str, Any]]:
    try:
        rows = [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]
    except (OSError, json.JSONDecodeError) as exc:
        raise PipelineError(f"JSONL de avaliacao negativa v21 invalido: {path}") from exc
    if not rows or any(not isinstance(row, dict) for row in rows):
        raise PipelineError("JSONL de avaliacao negativa v21 vazio ou invalido.")
    return rows


def _verify_blind_scores(
    *, scored_root: Path, calibrator_path: Path, prepared_root: Path,
    expected_case_count: int,
) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any], dict[str, Any]]:
    scored_root = Path(scored_root).resolve()
    summary_path = scored_root / "summary.json"
    scores_path = scored_root / "scores.jsonl"
    calibrator_path = Path(calibrator_path).resolve()
    prepared_path = Path(prepared_root).resolve() / "cohort_manifest.json"
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
        raise PipelineError("Predicoes CHAOS v21 nao estao completas, congeladas e cegas.")
    if (
        prepared.get("schema") != PREPARED_COHORT_SCHEMA
        or prepared.get("case_count") != expected_case_count
        or prepared.get("lesion_masks_copied") is not False
        or prepared.get("pathology_labels_copied") is not False
        or prepared.get("ground_truth_class_read") is not False
        or prepared.get("combined_primary_metric_allowed") is not False
        or prepared.get("holdout_opened") is not False
    ):
        raise PipelineError("Coorte preparada CHAOS invalida para avaliacao.")
    case_ids = [str(item.get("case_id", "")) for item in prepared.get("cases", [])]
    if (
        len(case_ids) != expected_case_count
        or summary.get("case_ids") != case_ids
        or [row.get("case_id") for row in scores] != case_ids
    ):
        raise PipelineError("Casos da coorte e das predicoes CHAOS divergem.")
    for row in scores:
        if (
            row.get("schema") != SCORE_SCHEMA
            or row.get("decision") not in {"POSITIVE", "NEGATIVE"}
            or row.get("calibrator_signature") != calibrator["calibrator_signature"]
            or row.get("ground_truth_read") is not False
            or row.get("metrics_calculated") is not False
            or row.get("holdout_opened") is not False
        ):
            raise PipelineError("Predicao CHAOS v21 individual invalida.")
    return summary, scores, calibrator, prepared


def _verify_public_protocol(bundle_root: Path, prepared: dict[str, Any]) -> tuple[dict[str, Any], Path]:
    bundle_root = Path(bundle_root).resolve()
    protocol_path = bundle_root / "cohort_protocol.json"
    labels_path = bundle_root / "protected_ground_truth" / "protected_labels.jsonl"
    protocol = _load(protocol_path)
    unsigned = dict(protocol)
    signature = str(unsigned.pop("protocol_signature", ""))
    if (
        protocol.get("schema") != PUBLIC_PROTOCOL_SCHEMA
        or signature != _public_canonical_hash(unsigned)
        or signature != prepared.get("source_public_protocol_signature")
        or protocol.get("protected_labels_sha256") != _sha256(labels_path)
        or protocol.get("holdout_opened") is not False
        or protocol.get("ground_truth_read_during_inference") is not False
    ):
        raise PipelineError("Protocolo publico/protected labels CHAOS invalido ou adulterado.")
    return protocol, labels_path


def freeze_chaos_v21_evaluation_protocol(
    *, scored_root: Path, calibrator_path: Path, prepared_root: Path,
    public_bundle_root: Path, output_path: Path, expected_case_count: int = 20,
) -> dict[str, Any]:
    """Bind blind predictions to the future protected negative-only evaluation."""

    summary, scores, calibrator, prepared = _verify_blind_scores(
        scored_root=scored_root, calibrator_path=calibrator_path,
        prepared_root=prepared_root, expected_case_count=expected_case_count,
    )
    public_protocol, labels_path = _verify_public_protocol(public_bundle_root, prepared)
    scored_root = Path(scored_root).resolve()
    calibrator_path = Path(calibrator_path).resolve()
    prepared_path = Path(prepared_root).resolve() / "cohort_manifest.json"
    public_protocol_path = Path(public_bundle_root).resolve() / "cohort_protocol.json"
    payload = {
        "schema": PROTOCOL_SCHEMA,
        "score_summary_sha256": _sha256(scored_root / "summary.json"),
        "scores_sha256": _sha256(scored_root / "scores.jsonl"),
        "calibrator_sha256": _sha256(calibrator_path),
        "calibrator_signature": calibrator["calibrator_signature"],
        "prepared_cohort_sha256": _sha256(prepared_path),
        "public_cohort_protocol_sha256": _sha256(public_protocol_path),
        "public_cohort_protocol_signature": public_protocol["protocol_signature"],
        "protected_labels_sha256": _sha256(labels_path),
        "case_count": expected_case_count,
        "case_ids_sha256": _canonical_sha([row["case_id"] for row in scores]),
        "holdout_must_remain_closed": True,
        "combined_primary_metric_allowed": False,
        "evaluation_scope": "negative_only_secondary_specificity_domain_shift_stress",
    }
    payload["protocol_signature"] = _canonical_sha(payload)
    destination = Path(output_path).resolve()
    if destination.exists():
        raise PipelineError("Protocolo de avaliacao CHAOS v21 ja existe; recuso sobrescrever.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    _write_json_atomic(destination, payload)
    return payload


def _verify_evaluation_protocol(
    *, protocol_path: Path, authorized_signature: str, scored_root: Path,
    calibrator_path: Path, prepared_root: Path, public_bundle_root: Path,
    expected_case_count: int,
) -> dict[str, Any]:
    protocol = _load(Path(protocol_path).resolve())
    unsigned = dict(protocol)
    signature = str(unsigned.pop("protocol_signature", ""))
    _summary, scores, calibrator, prepared = _verify_blind_scores(
        scored_root=scored_root, calibrator_path=calibrator_path,
        prepared_root=prepared_root, expected_case_count=expected_case_count,
    )
    public_protocol, labels_path = _verify_public_protocol(public_bundle_root, prepared)
    scored_root = Path(scored_root).resolve()
    prepared_path = Path(prepared_root).resolve() / "cohort_manifest.json"
    public_protocol_path = Path(public_bundle_root).resolve() / "cohort_protocol.json"
    expected = {
        "schema": PROTOCOL_SCHEMA,
        "score_summary_sha256": _sha256(scored_root / "summary.json"),
        "scores_sha256": _sha256(scored_root / "scores.jsonl"),
        "calibrator_sha256": _sha256(Path(calibrator_path).resolve()),
        "calibrator_signature": calibrator["calibrator_signature"],
        "prepared_cohort_sha256": _sha256(prepared_path),
        "public_cohort_protocol_sha256": _sha256(public_protocol_path),
        "public_cohort_protocol_signature": public_protocol["protocol_signature"],
        "protected_labels_sha256": _sha256(labels_path),
        "case_count": expected_case_count,
        "case_ids_sha256": _canonical_sha([row["case_id"] for row in scores]),
        "holdout_must_remain_closed": True,
        "combined_primary_metric_allowed": False,
        "evaluation_scope": "negative_only_secondary_specificity_domain_shift_stress",
    }
    if unsigned != expected or signature != _canonical_sha(unsigned) or signature != str(authorized_signature):
        raise PipelineError("Protocolo de avaliacao CHAOS invalido, adulterado ou nao autorizado.")
    return protocol


def evaluate_chaos_v21_negative_arm(
    *, scored_root: Path, calibrator_path: Path, prepared_root: Path,
    public_bundle_root: Path, protocol_path: Path,
    authorized_protocol_signature: str, output_dir: Path,
    allow_protected_public_ground_truth: bool = False,
    expected_case_count: int = 20,
) -> dict[str, Any]:
    """Evaluate specificity only after blind predictions and explicit authorization."""

    if allow_protected_public_ground_truth is not True:
        raise PipelineError("Abertura do ground truth publico CHAOS nao foi autorizada.")
    summary, scores, calibrator, prepared = _verify_blind_scores(
        scored_root=scored_root, calibrator_path=calibrator_path,
        prepared_root=prepared_root, expected_case_count=expected_case_count,
    )
    public_protocol, labels_path = _verify_public_protocol(public_bundle_root, prepared)
    protocol = _verify_evaluation_protocol(
        protocol_path=protocol_path, authorized_signature=authorized_protocol_signature,
        scored_root=scored_root, calibrator_path=calibrator_path,
        prepared_root=prepared_root, public_bundle_root=public_bundle_root,
        expected_case_count=expected_case_count,
    )

    # This is the only semantic parse of the protected labels and happens after all gates.
    all_labels = _jsonl(labels_path)
    labels_by_id = {str(row.get("case_id", "")): row for row in all_labels}
    case_ids = [str(item["case_id"]) for item in prepared["cases"]]
    selected = [labels_by_id.get(case_id) for case_id in case_ids]
    if any(row is None for row in selected):
        raise PipelineError("Ground truth CHAOS nao contem todos os casos preparados.")
    for row in selected:
        assert row is not None
        if (
            row.get("schema") != LABELS_SCHEMA
            or row.get("label") != "negative"
            or row.get("dataset_id") != "chaos_mri"
            or row.get("target_condition") != "focal_liver_lesion_suspicion"
            or row.get("research_only") is not True
            or row.get("clinical_use_allowed") is not False
        ):
            raise PipelineError("Ground truth protegido nao comprova o braco negativo CHAOS.")

    true_negative = sum(row["decision"] == "NEGATIVE" for row in scores)
    false_positive = expected_case_count - true_negative
    specificity = true_negative / expected_case_count
    times = [float(row.get("total_component_seconds", math.inf)) for row in scores]
    if any(not math.isfinite(value) or value < 0 for value in times):
        raise PipelineError("Tempo de predicao CHAOS v21 invalido.")
    ordered = sorted(times)
    p95 = ordered[max(0, math.ceil(0.95 * len(ordered)) - 1)]
    time_passed = all(row.get("time_gate_180_seconds_passed") is True for row in scores) and max(times) <= 180.0
    result = {
        "schema": EVALUATION_SCHEMA,
        "status": "secondary_negative_arm_evaluated_holdout_still_closed",
        "evaluation_scope": "negative_only_secondary_specificity_domain_shift_stress",
        "case_count": expected_case_count, "positive_count": 0,
        "negative_count": expected_case_count,
        "confusion_matrix_negative_arm": {"tn": true_negative, "fp": false_positive},
        "specificity": specificity,
        "specificity_95_wilson": _wilson(true_negative, expected_case_count),
        "false_positive_rate": false_positive / expected_case_count,
        "sensitivity": None,
        "sensitivity_status": "not_estimable_no_positive_cases_in_this_arm",
        "roc_auc": None, "roc_auc_status": "not_estimable_single_class",
        "specificity_gate_75_passed": specificity >= 0.75,
        "simultaneous_75_75_gate_evaluated": False,
        "simultaneous_75_75_gate_passed": False,
        "timing_seconds": {
            "mean": statistics.fmean(times), "median": statistics.median(times),
            "p95_nearest_rank": p95, "maximum": max(times),
        },
        "time_gate_180_seconds_passed": time_passed,
        "dataset_class_confounding": True,
        "combined_primary_metric_allowed": False,
        "qualified": False,
        "qualification_reason": "negative-only cross-dataset stress cannot establish simultaneous 75/75",
        "authorized_protocol_signature": protocol["protocol_signature"],
        "public_cohort_protocol_signature": public_protocol["protocol_signature"],
        "source_hashes": {
            "scores_sha256": _sha256(Path(scored_root).resolve() / "scores.jsonl"),
            "calibrator_sha256": _sha256(Path(calibrator_path).resolve()),
            "prepared_cohort_sha256": _sha256(Path(prepared_root).resolve() / "cohort_manifest.json"),
            "protected_labels_sha256": _sha256(labels_path),
        },
        "protected_public_ground_truth_read": True,
        "holdout_opened": False, "research_only": True,
        "clinical_use_allowed": False, "requires_human_review": True,
    }
    output_dir = Path(output_dir).resolve()
    if output_dir.exists():
        raise PipelineError("Avaliacao negativa CHAOS v21 ja existe; recuso sobrescrever.")
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    staging = output_dir.parent / f"._chaos_v21_eval_{uuid.uuid4().hex[:8]}"
    staging.mkdir()
    try:
        _write_json_atomic(staging / "evaluation.json", result)
        report = (
            "# Avaliação externa v21 — braço negativo CHAOS\n\n"
            f"- Controles: {expected_case_count}\n"
            f"- TN/FP: {true_negative}/{false_positive}\n"
            f"- Especificidade: {100*specificity:.2f}%\n"
            f"- IC95% Wilson: {100*result['specificity_95_wilson'][0]:.2f}%–{100*result['specificity_95_wilson'][1]:.2f}%\n"
            f"- Tempo máximo: {max(times):.2f} s\n"
            f"- Gate de 180 s: {'PASS' if time_passed else 'FAIL'}\n\n"
            "Este é um estresse secundário de mudança de domínio e classe única. "
            "Não deve ser combinado como matriz primária com LiverHccSeg. O holdout permanece fechado.\n"
        )
        (staging / "report.md").write_text(report, encoding="utf-8")
        _publish_directory(staging, output_dir)
        return result
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
