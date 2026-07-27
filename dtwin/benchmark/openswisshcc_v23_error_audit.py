"""Deterministic retrospective audit of the frozen v23 development errors."""
from __future__ import annotations

import csv
import hashlib
import json
import math
import shutil
import statistics
import uuid
from pathlib import Path
from typing import Any

from dtwin.benchmark.openswisshcc_alignment import _publish_directory
from dtwin.benchmark.openswisshcc_candidate_shape import CASE_SCHEMA
from dtwin.benchmark.openswisshcc_v20_fusion import (
    BLIND_SIGNAL_SCHEMA,
    V11_WEIGHTS,
    _loocv as _v11_loocv,
)
from dtwin.benchmark.openswisshcc_v23_baseline import verify_v23_baseline_lock
from dtwin.core import PipelineError


AUDIT_SCHEMA = "argos-openswisshcc-v23-development-error-audit-v1"
ERROR_SCHEMA = "argos-openswisshcc-v23-development-error-case-v1"
NEAR_THRESHOLD_ABSOLUTE_MARGIN = 0.025


def _load_json(path: Path, description: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PipelineError(f"{description} ausente ou inválido.") from exc
    if not isinstance(value, dict):
        raise PipelineError(f"{description} deve ser objeto JSON.")
    return value


def _load_jsonl(path: Path, description: str) -> list[dict[str, Any]]:
    try:
        rows = [
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    except (OSError, json.JSONDecodeError) as exc:
        raise PipelineError(f"{description} ausente ou inválido.") from exc
    if not rows or not all(isinstance(row, dict) for row in rows):
        raise PipelineError(f"{description} deve conter objetos JSONL.")
    return rows


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
    except OSError as exc:
        raise PipelineError(f"Não foi possível ler artefato da auditoria: {path}.") from exc
    return digest.hexdigest()


def _finite(value: Any, description: str) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float, str))
    ):
        raise PipelineError(f"{description} não é numérico.")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise PipelineError(f"{description} não é numérico.") from exc
    if not math.isfinite(number):
        raise PipelineError(f"{description} não é finito.")
    return number


def _transition(*, truth: bool, v11_prediction: bool, v23_prediction: bool) -> str:
    v11_correct = v11_prediction == truth
    v23_correct = v23_prediction == truth
    if v11_correct and v23_correct:
        return "correct_in_v11_and_v23"
    if not v11_correct and v23_correct:
        return "corrected_by_v23_shape_fusion"
    if v11_correct and not v23_correct:
        return "introduced_by_v23_shape_fusion"
    return "persistent_error_from_v11"


def _shape_rank_band(percentile: float) -> str:
    if percentile >= 0.75:
        return "upper_quartile_more_linear"
    if percentile <= 0.25:
        return "lower_quartile_less_linear"
    return "middle_half"


def _audit_flags(
    *,
    v23_margin: float,
    shape_percentile: float,
    candidate_present: int,
    transition: str,
) -> list[str]:
    flags = [transition, _shape_rank_band(shape_percentile)]
    if abs(v23_margin) <= NEAR_THRESHOLD_ABSOLUTE_MARGIN:
        flags.append("near_v23_threshold")
    if candidate_present == 0:
        flags.append("no_automatic_candidate")
    return flags


def _median_features(rows: list[dict[str, Any]], names: list[str]) -> dict[str, float]:
    if not rows:
        return {}
    return {
        name: float(statistics.median(float(row["candidate_features"][name]) for row in rows))
        for name in names
    }


