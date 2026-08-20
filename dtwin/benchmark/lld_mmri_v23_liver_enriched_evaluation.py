"""Post-freeze evaluation for the label-blind LLD-MMRI liver-enriched run."""
from __future__ import annotations

import json
import math
import shutil
import uuid
from pathlib import Path
from typing import Any

from dtwin.benchmark.lld_mmri_v23_download import _load_and_validate_protocol
from dtwin.benchmark.lld_mmri_v23_evaluation import LABEL_SCHEMA
from dtwin.benchmark.lld_mmri_v23_liver_enriched_timing import (
    verify_liver_enriched_timing_run,
)
from dtwin.benchmark.metrics import wilson_interval
from dtwin.benchmark.openswisshcc_alignment import _publish_directory, _sha256
from dtwin.benchmark.openswisshcc_v20_fusion import _canonical_sha
from dtwin.core import PipelineError
from dtwin.medgemma_screening import _write_json_atomic

EVALUATION_PROTOCOL_SCHEMA = (
    "argos-lld-mmri-v23-liver-enriched-evaluation-protocol-v1"
)
PREDICTION_SCHEMA = "argos-lld-mmri-v23-liver-enriched-frozen-prediction-v1"
PREDICTION_RUN_SCHEMA = (
    "argos-lld-mmri-v23-liver-enriched-frozen-prediction-batch-v1"
)
EVALUATION_SCHEMA = "argos-lld-mmri-v23-liver-enriched-evaluation-v1"
SCORE_RULE = "max_panel_choice_probability_positiva_v1"
DECISION_MAPPING = {
    "POSITIVA": "POSITIVE",
    "NEGATIVA": "NEGATIVE",
    "INCONCLUSIVA": "INCONCLUSIVE",
}


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


def _unsigned_signature(value: dict[str, Any], field: str, label: str) -> str:
    unsigned = dict(value)
    signature = unsigned.pop(field, None)
    if not isinstance(signature, str) or signature != _canonical_sha(unsigned):
        raise PipelineError(f"Assinatura de {label} invalida.")
    return signature


def _validate_probability_set(value: Any) -> dict[str, float]:
    if not isinstance(value, dict) or set(value) != set(DECISION_MAPPING):
        raise PipelineError("Probabilidades de escolha MedGemma incompletas.")
    result: dict[str, float] = {}
    for key in DECISION_MAPPING:
        item = value[key]
        if (
            isinstance(item, bool)
            or not isinstance(item, (int, float))
            or not math.isfinite(float(item))
            or not 0.0 <= float(item) <= 1.0
        ):
            raise PipelineError("Probabilidade de escolha MedGemma invalida.")
        result[key] = float(item)
    if not math.isclose(sum(result.values()), 1.0, rel_tol=0.0, abs_tol=2e-5):
        raise PipelineError("Probabilidades de escolha MedGemma nao somam um.")
    return result


def _score_from_report(report: dict[str, Any]) -> tuple[float, list[float]]:
    panel_reports = report.get("panel_reports")
    if not isinstance(panel_reports, list) or not panel_reports:
        raise PipelineError("Relatorio MedGemma sem respostas por painel.")
    positive_probabilities: list[float] = []
    for expected_number, panel in enumerate(panel_reports, start=1):
        if (
            not isinstance(panel, dict)
            or panel.get("panel_number") != expected_number
            or panel.get("panel_total") != len(panel_reports)
        ):
            raise PipelineError("Ordem dos paines MedGemma invalida.")
        audit = panel.get("response_validation_audit")
        if not isinstance(audit, dict):
            raise PipelineError("Auditoria de resposta MedGemma ausente.")
        probabilities = _validate_probability_set(audit.get("choice_probabilities"))
        positive_probabilities.append(probabilities["POSITIVA"])
    return max(positive_probabilities), positive_probabilities


