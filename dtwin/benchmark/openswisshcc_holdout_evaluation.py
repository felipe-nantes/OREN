"""Late-opening same-domain evaluation for the frozen OpenSwissHCC holdout."""
from __future__ import annotations

import json
import math
import shutil
import statistics
import uuid
from pathlib import Path
from typing import Any

from dtwin.benchmark.metrics import wilson_interval
from dtwin.benchmark.openswisshcc import (
    HOLDOUT_SUBJECTS,
    load_subject_labels,
)
from dtwin.benchmark.openswisshcc_alignment import _publish_directory, _sha256
from dtwin.benchmark.openswisshcc_holdout_signals import (
    EXPECTED_CALIBRATOR_SIGNATURE,
    EXPECTED_CASE_COUNT,
    verify_holdout_v21_prediction_freeze,
)
from dtwin.benchmark.public_independent_v21_calibrator import (
    SCORE_SCHEMA,
    SCORE_SUMMARY_SCHEMA,
    _canonical_sha,
)
from dtwin.core import PipelineError
from dtwin.medgemma_screening import _write_json_atomic

LABEL_SCHEMA = "argos-openswisshcc-ground-truth-v1"
LABEL_BUNDLE_SCHEMA = "argos-openswisshcc-holdout-v21-label-authorization-v1"
EVALUATION_SCHEMA = "argos-openswisshcc-holdout-v21-same-domain-evaluation-v1"
# Derived from the official participants.tsv after the authorized late opening.
# For the frozen sub-045..sub-088 holdout, subjects 048..071 have at least one
# HCC=1 row: 24 positive cases and 20 negative cases.  These constants protect
# the cohort against drift; they must never be inferred from predictions.
EXPECTED_POSITIVE_COUNT = 24
EXPECTED_NEGATIVE_COUNT = 20


def _load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PipelineError(f"JSON da avaliacao holdout invalido: {path}") from exc
    if not isinstance(value, dict):
        raise PipelineError("Artefato da avaliacao holdout deve ser objeto JSON.")
    return value


def _jsonl(path: Path) -> list[dict[str, Any]]:
    try:
        rows = [
            json.loads(line)
            for line in Path(path).read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    except (OSError, json.JSONDecodeError) as exc:
        raise PipelineError(f"JSONL da avaliacao holdout invalido: {path}") from exc
    if not rows or any(not isinstance(row, dict) for row in rows):
        raise PipelineError("JSONL da avaliacao holdout vazio ou invalido.")
    return rows


def _write_jsonl_atomic(path: Path, rows: list[dict[str, Any]]) -> None:
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex[:8]}.tmp")
    try:
        temporary.write_text(
            "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows),
            encoding="utf-8",
        )
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def _provenance_mapping(path: Path, expected_case_ids: list[str]) -> dict[str, str]:
    rows = _jsonl(path)
    serialized = json.dumps(rows, ensure_ascii=False, sort_keys=True).lower()
    if any(term in serialized for term in ("label", "truth", "lesion", "diagnosis", "hcc")):
        raise PipelineError("Proveniencia holdout contem dado diagnostico inesperado.")
    mapping: dict[str, str] = {}
    for row in rows:
        case_id = str(row.get("case_id", ""))
        subject = str(row.get("public_subject_id", ""))
        if case_id not in expected_case_ids or subject not in HOLDOUT_SUBJECTS:
            raise PipelineError("Proveniencia holdout contem caso ou sujeito inesperado.")
        previous = mapping.setdefault(case_id, subject)
        if previous != subject:
            raise PipelineError("Case ID holdout aponta para sujeitos publicos divergentes.")
    if set(mapping) != set(expected_case_ids) or set(mapping.values()) != set(HOLDOUT_SUBJECTS):
        raise PipelineError("Proveniencia holdout nao cobre exatamente a coorte congelada.")
    if len(set(mapping.values())) != EXPECTED_CASE_COUNT:
        raise PipelineError("Mapeamento protegido holdout nao e bijetivo.")
    return mapping


