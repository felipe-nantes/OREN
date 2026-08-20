"""Pre-declared development evaluation for the OpenSwissHCC v10 lesion localizer."""
from __future__ import annotations

import csv
import hashlib
import json
import math
import shutil
import uuid
from pathlib import Path
from typing import Any

from dtwin.benchmark.openswisshcc_alignment import _publish_directory, _sha256
from dtwin.benchmark.openswisshcc_lesion_localizer import CASE_SCHEMA, TASK
from dtwin.benchmark.openswisshcc_lesion_localizer_chunks import MERGED_RUN_SCHEMA
from dtwin.benchmark.openswisshcc_localizer_roi_evaluation import _wilson
from dtwin.benchmark.openswisshcc_volumetric_evaluation import (
    _best_threshold,
    _loocv,
    _repeated_stratified_cv,
)
from dtwin.core import PipelineError
from dtwin.medgemma_screening import _write_json_atomic

PROTOCOL_SCHEMA = "argos-openswisshcc-lesion-localizer-evaluation-protocol-v1"
EVALUATION_SCHEMA = "argos-openswisshcc-lesion-localizer-development-evaluation-v1"
PRIMARY_FEATURE = "candidate_total_volume_log1p"


def _load(path: Path) -> Any:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PipelineError(f"JSON da avaliacao do localizador v10 invalido: {path}") from exc