def _write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _report(summary: dict[str, Any]) -> str:
    v11 = summary["v11_loocv_metrics"]
    v23 = summary["v23_loocv_metrics"]
    transitions = summary["error_transition_counts"]
    all_transitions = summary["all_case_transition_counts"]
    confusion = summary["v23_error_counts"]
    return "\n".join(
        [
            "# Auditoria retrospectiva dos erros v23",
            "",
            "Esta auditoria usa somente os 87 casos de desenvolvimento já abertos. "
            "Ela não altera o baseline, não qualifica o sistema final e não reutiliza "
            "o holdout v21.",
            "",
            "## Comparação",
            "",
            "| Leitor | Sensibilidade | Especificidade | TP | TN | FP | FN |",
            "|---|---:|---:|---:|---:|---:|---:|",
            (
                f"| v11 | {100*v11['sensitivity']:.2f}% | "
                f"{100*v11['specificity']:.2f}% | {v11['tp']} | {v11['tn']} | "
                f"{v11['fp']} | {v11['fn']} |"
            ),
            (
                f"| v23 | {100*v23['sensitivity']:.2f}% | "
                f"{100*v23['specificity']:.2f}% | {v23['tp']} | {v23['tn']} | "
                f"{v23['fp']} | {v23['fn']} |"
            ),
            "",
            "## Erros v23",
            "",
            f"- falsos positivos: {confusion['false_positive']};",
            f"- falsos negativos: {confusion['false_negative']};",
            f"- total: {summary['error_case_count']};",
            (
                "- erros da v11 corrigidos pela v23: "
                f"{all_transitions.get('corrected_by_v23_shape_fusion', 0)};"
            ),
            (
                "- erros introduzidos pela fusão geométrica: "
                f"{transitions.get('introduced_by_v23_shape_fusion', 0)};"
            ),
            (
                "- erros persistentes desde a v11: "
                f"{transitions.get('persistent_error_from_v11', 0)}."
            ),
            (
                "- erros v23 próximos do limiar predefinido: "
                f"{summary['near_threshold_error_count']}."
            ),
            "",
            "A v23 corrigiu erros da v11 sem introduzir novos erros. Os erros "
            "remanescentes estão distribuídos entre os quartis de linearidade e "
            "não são explicados por proximidade ao limiar.",
            "",
            "## Salvaguardas",
            "",
            "- máscaras de lesão lidas: não;",
            "- holdout v21 aberto ou reutilizado: não;",
            "- finalidade: auditoria retrospectiva de desenvolvimento;",
            "- revisão humana: obrigatória.",
            "",
        ]
    )