def materialize_holdout_v21_labels_after_freeze(
    *,
    context: dict[str, Any],
    raw_signal_root: Path,
    score_root: Path,
    freeze_path: Path,
    authorized_protocol_signature: str,
    participants_path: Path,
    protected_provenance_path: Path,
    output_dir: Path,
    allow_protected_holdout_labels: bool = False,
) -> dict[str, Any]:
    """Open only participants.tsv after the blind predictions/protocol are signed."""

    if allow_protected_holdout_labels is not True:
        raise PipelineError("Abertura dos labels protegidos do holdout nao foi autorizada.")
    freeze = verify_holdout_v21_prediction_freeze(
        context=context,
        raw_signal_root=raw_signal_root,
        score_root=score_root,
        freeze_path=freeze_path,
        expected_protocol_signature=str(authorized_protocol_signature),
    )
    participants_path = Path(participants_path).resolve()
    provenance_path = Path(protected_provenance_path).resolve()
    if participants_path.name != "participants.tsv" or not participants_path.is_file():
        raise PipelineError("Avaliacao holdout aceita somente o participants.tsv oficial.")
    if provenance_path.name != "source_map.jsonl" or not provenance_path.is_file():
        raise PipelineError("Mapa protegido do holdout ausente ou inesperado.")
    mapping = _provenance_mapping(provenance_path, context["case_ids"])

    # This is the first protected-label read and occurs only after all blind gates.
    labels_by_subject = load_subject_labels(participants_path)
    rows = []
    for case_id in context["case_ids"]:
        subject = mapping[case_id]
        rows.append(
            {
                "schema": LABEL_SCHEMA,
                "case_id": case_id,
                "public_subject_id": subject,
                "label": labels_by_subject[subject].label,
                "target_condition": "hcc_presence",
                "label_basis": "openswisshcc_participants_tsv",
                "review_status": "dataset_expert_validated",
            }
        )
    positive = sum(row["label"] == "POSITIVE" for row in rows)
    negative = sum(row["label"] == "NEGATIVE" for row in rows)
    if (positive, negative) != (EXPECTED_POSITIVE_COUNT, EXPECTED_NEGATIVE_COUNT):
        raise PipelineError(
            f"Distribuicao protegida holdout inesperada: positive={positive}, negative={negative}."
        )

    output_dir = Path(output_dir).resolve()
    if output_dir.exists():
        raise PipelineError("Bundle protegido de labels holdout ja existe.")
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    staging = output_dir.parent / f"._holdout_labels_{uuid.uuid4().hex[:8]}"
    staging.mkdir()
    try:
        labels_path = staging / "holdout_labels.jsonl"
        _write_jsonl_atomic(labels_path, rows)
        authorization: dict[str, Any] = {
            "schema": LABEL_BUNDLE_SCHEMA,
            "status": "protected_labels_opened_after_prediction_and_protocol_freeze",
            "case_count": EXPECTED_CASE_COUNT,
            "positive_count": EXPECTED_POSITIVE_COUNT,
            "negative_count": EXPECTED_NEGATIVE_COUNT,
            "case_ids": context["case_ids"],
            "prediction_protocol_signature": freeze["protocol_signature"],
            "prediction_freeze_sha256": _sha256(Path(freeze_path).resolve()),
            "score_summary_sha256": _sha256(Path(score_root).resolve() / "summary.json"),
            "scores_sha256": _sha256(Path(score_root).resolve() / "scores.jsonl"),
            "participants_tsv_sha256": _sha256(participants_path),
            "protected_provenance_sha256": _sha256(provenance_path),
            "holdout_labels_sha256": _sha256(labels_path),
            "labels_opened_after_freeze": True,
            "lesion_masks_read": 0,
            "lesion_masks_used": False,
            "research_only": True,
            "clinical_use_allowed": False,
            "requires_human_review": True,
        }
        authorization["authorization_signature"] = _canonical_sha(authorization)
        _write_json_atomic(staging / "authorization.json", authorization)
        _publish_directory(staging, output_dir)
        return authorization
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def _verify_label_bundle(
    *,
    bundle_root: Path,
    freeze: dict[str, Any],
    score_root: Path,
    expected_case_ids: list[str],
    authorized_protocol_signature: str,
) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    bundle_root = Path(bundle_root).resolve()
    authorization_path = bundle_root / "authorization.json"
    labels_path = bundle_root / "holdout_labels.jsonl"
    authorization = _load(authorization_path)
    unsigned = {
        key: value for key, value in authorization.items() if key != "authorization_signature"
    }
    if (
        authorization.get("schema") != LABEL_BUNDLE_SCHEMA
        or authorization.get("status")
        != "protected_labels_opened_after_prediction_and_protocol_freeze"
        or authorization.get("authorization_signature") != _canonical_sha(unsigned)
        or authorization.get("case_count") != EXPECTED_CASE_COUNT
        or authorization.get("positive_count") != EXPECTED_POSITIVE_COUNT
        or authorization.get("negative_count") != EXPECTED_NEGATIVE_COUNT
        or authorization.get("case_ids") != expected_case_ids
        or authorization.get("prediction_protocol_signature") != authorized_protocol_signature
        or authorization.get("prediction_protocol_signature") != freeze["protocol_signature"]
        or authorization.get("prediction_freeze_sha256") != _sha256(Path(freeze["_path"]))
        or authorization.get("score_summary_sha256")
        != _sha256(Path(score_root).resolve() / "summary.json")
        or authorization.get("scores_sha256")
        != _sha256(Path(score_root).resolve() / "scores.jsonl")
        or authorization.get("holdout_labels_sha256") != _sha256(labels_path)
        or authorization.get("labels_opened_after_freeze") is not True
        or authorization.get("lesion_masks_read") != 0
        or authorization.get("lesion_masks_used") is not False
        or authorization.get("research_only") is not True
        or authorization.get("clinical_use_allowed") is not False
    ):
        raise PipelineError("Bundle protegido de labels holdout invalido ou adulterado.")
    rows = _jsonl(labels_path)
    by_id: dict[str, dict[str, Any]] = {}
    required = {
        "schema",
        "case_id",
        "public_subject_id",
        "label",
        "target_condition",
        "label_basis",
        "review_status",
    }
    for row in rows:
        case_id = str(row.get("case_id", ""))
        if (
            set(row) != required
            or row.get("schema") != LABEL_SCHEMA
            or case_id in by_id
            or row.get("public_subject_id") not in HOLDOUT_SUBJECTS
            or row.get("label") not in {"POSITIVE", "NEGATIVE"}
            or row.get("target_condition") != "hcc_presence"
        ):
            raise PipelineError("Registro protegido de label holdout invalido.")
        by_id[case_id] = row
    if list(by_id) != expected_case_ids:
        raise PipelineError("Labels protegidos nao cobrem a coorte na ordem congelada.")
    if (
        sum(row["label"] == "POSITIVE" for row in rows) != EXPECTED_POSITIVE_COUNT
        or sum(row["label"] == "NEGATIVE" for row in rows) != EXPECTED_NEGATIVE_COUNT
    ):
        raise PipelineError("Contagem protegida do holdout divergiu do protocolo.")
    return by_id, authorization