def _canonical(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _validate_blind_localizer_run(run_root: Path, expected_case_count: int) -> tuple[dict[str, Any], dict[str, float]]:
    root = Path(run_root).resolve()
    summary_path = root / "summary.json"
    summary = _load(summary_path)
    if (
        not isinstance(summary, dict)
        or summary.get("schema") != MERGED_RUN_SCHEMA
        or summary.get("status") != "complete_scores_only_no_decision"
        or summary.get("case_count") != expected_case_count
        or summary.get("task") != TASK
        or summary.get("all_cases_within_90_seconds") is not True
        or summary.get("ground_truth_lesion_mask_used") is not False
        or summary.get("ground_truth_read") is not False
        or summary.get("metrics_calculated") is not False
        or summary.get("final_decision") is not None
        or summary.get("research_only") is not True
        or summary.get("clinical_use_allowed") is not False
    ):
        raise PipelineError("Run full87 do localizador nao esta completo e cego.")
    case_ids = summary.get("case_ids")
    if not isinstance(case_ids, list) or len(case_ids) != expected_case_count or len(set(case_ids)) != len(case_ids):
        raise PipelineError("Lista de casos do run full87 e invalida.")
    visible = sorted(path.name for path in root.iterdir() if path.is_dir() and not path.name.startswith("."))
    if visible != sorted(case_ids):
        raise PipelineError("Run full87 nao cobre exatamente os casos declarados.")
    values: dict[str, float] = {}
    for case_id in case_ids:
        manifest_path = root / case_id / "localizer_manifest.json"
        manifest = _load(manifest_path)
        features = manifest.get("features") if isinstance(manifest, dict) else None
        volume = features.get("total_candidate_volume_mm3") if isinstance(features, dict) else None
        if (
            manifest.get("schema") != CASE_SCHEMA
            or manifest.get("case_id") != case_id
            or manifest.get("status") != "candidate_scores_only_no_decision"
            or manifest.get("task") != summary["task"]
            or manifest.get("model_version") != summary["model_version"]
            or manifest.get("within_90_seconds") is not True
            or manifest.get("ground_truth_lesion_mask_used") is not False
            or manifest.get("ground_truth_read") is not False
            or manifest.get("metrics_calculated") is not False
            or manifest.get("final_decision") is not None
            or not isinstance(volume, (int, float))
            or not math.isfinite(float(volume))
            or float(volume) < 0
        ):
            raise PipelineError(f"Caso full87 invalido antes dos labels: {case_id}.")
        values[case_id] = math.log1p(float(volume))
    return summary, values


def create_evaluation_protocol(
    *, run_root: Path, output_path: Path, expected_case_count: int = 87
) -> dict[str, Any]:
    """Freeze one feature and one analysis before protected labels are opened."""
    summary, values = _validate_blind_localizer_run(run_root, expected_case_count)
    output = Path(output_path).resolve()
    if output.exists():
        raise PipelineError("Protocolo de avaliacao do localizador v10 ja existe.")
    payload = {
        "schema": PROTOCOL_SCHEMA,
        "status": "frozen_before_protected_labels",
        "case_count": expected_case_count,
        "case_ids": list(summary["case_ids"]),
        "run_summary_sha256": _sha256(Path(run_root).resolve() / "summary.json"),
        "selection_signature": summary["selection_signature"],
        "model_version": summary["model_version"],
        "primary_feature": PRIMARY_FEATURE,
        "feature_definition": "log1p(total_candidate_volume_mm3)",
        "direction": "higher_is_positive",
        "threshold_selection": "maximize_minimum_sensitivity_specificity_then_balanced_accuracy_on_training_only",
        "primary_estimator": "leave_one_out_cross_validation",
        "secondary_estimator": "repeated_stratified_5fold_50_repeats_seed_20260714",
        "confidence_intervals": "wilson_95_percent_on_loocv_confusion_matrix",
        "development_gate": {"minimum_sensitivity": 0.75, "minimum_specificity": 0.75},
        "feature_vector_sha256": _canonical([[case_id, values[case_id]] for case_id in summary["case_ids"]]),
        "ground_truth_read": False,
        "metrics_calculated": False,
        "holdout_opened": False,
        "research_only": True,
        "clinical_use_allowed": False,
        "requires_human_review": True,
    }
    payload["protocol_signature"] = _canonical(payload)
    output.parent.mkdir(parents=True, exist_ok=True)
    _write_json_atomic(output, payload)
    return payload


def verify_evaluation_protocol(
    *, run_root: Path, protocol_path: Path, expected_case_count: int = 87
) -> tuple[dict[str, Any], dict[str, Any], dict[str, float]]:
    summary, values = _validate_blind_localizer_run(run_root, expected_case_count)
    protocol = _load(protocol_path)
    signed = {key: value for key, value in protocol.items() if key != "protocol_signature"}
    expected_vector = _canonical([[case_id, values[case_id]] for case_id in summary["case_ids"]])
    if (
        not isinstance(protocol, dict)
        or protocol.get("schema") != PROTOCOL_SCHEMA
        or protocol.get("status") != "frozen_before_protected_labels"
        or protocol.get("protocol_signature") != _canonical(signed)
        or protocol.get("case_count") != expected_case_count
        or protocol.get("case_ids") != summary["case_ids"]
        or protocol.get("run_summary_sha256") != _sha256(Path(run_root).resolve() / "summary.json")
        or protocol.get("selection_signature") != summary["selection_signature"]
        or protocol.get("model_version") != summary["model_version"]
        or protocol.get("primary_feature") != PRIMARY_FEATURE
        or protocol.get("feature_definition") != "log1p(total_candidate_volume_mm3)"
        or protocol.get("feature_vector_sha256") != expected_vector
        or protocol.get("ground_truth_read") is not False
        or protocol.get("metrics_calculated") is not False
        or protocol.get("holdout_opened") is not False
    ):
        raise PipelineError("Protocolo congelado do localizador v10 e invalido ou divergiu do run.")
    return protocol, summary, values


def _load_development_labels(path: Path, expected_case_ids: list[str]) -> tuple[dict[str, dict[str, Any]], str]:
    resolved = Path(path).resolve()
    if resolved.name != "development_labels.jsonl" or resolved.parent.name != "protected_ground_truth" or "holdout" in str(resolved).lower():
        raise PipelineError("Apenas o arquivo protegido de labels de desenvolvimento e autorizado.")
    try:
        rows = [json.loads(line) for line in resolved.read_text(encoding="utf-8").splitlines() if line.strip()]
    except (OSError, json.JSONDecodeError) as exc:
        raise PipelineError("Labels protegidos de desenvolvimento invalidos.") from exc
    required = {"schema", "case_id", "public_subject_id", "label", "target_condition", "label_basis", "review_status"}
    by_id: dict[str, dict[str, Any]] = {}
    for row in rows:
        if (
            not isinstance(row, dict)
            or set(row) != required
            or row.get("schema") != "argos-openswisshcc-ground-truth-v1"
            or row.get("label") not in {"POSITIVE", "NEGATIVE"}
            or row.get("target_condition") != "hcc_presence"
        ):
            raise PipelineError("Registro protegido de desenvolvimento incompativel.")
        case_id = str(row.get("case_id", ""))
        if not case_id.startswith("anon-") or case_id in by_id:
            raise PipelineError("Labels de desenvolvimento possuem ID invalido ou duplicado.")
        by_id[case_id] = row
    if any(case_id not in by_id for case_id in expected_case_ids):
        raise PipelineError("Labels protegidos nao cobrem o run full87.")
    return {case_id: by_id[case_id] for case_id in expected_case_ids}, _sha256(resolved)


def evaluate_full_development(
    *,
    run_root: Path,
    protocol_path: Path,
    labels_path: Path,
    output_dir: Path,
    allow_protected_development_labels: bool = False,
    expected_case_count: int = 87,
) -> dict[str, Any]:
    """Evaluate only after an explicit development-label authorization flag."""
    protocol, summary, values_by_id = verify_evaluation_protocol(
        run_root=run_root, protocol_path=protocol_path, expected_case_count=expected_case_count
    )
    if allow_protected_development_labels is not True:
        raise PipelineError("Abertura dos labels protegidos de desenvolvimento nao foi autorizada explicitamente.")
    output = Path(output_dir).resolve()
    if output.exists():
        raise PipelineError("Avaliacao full87 do localizador v10 ja existe.")
    labels, labels_hash = _load_development_labels(labels_path, list(summary["case_ids"]))
    case_ids = list(summary["case_ids"])
    scores = [values_by_id[case_id] for case_id in case_ids]
    truth = [labels[case_id]["label"] == "POSITIVE" for case_id in case_ids]
    positive_count = sum(truth)
    negative_count = len(truth) - positive_count
    if positive_count == 0 or negative_count == 0:
        raise PipelineError("Desenvolvimento full87 precisa conter positivos e negativos.")
    threshold, apparent = _best_threshold(scores, truth)
    loocv = _loocv(scores, truth)
    repeated = _repeated_stratified_cv(scores, truth, repeats=50, folds=5)
    result = {
        "schema": EVALUATION_SCHEMA,
        "status": "development_calibration_not_holdout_qualified",
        "case_count": expected_case_count,
        "positive_count": positive_count,
        "negative_count": negative_count,
        "primary_feature": PRIMARY_FEATURE,
        "apparent_threshold_for_future_freeze": threshold,
        "apparent_metrics": apparent,
        "primary_loocv_metrics": loocv,
        "repeated_stratified_5fold": repeated,
        "loocv_confidence_intervals": {
            "sensitivity_95": _wilson(loocv["tp"], loocv["tp"] + loocv["fn"]),
            "specificity_95": _wilson(loocv["tn"], loocv["tn"] + loocv["fp"]),
        },
        "development_gate_passed": loocv["sensitivity"] >= 0.75 and loocv["specificity"] >= 0.75,
        "protocol_signature": protocol["protocol_signature"],
        "run_summary_sha256": protocol["run_summary_sha256"],
        "protected_development_labels_sha256": labels_hash,
        "threshold_selected_using_development_labels": True,
        "holdout_opened": False,
        "qualified": False,
        "ground_truth_read": True,
        "metrics_calculated": True,
        "research_only": True,
        "clinical_use_allowed": False,
        "requires_human_review": True,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    staging = output.parent / f"._l10eval_{uuid.uuid4().hex[:8]}"
    staging.mkdir()
    try:
        _write_json_atomic(staging / "evaluation.json", result)
        with (staging / "case_features.csv").open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=["case_id", "label", PRIMARY_FEATURE])
            writer.writeheader()
            for case_id in case_ids:
                writer.writerow({"case_id": case_id, "label": labels[case_id]["label"], PRIMARY_FEATURE: values_by_id[case_id]})
        _publish_directory(staging, output)
        return result
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