def _validate_evaluation_protocol(
    *, evaluation_protocol_path: Path, public_protocol: dict[str, Any],
    timing_protocol: dict[str, Any], timing_verification: dict[str, Any],
) -> dict[str, Any]:
    protocol = _load(evaluation_protocol_path, "Protocolo de avaliacao liver-enriched")
    signature = _unsigned_signature(
        protocol, "evaluation_protocol_signature", "protocolo de avaliacao liver-enriched"
    )
    technical_ids = timing_protocol.get("technical_failure_case_ids")
    expected_ids = [
        case_id for case_id in public_protocol["case_ids"]
        if case_id not in set(technical_ids or [])
    ]
    if (
        protocol.get("schema") != EVALUATION_PROTOCOL_SCHEMA
        or protocol.get("status") != "frozen_before_public_labels_opened"
        or protocol.get("protocol_case_count") != public_protocol["case_count"]
        or protocol.get("inference_eligible_case_count") != len(expected_ids)
        or protocol.get("inference_eligible_case_ids") != expected_ids
        or protocol.get("technical_failure_case_ids") != technical_ids
        or protocol.get("technical_failure_case_count") != len(technical_ids or [])
        or protocol.get("technical_failures_count_as_primary_metric_errors") is not True
        or protocol.get("inconclusive_counts_as_primary_metric_error") is not True
        or protocol.get("decision_mapping") != DECISION_MAPPING
        or protocol.get("score_rule") != SCORE_RULE
        or protocol.get("score_used_for_discrete_decision") is not False
        or protocol.get("roc_auc_scope") != "inference_eligible_cases_only"
        or protocol.get("sensitivity_threshold") != 0.75
        or protocol.get("specificity_threshold") != 0.75
        or protocol.get("public_protocol_signature")
        != public_protocol["protocol_signature"]
        or protocol.get("source_timing_protocol_signature")
        != timing_protocol.get("protocol_signature")
        or protocol.get("source_run_signature")
        != timing_verification.get("run_signature")
        or protocol.get("protected_labels_sha256")
        != public_protocol.get("protected_labels_sha256")
        or protocol.get("labels_opened") is not False
        or protocol.get("lesion_masks_read") != 0
        or protocol.get("research_only") is not True
        or protocol.get("clinical_use_allowed") is not False
    ):
        raise PipelineError("Protocolo de avaliacao liver-enriched invalido.")
    protocol["evaluation_protocol_signature"] = signature
    return protocol


def freeze_liver_enriched_evaluation_protocol(
    *, protocol_root: Path, panel_root: Path, gallery_root: Path,
    review_path: Path, config_path: Path, timing_protocol_path: Path,
    timing_output_root: Path, output_path: Path,
) -> dict[str, Any]:
    """Freeze label-independent evaluation and score rules before labels open."""
    public_protocol, _ = _load_and_validate_protocol(protocol_root)
    timing_verification = verify_liver_enriched_timing_run(
        panel_root=panel_root, gallery_root=gallery_root, review_path=review_path,
        config_path=config_path, protocol_path=timing_protocol_path,
        output_root=timing_output_root,
    )
    timing_protocol = _load(timing_protocol_path, "Protocolo temporal liver-enriched")
    _unsigned_signature(timing_protocol, "protocol_signature", "protocolo temporal")
    technical_ids = timing_protocol.get("technical_failure_case_ids")
    if not isinstance(technical_ids, list) or len(technical_ids) != len(set(technical_ids)):
        raise PipelineError("Falhas tecnicas liver-enriched invalidas.")
    failure_set = set(technical_ids)
    eligible_ids = [
        case_id for case_id in public_protocol["case_ids"] if case_id not in failure_set
    ]
    timing_case_ids = [str(item.get("case_id")) for item in timing_protocol.get("cases", [])]
    if (
        public_protocol["case_count"] != len(eligible_ids) + len(technical_ids)
        or timing_case_ids != eligible_ids
        or timing_verification.get("case_count") != len(eligible_ids)
        or timing_verification.get("protocol_case_count") != public_protocol["case_count"]
        or timing_verification.get("technical_failure_case_count") != len(technical_ids)
        or timing_verification.get("ground_truth_read") is not False
        or timing_verification.get("lesion_masks_read") != 0
    ):
        raise PipelineError("Coorte temporal divergiu do protocolo publico LLD-MMRI.")
    output_path = Path(output_path).resolve()
    if output_path.exists():
        raise PipelineError("Protocolo de avaliacao liver-enriched ja existe.")
    base = {
        "schema": EVALUATION_PROTOCOL_SCHEMA,
        "status": "frozen_before_public_labels_opened",
        "protocol_case_count": public_protocol["case_count"],
        "inference_eligible_case_count": len(eligible_ids),
        "inference_eligible_case_ids": eligible_ids,
        "technical_failure_case_count": len(technical_ids),
        "technical_failure_case_ids": technical_ids,
        "technical_failures_excluded_from_inference": True,
        "technical_failures_count_as_primary_metric_errors": True,
        "inconclusive_counts_as_primary_metric_error": True,
        "decision_mapping": DECISION_MAPPING,
        "score_rule": SCORE_RULE,
        "score_used_for_discrete_decision": False,
        "roc_auc_scope": "inference_eligible_cases_only",
        "primary_metrics": ["sensitivity", "specificity"],
        "secondary_metrics": [
            "confusion_matrix", "wilson_95_intervals", "roc_auc",
            "balanced_accuracy", "overall_accuracy", "subtype_metrics",
        ],
        "sensitivity_threshold": 0.75,
        "specificity_threshold": 0.75,
        "public_protocol_signature": public_protocol["protocol_signature"],
        "source_timing_protocol_signature": timing_protocol["protocol_signature"],
        "source_review_signature": timing_verification["review_signature"],
        "source_run_signature": timing_verification["run_signature"],
        "protected_labels_sha256": public_protocol["protected_labels_sha256"],
        "panel_set_180_second_gate_required": True,
        "full_dicom_end_to_end_gate_required_for_final_qualification": True,
        "full_dicom_end_to_end_gate_available": False,
        "labels_opened": False,
        "ground_truth_read": False,
        "lesion_masks_read": 0,
        "research_only": True,
        "clinical_use_allowed": False,
        "requires_human_review": True,
    }
    result = {**base, "evaluation_protocol_signature": _canonical_sha(base)}
    output_path.parent.mkdir(parents=True, exist_ok=True)
    _write_json_atomic(output_path, result)
    return result