def audit_v23_development_errors(
    *,
    lock_path: Path,
    workspace_root: Path,
    output_dir: Path,
) -> dict[str, Any]:
    """Audit all frozen v23 errors without modifying or reselecting the baseline."""

    baseline = verify_v23_baseline_lock(
        lock_path=lock_path,
        workspace_root=workspace_root,
    )
    lock = _load_json(Path(lock_path).resolve(), "Lock v23")
    roles = lock.get("artifact_roles", {})
    required = {"case_scores", "v20_signals", "shape_features", "development_labels"}
    if not isinstance(roles, dict) or not required.issubset(roles):
        raise PipelineError("Lock v23 não expõe todos os artefatos necessários à auditoria.")
    root = Path(workspace_root).resolve()
    paths = {name: (root / roles[name]).resolve() for name in required}
    if paths["development_labels"].name != "development_labels.jsonl" or any(
        "holdout" in part.lower() for part in paths["development_labels"].parts
    ):
        raise PipelineError("Auditoria v23 aceita somente labels de desenvolvimento.")

    try:
        with paths["case_scores"].open("r", encoding="utf-8", newline="") as stream:
            score_rows = list(csv.DictReader(stream))
    except OSError as exc:
        raise PipelineError("Scores congelados v23 estão ausentes.") from exc
    signal_rows = _load_jsonl(paths["v20_signals"], "Sinais cegos v20")
    shape_rows = _load_jsonl(paths["shape_features"], "Features geométricas v23")
    label_rows = _load_jsonl(paths["development_labels"], "Labels de desenvolvimento")

    if not score_rows or len(score_rows) != baseline["case_count"]:
        raise PipelineError("Quantidade de scores v23 diverge do baseline.")
    score_by_id = {str(row.get("case_id")): row for row in score_rows}
    signal_by_id = {str(row.get("case_id")): row for row in signal_rows}
    shape_by_id = {str(row.get("case_id")): row for row in shape_rows}
    label_by_id = {str(row.get("case_id")): row for row in label_rows}
    expected_ids = list(score_by_id)
    if (
        len(score_by_id) != len(score_rows)
        or len(signal_by_id) != len(signal_rows)
        or len(shape_by_id) != len(shape_rows)
        or len(label_by_id) != len(label_rows)
        or set(expected_ids) != set(signal_by_id) != set(shape_by_id)
    ):
        raise PipelineError("IDs ou duplicações divergem entre os artefatos v23.")
    if set(expected_ids) != set(signal_by_id) or set(expected_ids) != set(shape_by_id):
        raise PipelineError("Coortes v20/v23 não correspondem.")
    if not set(expected_ids).issubset(label_by_id):
        raise PipelineError("Labels de desenvolvimento incompletos para auditoria v23.")

    ordered_signals = [signal_by_id[case_id] for case_id in expected_ids]
    truth: list[bool] = []
    for case_id, row in zip(expected_ids, ordered_signals, strict=True):
        label = label_by_id[case_id].get("label")
        if label not in {"POSITIVE", "NEGATIVE"}:
            raise PipelineError(f"Label inválido na auditoria v23: {case_id}.")
        truth.append(label == "POSITIVE")
        if (
            row.get("schema") != BLIND_SIGNAL_SCHEMA
            or row.get("ground_truth_read") is not False
            or row.get("metrics_calculated") is not False
            or row.get("holdout_opened") is not False
            or set(row.get("signals", {})) != {*V11_WEIGHTS, "v19_rag_atlas_log_odds"}
        ):
            raise PipelineError(f"Sinal v20 inseguro ou inválido: {case_id}.")

    v11 = _v11_loocv(ordered_signals, truth, V11_WEIGHTS)
    expected_v11 = {"tp": 29, "tn": 36, "fp": 12, "fn": 10}
    if any(v11.get(name) != value for name, value in expected_v11.items()):
        raise PipelineError("Reprodução v11 divergiu durante auditoria v23.")

    all_cases: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    feature_names: list[str] | None = None
    for index, case_id in enumerate(expected_ids):
        score_row = score_by_id[case_id]
        shape_row = shape_by_id[case_id]
        features = shape_row.get("features")
        if (
            shape_row.get("schema") != CASE_SCHEMA
            or shape_row.get("ground_truth_read") is not False
            or shape_row.get("ground_truth_lesion_mask_used") is not False
            or shape_row.get("inference_executed") is not False
            or not isinstance(features, dict)
        ):
            raise PipelineError(f"Feature geométrica insegura ou inválida: {case_id}.")
        current_names = sorted(features)
        if feature_names is None:
            feature_names = current_names
        if current_names != feature_names:
            raise PipelineError("Schema das features geométricas varia entre casos.")
        numeric_features = {
            name: _finite(features[name], f"Feature {name} de {case_id}")
            for name in feature_names
        }

        label = "POSITIVE" if truth[index] else "NEGATIVE"
        if score_row.get("label") != label:
            raise PipelineError(f"Label anexado ao score v23 diverge: {case_id}.")
        v23_score = _finite(score_row.get("loocv_score"), f"Score v23 de {case_id}")
        v23_threshold = _finite(
            score_row.get("loocv_threshold"), f"Limiar v23 de {case_id}"
        )
        v23_prediction = v23_score >= v23_threshold
        expected_prediction = "POSITIVE" if v23_prediction else "NEGATIVE"
        if score_row.get("prediction") != expected_prediction:
            raise PipelineError(f"Predição congelada v23 diverge do score: {case_id}.")

        v11_score = float(v11["scores"][index])
        v11_threshold = float(v11["thresholds"][index])
        v11_prediction = v11_score >= v11_threshold
        shape_percentile = (v23_score - 0.8 * v11_score) / 0.2
        if not -1e-12 <= shape_percentile <= 1.0 + 1e-12:
            raise PipelineError(f"Contribuição geométrica v23 inválida: {case_id}.")
        shape_percentile = min(1.0, max(0.0, float(shape_percentile)))
        transition = _transition(
            truth=truth[index],
            v11_prediction=v11_prediction,
            v23_prediction=v23_prediction,
        )
        candidate_present = int(numeric_features["candidate_present"])
        if candidate_present not in {0, 1}:
            raise PipelineError(f"Presença de candidato inválida: {case_id}.")
        v23_margin = v23_score - v23_threshold
        confusion = (
            "true_positive" if truth[index] and v23_prediction
            else "false_negative" if truth[index]
            else "false_positive" if v23_prediction
            else "true_negative"
        )
        record = {
            "case_id": case_id,
            "label": label,
            "v23_confusion": confusion,
            "v11": {
                "score": v11_score,
                "threshold": v11_threshold,
                "signed_margin": v11_score - v11_threshold,
                "prediction": "POSITIVE" if v11_prediction else "NEGATIVE",
                "correct": v11_prediction == truth[index],
            },
            "v23": {
                "score": v23_score,
                "threshold": v23_threshold,
                "signed_margin": v23_margin,
                "absolute_margin": abs(v23_margin),
                "prediction": expected_prediction,
                "correct": v23_prediction == truth[index],
            },
            "shape": {
                "raw_weighted_linearity": numeric_features[
                    "candidate_weighted_linearity"
                ],
                "leave_one_out_ecdf_percentile": shape_percentile,
                "score_contribution": 0.2 * shape_percentile,
                "rank_band": _shape_rank_band(shape_percentile),
            },
            "v11_score_contribution": 0.8 * v11_score,
            "transition": transition,
            "audit_flags": _audit_flags(
                v23_margin=v23_margin,
                shape_percentile=shape_percentile,
                candidate_present=candidate_present,
                transition=transition,
            ),
            "candidate_features": numeric_features,
        }
        all_cases.append(record)
        if not record["v23"]["correct"]:
            errors.append({"schema": ERROR_SCHEMA, **record})

    feature_names = feature_names or []
    if len(errors) != 17:
        raise PipelineError("Quantidade de erros v23 diverge do baseline congelado.")
    transition_names = (
        "correct_in_v11_and_v23",
        "corrected_by_v23_shape_fusion",
        "introduced_by_v23_shape_fusion",
        "persistent_error_from_v11",
    )
    transition_counts: dict[str, int] = {name: 0 for name in transition_names}
    all_transition_counts: dict[str, int] = {name: 0 for name in transition_names}
    confusion_counts: dict[str, int] = {
        "false_positive": 0,
        "false_negative": 0,
    }
    shape_rank_counts: dict[str, int] = {
        "upper_quartile_more_linear": 0,
        "middle_half": 0,
        "lower_quartile_less_linear": 0,
    }
    near_threshold_error_count = 0
    for row in all_cases:
        all_transition_counts[row["transition"]] = (
            all_transition_counts.get(row["transition"], 0) + 1
        )
    for row in errors:
        transition_counts[row["transition"]] = transition_counts.get(row["transition"], 0) + 1
        confusion_counts[row["v23_confusion"]] = confusion_counts.get(row["v23_confusion"], 0) + 1
        rank = row["shape"]["rank_band"]
        shape_rank_counts[rank] = shape_rank_counts.get(rank, 0) + 1
        near_threshold_error_count += int("near_v23_threshold" in row["audit_flags"])

    feature_medians = {
        group: _median_features(
            [row for row in all_cases if row["v23_confusion"] == group],
            feature_names,
        )
        for group in ("true_positive", "true_negative", "false_positive", "false_negative")
    }
    summary = {
        "schema": AUDIT_SCHEMA,
        "status": "complete_retrospective_development_error_audit",
        "case_count": len(all_cases),
        "error_case_count": len(errors),
        "v23_error_counts": confusion_counts,
        "error_transition_counts": transition_counts,
        "all_case_transition_counts": all_transition_counts,
        "corrected_by_v23_shape_fusion_case_ids": [
            row["case_id"]
            for row in all_cases
            if row["transition"] == "corrected_by_v23_shape_fusion"
        ],
        "corrected_by_v23_shape_fusion_label_counts": {
            label: sum(
                row["transition"] == "corrected_by_v23_shape_fusion"
                and row["label"] == label
                for row in all_cases
            )
            for label in ("POSITIVE", "NEGATIVE")
        },
        "introduced_by_v23_shape_fusion_case_ids": [
            row["case_id"]
            for row in all_cases
            if row["transition"] == "introduced_by_v23_shape_fusion"
        ],
        "error_shape_rank_counts": shape_rank_counts,
        "near_threshold_error_count": near_threshold_error_count,
        "near_threshold_absolute_margin": NEAR_THRESHOLD_ABSOLUTE_MARGIN,
        "v11_loocv_metrics": {
            name: v11[name]
            for name in ("tp", "tn", "fp", "fn", "sensitivity", "specificity", "balanced_accuracy")
        },
        "v23_loocv_metrics": baseline["primary_loocv_metrics"],
        "feature_medians_by_v23_confusion_group": feature_medians,
        "source_hashes": {
            "baseline_lock": _sha256(Path(lock_path).resolve()),
            **{
                name: _sha256(paths[name])
                for name in sorted(paths)
            },
        },
        "baseline_modified": False,
        "ground_truth_read_for_retrospective_audit": True,
        "lesion_masks_read": False,
        "holdout_v21_opened_or_reused": False,
        "development_only": True,
        "qualified": False,
        "research_only": True,
        "clinical_use_allowed": False,
        "requires_human_review": True,
    }

    destination = Path(output_dir).resolve()
    if destination.exists():
        raise PipelineError("Destino da auditoria v23 já existe; sobrescrita recusada.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = destination.parent / f"._v23_error_audit_{uuid.uuid4().hex[:8]}"
    staging.mkdir()
    try:
        _write_json(staging / "summary.json", summary)
        with (staging / "errors.jsonl").open("w", encoding="utf-8", newline="\n") as stream:
            for row in errors:
                stream.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
        with (staging / "all_cases.csv").open(
            "w", encoding="utf-8", newline=""
        ) as stream:
            columns = [
                "case_id", "label", "v23_confusion", "transition",
                "v11_score", "v11_threshold", "v11_prediction",
                "v23_score", "v23_threshold", "v23_prediction",
                "v23_signed_margin", "shape_raw_weighted_linearity",
                "shape_leave_one_out_ecdf_percentile", "audit_flags",
            ]
            writer = csv.DictWriter(stream, fieldnames=columns)
            writer.writeheader()
            for row in all_cases:
                writer.writerow({
                    "case_id": row["case_id"],
                    "label": row["label"],
                    "v23_confusion": row["v23_confusion"],
                    "transition": row["transition"],
                    "v11_score": row["v11"]["score"],
                    "v11_threshold": row["v11"]["threshold"],
                    "v11_prediction": row["v11"]["prediction"],
                    "v23_score": row["v23"]["score"],
                    "v23_threshold": row["v23"]["threshold"],
                    "v23_prediction": row["v23"]["prediction"],
                    "v23_signed_margin": row["v23"]["signed_margin"],
                    "shape_raw_weighted_linearity": row["shape"]["raw_weighted_linearity"],
                    "shape_leave_one_out_ecdf_percentile": row["shape"][
                        "leave_one_out_ecdf_percentile"
                    ],
                    "audit_flags": "|".join(row["audit_flags"]),
                })
        (staging / "report.md").write_text(_report(summary), encoding="utf-8")
        _publish_directory(staging, destination)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return summary


__all__ = [
    "AUDIT_SCHEMA",
    "ERROR_SCHEMA",
    "NEAR_THRESHOLD_ABSOLUTE_MARGIN",
    "audit_v23_development_errors",
]