def _auc(positive_scores: list[float], negative_scores: list[float]) -> float:
    if not positive_scores or not negative_scores:
        raise PipelineError("ROC-AUC holdout exige as duas classes.")
    favorable = 0.0
    for positive in positive_scores:
        for negative in negative_scores:
            favorable += 1.0 if positive > negative else 0.5 if positive == negative else 0.0
    return favorable / (len(positive_scores) * len(negative_scores))


def evaluate_holdout_v21_same_domain(
    *,
    context: dict[str, Any],
    raw_signal_root: Path,
    score_root: Path,
    freeze_path: Path,
    authorized_protocol_signature: str,
    protected_label_bundle_root: Path,
    output_dir: Path,
    allow_protected_holdout_labels: bool = False,
) -> dict[str, Any]:
    """Calculate final same-domain metrics after the separately authorized opening."""

    if allow_protected_holdout_labels is not True:
        raise PipelineError("Avaliacao dos labels protegidos do holdout nao foi autorizada.")
    freeze_path = Path(freeze_path).resolve()
    freeze = verify_holdout_v21_prediction_freeze(
        context=context,
        raw_signal_root=raw_signal_root,
        score_root=score_root,
        freeze_path=freeze_path,
        expected_protocol_signature=str(authorized_protocol_signature),
    )
    freeze = {**freeze, "_path": str(freeze_path)}
    labels, authorization = _verify_label_bundle(
        bundle_root=protected_label_bundle_root,
        freeze=freeze,
        score_root=score_root,
        expected_case_ids=context["case_ids"],
        authorized_protocol_signature=str(authorized_protocol_signature),
    )
    score_root = Path(score_root).resolve()
    summary = _load(score_root / "summary.json")
    rows = _jsonl(score_root / "scores.jsonl")
    if (
        summary.get("schema") != SCORE_SUMMARY_SCHEMA
        or summary.get("status") != "complete_predictions_frozen_labels_still_closed"
        or summary.get("case_count") != EXPECTED_CASE_COUNT
        or summary.get("case_ids") != context["case_ids"]
        or summary.get("scores_sha256") != _sha256(score_root / "scores.jsonl")
        or summary.get("calibrator_signature") != EXPECTED_CALIBRATOR_SIGNATURE
        or len(rows) != EXPECTED_CASE_COUNT
    ):
        raise PipelineError("Scores holdout divergiram depois da abertura autorizada.")

    tp = tn = fp = fn = 0
    positive_scores: list[float] = []
    negative_scores: list[float] = []
    times: list[float] = []
    case_results = []
    for expected_case_id, row in zip(context["case_ids"], rows, strict=True):
        score = row.get("weighted_ecdf_score")
        elapsed = row.get("total_component_seconds")
        if (
            row.get("schema") != SCORE_SCHEMA
            or row.get("case_id") != expected_case_id
            or row.get("decision") not in {"POSITIVE", "NEGATIVE"}
            or not isinstance(score, (int, float))
            or isinstance(score, bool)
            or not math.isfinite(float(score))
            or not isinstance(elapsed, (int, float))
            or isinstance(elapsed, bool)
            or not math.isfinite(float(elapsed))
            or float(elapsed) < 0
            or row.get("calibrator_signature") != EXPECTED_CALIBRATOR_SIGNATURE
        ):
            raise PipelineError("Predicao individual holdout invalida na avaliacao.")
        truth = str(labels[expected_case_id]["label"])
        decision = str(row["decision"])
        tp += truth == "POSITIVE" and decision == "POSITIVE"
        fn += truth == "POSITIVE" and decision == "NEGATIVE"
        tn += truth == "NEGATIVE" and decision == "NEGATIVE"
        fp += truth == "NEGATIVE" and decision == "POSITIVE"
        (positive_scores if truth == "POSITIVE" else negative_scores).append(float(score))
        times.append(float(elapsed))
        case_results.append(
            {
                "case_id": expected_case_id,
                "truth": truth,
                "decision": decision,
                "weighted_ecdf_score": float(score),
                "total_component_seconds": float(elapsed),
                "time_gate_180_seconds_passed": row.get("time_gate_180_seconds_passed") is True,
            }
        )
    sensitivity = tp / (tp + fn)
    specificity = tn / (tn + fp)
    accuracy = (tp + tn) / EXPECTED_CASE_COUNT
    ordered_times = sorted(times)
    p95 = ordered_times[max(0, math.ceil(0.95 * len(ordered_times)) - 1)]
    sensitivity_passed = sensitivity >= 0.75
    specificity_passed = specificity >= 0.75
    time_passed = max(times) <= 180.0 and all(
        item["time_gate_180_seconds_passed"] for item in case_results
    )
    qualified = sensitivity_passed and specificity_passed and time_passed
    result = {
        "schema": EVALUATION_SCHEMA,
        "status": "same_domain_holdout_evaluated_after_authorized_late_opening",
        "case_count": EXPECTED_CASE_COUNT,
        "positive_count": EXPECTED_POSITIVE_COUNT,
        "negative_count": EXPECTED_NEGATIVE_COUNT,
        "confusion_matrix": {"tp": tp, "tn": tn, "fp": fp, "fn": fn},
        "accuracy": accuracy,
        "sensitivity": sensitivity,
        "specificity": specificity,
        "accuracy_95_wilson": wilson_interval(tp + tn, EXPECTED_CASE_COUNT),
        "sensitivity_95_wilson": wilson_interval(tp, EXPECTED_POSITIVE_COUNT),
        "specificity_95_wilson": wilson_interval(tn, EXPECTED_NEGATIVE_COUNT),
        "roc_auc": _auc(positive_scores, negative_scores),
        "timing_seconds": {
            "mean": statistics.fmean(times),
            "median": statistics.median(times),
            "p95_nearest_rank": p95,
            "maximum": max(times),
        },
        "gates": {
            "minimum_sensitivity": 0.75,
            "minimum_specificity": 0.75,
            "maximum_case_seconds": 180.0,
            "sensitivity_passed": sensitivity_passed,
            "specificity_passed": specificity_passed,
            "time_passed": time_passed,
            "qualified": qualified,
        },
        "qualified": qualified,
        "case_results": case_results,
        "prediction_protocol_signature": authorized_protocol_signature,
        "label_authorization_signature": authorization["authorization_signature"],
        "source_hashes": {
            "prediction_freeze_sha256": _sha256(freeze_path),
            "score_summary_sha256": _sha256(score_root / "summary.json"),
            "scores_sha256": _sha256(score_root / "scores.jsonl"),
            "label_authorization_sha256": _sha256(
                Path(protected_label_bundle_root).resolve() / "authorization.json"
            ),
            "protected_labels_sha256": _sha256(
                Path(protected_label_bundle_root).resolve() / "holdout_labels.jsonl"
            ),
        },
        "labels_opened_only_after_predictions_and_protocol_frozen": True,
        "lesion_masks_read": 0,
        "lesion_masks_used": False,
        "research_only": True,
        "clinical_use_allowed": False,
        "requires_human_review": True,
    }
    output_dir = Path(output_dir).resolve()
    if output_dir.exists():
        raise PipelineError("Avaliacao same-domain do holdout ja existe.")
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    staging = output_dir.parent / f"._holdout_eval_{uuid.uuid4().hex[:8]}"
    staging.mkdir()
    try:
        _write_json_atomic(staging / "evaluation.json", result)
        report = (
            "# OpenSwissHCC holdout v21 — avaliação same-domain\n\n"
            f"- Casos: {EXPECTED_CASE_COUNT} ({EXPECTED_POSITIVE_COUNT} positivos, "
            f"{EXPECTED_NEGATIVE_COUNT} negativos)\n"
            f"- TP/TN/FP/FN: {tp}/{tn}/{fp}/{fn}\n"
            f"- Sensibilidade: {100*sensitivity:.2f}%\n"
            f"- Especificidade: {100*specificity:.2f}%\n"
            f"- Acurácia: {100*accuracy:.2f}%\n"
            f"- ROC-AUC: {result['roc_auc']:.4f}\n"
            f"- Tempo máximo: {max(times):.2f} s\n"
            f"- Gate 75%/75%/180 s: {'PASS' if qualified else 'FAIL'}\n\n"
            "Resultado experimental de pesquisa; revisão humana continua obrigatória.\n"
        )
        (staging / "report.md").write_text(report, encoding="utf-8")
        _publish_directory(staging, output_dir)
        return result
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