def _source_rows(
    *, timing_output_root: Path, eligible_ids: list[str]
) -> list[tuple[dict[str, Any], dict[str, Any], dict[str, Any]]]:
    root = Path(timing_output_root).resolve()
    timing_rows = _jsonl(root / "cases.jsonl", "Casos temporais liver-enriched")
    if [str(row.get("case_id")) for row in timing_rows] != eligible_ids:
        raise PipelineError("Ordem dos casos temporais liver-enriched divergiu.")
    result = []
    for timing_row in timing_rows:
        case_id = str(timing_row["case_id"])
        report_path = root / case_id / "medgemma_report.json"
        manifest_path = root / case_id / "timing_manifest.json"
        report = _load(report_path, f"Relatorio MedGemma {case_id}")
        manifest = _load(manifest_path, f"Manifesto temporal {case_id}")
        if (
            _sha256(report_path) != timing_row.get("report_sha256")
            or _sha256(report_path) != manifest.get("report_sha256")
            or manifest.get("case_id") != case_id
            or manifest.get("prediction") != timing_row.get("prediction")
            or report.get("case_id") != case_id
        ):
            raise PipelineError("Fonte MedGemma liver-enriched adulterada.")
        result.append((timing_row, manifest, report))
    return result


def freeze_liver_enriched_predictions(
    *, protocol_root: Path, panel_root: Path, gallery_root: Path,
    review_path: Path, config_path: Path, timing_protocol_path: Path,
    timing_output_root: Path, evaluation_protocol_path: Path, output_root: Path,
) -> dict[str, Any]:
    """Freeze discrete predictions and continuous scores without opening labels."""
    public_protocol, _ = _load_and_validate_protocol(protocol_root)
    timing_verification = verify_liver_enriched_timing_run(
        panel_root=panel_root, gallery_root=gallery_root, review_path=review_path,
        config_path=config_path, protocol_path=timing_protocol_path,
        output_root=timing_output_root,
    )
    timing_protocol = _load(timing_protocol_path, "Protocolo temporal liver-enriched")
    evaluation_protocol = _validate_evaluation_protocol(
        evaluation_protocol_path=evaluation_protocol_path,
        public_protocol=public_protocol, timing_protocol=timing_protocol,
        timing_verification=timing_verification,
    )
    eligible_ids = list(evaluation_protocol["inference_eligible_case_ids"])
    output_root = Path(output_root).resolve()
    if output_root.exists():
        raise PipelineError("Predicoes liver-enriched ja existem; sobrescrita recusada.")
    output_root.parent.mkdir(parents=True, exist_ok=True)
    staging = output_root.parent / f"._lld_liver_predictions_{uuid.uuid4().hex[:8]}"
    staging.mkdir()
    predictions: list[dict[str, Any]] = []
    try:
        for timing_row, manifest, report in _source_rows(
            timing_output_root=timing_output_root, eligible_ids=eligible_ids
        ):
            source_decision = str(timing_row["prediction"])
            if source_decision not in DECISION_MAPPING:
                raise PipelineError("Decisao MedGemma liver-enriched invalida.")
            score, panel_positive_probabilities = _score_from_report(report)
            base = {
                "schema": PREDICTION_SCHEMA,
                "case_id": timing_row["case_id"],
                "prediction": DECISION_MAPPING[source_decision],
                "source_prediction": source_decision,
                "score": score,
                "score_rule": SCORE_RULE,
                "panel_positive_probabilities": panel_positive_probabilities,
                "panel_image_count": manifest["panel_image_count"],
                "elapsed_seconds": manifest["elapsed_seconds"],
                "within_180_seconds": manifest["within_time_limit"],
                "source_report_sha256": manifest["report_sha256"],
                "source_case_signature": timing_row["case_signature"],
                "source_run_signature": timing_verification["run_signature"],
                "evaluation_protocol_signature": evaluation_protocol[
                    "evaluation_protocol_signature"
                ],
                "public_protocol_signature": public_protocol["protocol_signature"],
                "ground_truth_read": False,
                "metrics_calculated": False,
                "research_only": True,
                "clinical_use_allowed": False,
                "requires_human_review": True,
            }
            predictions.append({**base, "prediction_signature": _canonical_sha(base)})
        predictions_path = staging / "predictions.jsonl"
        predictions_path.write_text(
            "".join(
                json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n"
                for row in predictions
            ),
            encoding="utf-8",
        )
        counts = {key: 0 for key in {"POSITIVE", "NEGATIVE", "INCONCLUSIVE"}}
        for row in predictions:
            counts[row["prediction"]] += 1
        base = {
            "schema": PREDICTION_RUN_SCHEMA,
            "status": "frozen_complete_predictions_before_labels",
            "protocol_case_count": public_protocol["case_count"],
            "case_count": len(predictions),
            "case_ids": eligible_ids,
            "technical_failure_case_count": evaluation_protocol[
                "technical_failure_case_count"
            ],
            "technical_failure_case_ids": evaluation_protocol[
                "technical_failure_case_ids"
            ],
            "technical_failures_excluded_from_inference": True,
            "technical_failures_count_as_primary_metric_errors": True,
            "inconclusive_counts_as_primary_metric_error": True,
            "prediction_counts": counts,
            "predictions_sha256": _sha256(predictions_path),
            "score_rule": SCORE_RULE,
            "source_run_signature": timing_verification["run_signature"],
            "evaluation_protocol_signature": evaluation_protocol[
                "evaluation_protocol_signature"
            ],
            "public_protocol_signature": public_protocol["protocol_signature"],
            "predictions_frozen": True,
            "ground_truth_read": False,
            "metrics_calculated": False,
            "qualified": False,
            "research_only": True,
            "clinical_use_allowed": False,
            "requires_human_review": True,
        }
        summary = {**base, "prediction_run_signature": _canonical_sha(base)}
        _write_json_atomic(staging / "summary.json", summary)
        _publish_directory(staging, output_root)
        return summary
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def verify_liver_enriched_predictions(
    *, protocol_root: Path, panel_root: Path, gallery_root: Path,
    review_path: Path, config_path: Path, timing_protocol_path: Path,
    timing_output_root: Path, evaluation_protocol_path: Path,
    prediction_root: Path,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Recompute the prediction freeze from signed, label-blind source artifacts."""
    public_protocol, _ = _load_and_validate_protocol(protocol_root)
    timing_verification = verify_liver_enriched_timing_run(
        panel_root=panel_root, gallery_root=gallery_root, review_path=review_path,
        config_path=config_path, protocol_path=timing_protocol_path,
        output_root=timing_output_root,
    )
    timing_protocol = _load(timing_protocol_path, "Protocolo temporal liver-enriched")
    evaluation_protocol = _validate_evaluation_protocol(
        evaluation_protocol_path=evaluation_protocol_path,
        public_protocol=public_protocol, timing_protocol=timing_protocol,
        timing_verification=timing_verification,
    )
    prediction_root = Path(prediction_root).resolve()
    summary = _load(prediction_root / "summary.json", "Resumo das predicoes")
    summary_signature = _unsigned_signature(
        summary, "prediction_run_signature", "predicoes liver-enriched"
    )
    rows = _jsonl(prediction_root / "predictions.jsonl", "Predicoes liver-enriched")
    eligible_ids = list(evaluation_protocol["inference_eligible_case_ids"])
    sources = _source_rows(timing_output_root=timing_output_root, eligible_ids=eligible_ids)
    if (
        summary.get("schema") != PREDICTION_RUN_SCHEMA
        or summary.get("status") != "frozen_complete_predictions_before_labels"
        or summary.get("protocol_case_count") != public_protocol["case_count"]
        or summary.get("case_count") != len(eligible_ids)
        or summary.get("case_ids") != eligible_ids
        or summary.get("technical_failure_case_ids")
        != evaluation_protocol["technical_failure_case_ids"]
        or summary.get("technical_failure_case_count")
        != evaluation_protocol["technical_failure_case_count"]
        or summary.get("technical_failures_count_as_primary_metric_errors") is not True
        or summary.get("inconclusive_counts_as_primary_metric_error") is not True
        or summary.get("predictions_sha256")
        != _sha256(prediction_root / "predictions.jsonl")
        or summary.get("score_rule") != SCORE_RULE
        or summary.get("source_run_signature") != timing_verification["run_signature"]
        or summary.get("evaluation_protocol_signature")
        != evaluation_protocol["evaluation_protocol_signature"]
        or summary.get("predictions_frozen") is not True
        or summary.get("ground_truth_read") is not False
        or summary.get("metrics_calculated") is not False
        or summary.get("qualified") is not False
        or len(rows) != len(eligible_ids)
    ):
        raise PipelineError("Resumo das predicoes liver-enriched invalido.")
    counts = {key: 0 for key in {"POSITIVE", "NEGATIVE", "INCONCLUSIVE"}}
    for case_id, row, source in zip(eligible_ids, rows, sources, strict=True):
        timing_row, manifest, report = source
        unsigned = dict(row)
        row_signature = unsigned.pop("prediction_signature", None)
        score, panel_scores = _score_from_report(report)
        expected_prediction = DECISION_MAPPING[str(timing_row["prediction"])]
        if (
            row.get("schema") != PREDICTION_SCHEMA
            or row.get("case_id") != case_id
            or row_signature != _canonical_sha(unsigned)
            or row.get("prediction") != expected_prediction
            or row.get("source_prediction") != timing_row["prediction"]
            or row.get("score") != score
            or row.get("score_rule") != SCORE_RULE
            or row.get("panel_positive_probabilities") != panel_scores
            or row.get("panel_image_count") != manifest["panel_image_count"]
            or row.get("source_report_sha256") != manifest["report_sha256"]
            or row.get("source_case_signature") != timing_row["case_signature"]
            or row.get("source_run_signature") != timing_verification["run_signature"]
            or row.get("evaluation_protocol_signature")
            != evaluation_protocol["evaluation_protocol_signature"]
            or row.get("ground_truth_read") is not False
            or row.get("metrics_calculated") is not False
        ):
            raise PipelineError("Predicao liver-enriched invalida ou adulterada.")
        counts[row["prediction"]] += 1
    if summary.get("prediction_counts") != counts:
        raise PipelineError("Contagem das predicoes liver-enriched divergiu.")
    summary["prediction_run_signature"] = summary_signature
    return summary, rows


def _auc(positive_scores: list[float], negative_scores: list[float]) -> float | None:
    if not positive_scores or not negative_scores:
        return None
    favorable = 0.0
    for positive in positive_scores:
        for negative in negative_scores:
            favorable += 1.0 if positive > negative else 0.5 if positive == negative else 0.0
    return favorable / (len(positive_scores) * len(negative_scores))


def evaluate_liver_enriched_predictions(
    *, protocol_root: Path, panel_root: Path, gallery_root: Path,
    review_path: Path, config_path: Path, timing_protocol_path: Path,
    timing_output_root: Path, evaluation_protocol_path: Path,
    prediction_root: Path, protected_labels_path: Path, output_root: Path,
    allow_protected_public_labels: bool = False,
) -> dict[str, Any]:
    """Open labels only after a complete independent prediction verification."""
    if allow_protected_public_labels is not True:
        raise PipelineError("Abertura dos labels publicos LLD-MMRI nao autorizada.")
    public_protocol, _ = _load_and_validate_protocol(protocol_root)
    prediction_summary, predictions = verify_liver_enriched_predictions(
        protocol_root=protocol_root, panel_root=panel_root, gallery_root=gallery_root,
        review_path=review_path, config_path=config_path,
        timing_protocol_path=timing_protocol_path,
        timing_output_root=timing_output_root,
        evaluation_protocol_path=evaluation_protocol_path,
        prediction_root=prediction_root,
    )
    evaluation_protocol = _load(
        evaluation_protocol_path, "Protocolo de avaliacao liver-enriched"
    )
    labels_path = Path(protected_labels_path).resolve()
    if _sha256(labels_path) != evaluation_protocol.get("protected_labels_sha256"):
        raise PipelineError("Hash dos labels protegidos LLD-MMRI divergiu.")
    # This is the first protected-label parse and occurs only after full freeze verification.
    labels = _jsonl(labels_path, "Labels protegidos LLD-MMRI")
    if len(labels) != public_protocol["case_count"]:
        raise PipelineError("Labels protegidos nao cobrem a coorte LLD-MMRI.")
    by_id = {str(row["case_id"]): row for row in predictions}
    failure_ids = list(prediction_summary["technical_failure_case_ids"])
    failure_set = set(failure_ids)
    tp = tn = fp = fn = 0
    inconclusive_count = 0
    failure_positive = failure_negative = 0
    positive_scores: list[float] = []
    negative_scores: list[float] = []
    subtype: dict[str, dict[str, int]] = {}
    results: list[dict[str, Any]] = []
    for expected_id, label in zip(public_protocol["case_ids"], labels, strict=True):
        truth = label.get("label")
        subtype_name = str(label.get("subtype", ""))
        if (
            label.get("schema") != LABEL_SCHEMA
            or label.get("case_id") != expected_id
            or truth not in {"POSITIVE", "NEGATIVE"}
            or not subtype_name
            or label.get("target_condition") != public_protocol["target_condition"]
            or label.get("research_only") is not True
            or label.get("clinical_use_allowed") is not False
        ):
            raise PipelineError("Label protegido LLD-MMRI invalido ou fora de ordem.")
        prediction = by_id.get(expected_id)
        technical_failure = expected_id in failure_set
        if technical_failure:
            if prediction is not None:
                raise PipelineError("Falha tecnica possui predicao indevida.")
            decision = "TECHNICAL_FAILURE"
            score = None
            if truth == "POSITIVE":
                fn += 1
                failure_positive += 1
            else:
                fp += 1
                failure_negative += 1
        else:
            if prediction is None:
                raise PipelineError("Caso elegivel sem predicao congelada.")
            decision = str(prediction["prediction"])
            score = float(prediction["score"])
            if truth == "POSITIVE":
                positive_scores.append(score)
                if decision == "POSITIVE":
                    tp += 1
                else:
                    fn += 1
            else:
                negative_scores.append(score)
                if decision == "NEGATIVE":
                    tn += 1
                else:
                    fp += 1
            inconclusive_count += decision == "INCONCLUSIVE"
        group = subtype.setdefault(subtype_name, {"total": 0, "correct": 0})
        group["total"] += 1
        group["correct"] += decision == truth
        results.append({
            "case_id": expected_id, "truth": truth, "subtype": subtype_name,
            "prediction": decision, "score": score,
            "technical_failure": technical_failure,
        })
    if tp + fn != public_protocol["positive_count"] or tn + fp != public_protocol["negative_count"]:
        raise PipelineError("Distribuicao protegida LLD-MMRI divergiu do protocolo.")
    sensitivity = tp / (tp + fn)
    specificity = tn / (tn + fp)
    accuracy = (tp + tn) / public_protocol["case_count"]
    balanced_accuracy = (sensitivity + specificity) / 2.0
    accuracy_gate = sensitivity >= 0.75 and specificity >= 0.75
    auc = _auc(positive_scores, negative_scores)
    output_root = Path(output_root).resolve()
    if output_root.exists():
        raise PipelineError("Avaliacao liver-enriched ja existe; sobrescrita recusada.")
    output_root.parent.mkdir(parents=True, exist_ok=True)
    staging = output_root.parent / f"._lld_liver_evaluation_{uuid.uuid4().hex[:8]}"
    staging.mkdir()
    try:
        case_path = staging / "case_results.jsonl"
        case_path.write_text(
            "".join(
                json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n"
                for row in results
            ),
            encoding="utf-8",
        )
        base = {
            "schema": EVALUATION_SCHEMA,
            "status": "complete_external_evaluation_after_prediction_freeze",
            "protocol_case_count": public_protocol["case_count"],
            "inference_eligible_case_count": len(predictions),
            "technical_failure_case_count": len(failure_ids),
            "technical_failure_case_ids": failure_ids,
            "technical_failures_count_as_primary_metric_errors": True,
            "technical_failure_positive_count": failure_positive,
            "technical_failure_negative_count": failure_negative,
            "inconclusive_count": inconclusive_count,
            "inconclusive_counts_as_primary_metric_error": True,
            "positive_count": tp + fn,
            "negative_count": tn + fp,
            "confusion_matrix": {"tp": tp, "tn": tn, "fp": fp, "fn": fn},
            "sensitivity": sensitivity,
            "sensitivity_percent": 100.0 * sensitivity,
            "sensitivity_95_wilson": wilson_interval(tp, tp + fn),
            "specificity": specificity,
            "specificity_percent": 100.0 * specificity,
            "specificity_95_wilson": wilson_interval(tn, tn + fp),
            "overall_accuracy": accuracy,
            "overall_accuracy_percent": 100.0 * accuracy,
            "balanced_accuracy": balanced_accuracy,
            "balanced_accuracy_percent": 100.0 * balanced_accuracy,
            "roc_auc": auc,
            "roc_auc_available": auc is not None,
            "roc_auc_scope": "inference_eligible_cases_only",
            "roc_auc_positive_count": len(positive_scores),
            "roc_auc_negative_count": len(negative_scores),
            "roc_auc_excluded_technical_failure_count": len(failure_ids),
            "subtype_metrics": {
                key: {
                    **value,
                    "accuracy_within_truth_subtype": value["correct"] / value["total"],
                }
                for key, value in sorted(subtype.items())
            },
            "accuracy_gate_75_75_passed": accuracy_gate,
            "panel_set_inference_180_second_gate_passed": True,
            "full_dicom_end_to_end_180_second_gate_available": False,
            "full_dicom_end_to_end_180_second_gate_passed": False,
            "qualified": False,
            "qualification_reason": (
                "full_dicom_end_to_end_gate_pending"
                if accuracy_gate else "accuracy_gate_75_75_not_met"
            ),
            "score_rule": SCORE_RULE,
            "evaluation_protocol_signature": evaluation_protocol[
                "evaluation_protocol_signature"
            ],
            "prediction_run_signature": prediction_summary[
                "prediction_run_signature"
            ],
            "predictions_sha256": prediction_summary["predictions_sha256"],
            "protected_labels_sha256": _sha256(labels_path),
            "case_results_sha256": _sha256(case_path),
            "labels_opened_after_prediction_freeze": True,
            "lesion_masks_read": 0,
            "lesion_masks_used": False,
            "research_only": True,
            "clinical_use_allowed": False,
            "requires_human_review": True,
        }
        summary = {**base, "evaluation_signature": _canonical_sha(base)}
        _write_json_atomic(staging / "summary.json", summary)
        _publish_directory(staging, output_root)
        return summary
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise


__all__ = [
    "EVALUATION_PROTOCOL_SCHEMA", "PREDICTION_SCHEMA", "PREDICTION_RUN_SCHEMA",
    "EVALUATION_SCHEMA", "SCORE_RULE", "freeze_liver_enriched_evaluation_protocol",
    "freeze_liver_enriched_predictions", "verify_liver_enriched_predictions",
    "evaluate_liver_enriched_predictions",
]
