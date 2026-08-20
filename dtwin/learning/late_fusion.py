"""Frozen late fusion of v23 and the Phase-5 supervised MedSigLIP signal."""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import yaml

from dtwin.core import PipelineError
from dtwin.learning.protocol import canonical_sha256, sha256_file

FUSION_SCHEMA = "argos-hybrid-v23-medsiglip-late-fusion-prediction-v1"
FREEZE_SCHEMA = "argos-hybrid-v23-medsiglip-late-fusion-freeze-v1"
EVALUATION_SCHEMA = "argos-hybrid-v23-medsiglip-late-fusion-evaluation-v1"


def _json(path: Path, description: str) -> dict[str, Any]:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PipelineError(f"{description} ausente ou inválido: {path}") from exc
    if not isinstance(value, dict):
        raise PipelineError(f"{description} deve ser objeto.")
    return value


def _jsonl(path: Path, description: str) -> list[dict[str, Any]]:
    try:
        rows = [
            json.loads(line)
            for line in Path(path).read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    except (OSError, json.JSONDecodeError) as exc:
        raise PipelineError(f"{description} ausente ou inválido: {path}") from exc
    if any(not isinstance(row, dict) for row in rows):
        raise PipelineError(f"{description} contém linha inválida.")
    return rows


def load_fusion_config(path: Path) -> dict[str, Any]:
    try:
        value = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise PipelineError(f"Config de fusão inválida: {path}") from exc
    if not isinstance(value, dict) or value.get("schema") != "argos-hybrid-late-fusion-config-v1":
        raise PipelineError("Schema de fusão inválido.")
    weights = value.get("weights")
    if not isinstance(weights, dict) or set(weights) != {"v23", "medsiglip_phase5"}:
        raise PipelineError("Pesos da fusão incompletos.")
    if not math.isclose(sum(float(item) for item in weights.values()), 1.0, abs_tol=1e-12):
        raise PipelineError("Pesos da fusão devem somar um.")
    if value.get("weight_selection") != "fixed_before_fusion_evaluation":
        raise PipelineError("Pesos devem ser congelados antes da avaliação.")
    if value.get("technical_failures_count_as_errors") is not True:
        raise PipelineError("Falhas técnicas devem contar como erros.")
    return value


def _verify_v23(root: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    summary = _json(root / "summary.json", "Freeze v23")
    predictions_path = root / "loocv_predictions.jsonl"
    if (
        summary.get("schema") != "argos-v23-retrospective-phase4-prediction-freeze-v1"
        or summary.get("status") != "phase4_patient_level_oof_predictions_frozen"
        or summary.get("artifacts", {}).get("loocv_predictions_sha256")
        != sha256_file(predictions_path)
        or summary.get("threshold_fit_on_outer_training_only") is not True
        or summary.get("technical_failures_must_count_as_errors_during_evaluation") is not True
    ):
        raise PipelineError("Fonte OOF v23 não satisfaz o contrato congelado.")
    rows = _jsonl(predictions_path, "Predições v23")
    if len(rows) != 132 or len({row["case_id"] for row in rows}) != 132:
        raise PipelineError("Cobertura v23 divergente.")
    return summary, rows


def _verify_medsiglip(root: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    freeze = _json(root / "prediction_freeze.json", "Freeze MedSigLIP")
    unsigned = dict(freeze)
    signature = unsigned.pop("prediction_signature", None)
    predictions_path = root / "oof_predictions.jsonl"
    if (
        signature != canonical_sha256(unsigned)
        or freeze.get("oof_predictions_sha256") != sha256_file(predictions_path)
        or freeze.get("held_out_labels_used_for_fit_or_threshold") is not False
    ):
        raise PipelineError("Fonte OOF MedSigLIP não satisfaz o contrato congelado.")
    rows = [
        row
        for row in _jsonl(predictions_path, "Predições MedSigLIP")
        if str(row.get("dataset_id", "")).startswith("openswisshcc")
    ]
    if len(rows) != 132 or len({row["case_id"] for row in rows}) != 132:
        raise PipelineError("Cobertura OpenSwissHCC MedSigLIP divergente.")
    return freeze, rows


def build_frozen_fusion(
    *,
    config_path: Path,
    v23_root: Path,
    medsiglip_root: Path,
    output_root: Path,
) -> dict[str, Any]:
    output_root = Path(output_root).resolve()
    if output_root.exists():
        raise PipelineError("Fusão OOF já existe; saída é imutável.")
    output_root.mkdir(parents=True)
    config = load_fusion_config(config_path)
    v23_summary, v23_rows = _verify_v23(Path(v23_root))
    medsiglip_freeze, medsiglip_rows = _verify_medsiglip(Path(medsiglip_root))
    v23 = {str(row["case_id"]): row for row in v23_rows}
    medsiglip = {str(row["case_id"]): row for row in medsiglip_rows}
    if set(v23) != set(medsiglip):
        raise PipelineError("Fontes de fusão não cobrem os mesmos casos.")
    w_v23 = float(config["weights"]["v23"])
    w_medsiglip = float(config["weights"]["medsiglip_phase5"])
    predictions: list[dict[str, Any]] = []
    for case_id in sorted(v23):
        left, right = v23[case_id], medsiglip[case_id]
        technical_failure = (
            left.get("score") is None
            or left.get("status") != "complete_out_of_fold_prediction"
            or right.get("technical_failure") is True
            or right.get("score") is None
        )
        if technical_failure:
            margin = None
            prediction = "TECHNICAL_FAILURE"
        else:
            margin = (
                w_v23 * (float(left["score"]) - float(left["threshold"]))
                + w_medsiglip * (float(right["score"]) - float(right["threshold"]))
            )
            prediction = "POSITIVE" if margin >= 0.0 else "NEGATIVE"
        predictions.append(
            {
                "schema": FUSION_SCHEMA,
                "case_id": case_id,
                "v23_oof_score": left.get("score"),
                "v23_oof_threshold": left.get("threshold"),
                "medsiglip_phase5_oof_score": right.get("score"),
                "medsiglip_phase5_oof_threshold": right.get("threshold"),
                "fused_signed_margin": margin,
                "decision_threshold": 0.0,
                "prediction": prediction,
                "technical_failure": technical_failure,
                "weights": {"v23": w_v23, "medsiglip_phase5": w_medsiglip},
                "ground_truth_in_artifact": False,
                "held_out_label_used_for_fusion": False,
                "research_only": True,
            }
        )
    predictions_path = output_root / "oof_predictions.jsonl"
    predictions_path.write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in predictions),
        encoding="utf-8",
    )
    body = {
        "schema": FREEZE_SCHEMA,
        "status": "frozen_before_final_metric_calculation",
        "candidate_id": str(config["candidate_id"]),
        "config_sha256": sha256_file(config_path),
        "prediction_count": len(predictions),
        "technical_failure_count": sum(row["technical_failure"] for row in predictions),
        "oof_predictions_sha256": sha256_file(predictions_path),
        "v23_prediction_freeze_signature": v23_summary["prediction_freeze_signature"],
        "v23_loocv_predictions_sha256": v23_summary["artifacts"]["loocv_predictions_sha256"],
        "medsiglip_phase5_prediction_signature": medsiglip_freeze["prediction_signature"],
        "medsiglip_phase5_oof_predictions_sha256": medsiglip_freeze["oof_predictions_sha256"],
        "weights": {"v23": w_v23, "medsiglip_phase5": w_medsiglip},
        "weight_or_threshold_selected_from_evaluation_labels": False,
        "individual_ground_truth_persisted": False,
        "lesion_masks_read": 0,
        "research_only": True,
        "clinical_use_allowed": False,
    }
    freeze = {**body, "fusion_signature": canonical_sha256(body)}
    (output_root / "fusion_freeze.json").write_text(
        json.dumps(freeze, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return freeze


def _wilson(successes: int, total: int) -> list[float]:
    z = 1.959963984540054
    p = successes / total
    denominator = 1 + z * z / total
    center = (p + z * z / (2 * total)) / denominator
    margin = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / denominator
    return [max(0.0, center - margin), min(1.0, center + margin)]


def _auc(labels: list[int], scores: list[float]) -> float:
    positives = [score for label, score in zip(labels, scores) if label]
    negatives = [score for label, score in zip(labels, scores) if not label]
    return sum(1.0 if p > n else 0.5 if p == n else 0.0 for p in positives for n in negatives) / (
        len(positives) * len(negatives)
    )


def _metrics(
    rows: list[dict[str, Any]],
    labels: dict[str, str],
    *,
    prediction_key: str = "prediction",
    score_key: str | None = None,
) -> dict[str, Any]:
    tp = tn = fp = fn = failures = 0
    auc_labels: list[int] = []
    auc_scores: list[float] = []
    for row in rows:
        positive = labels[str(row["case_id"])] == "POSITIVE"
        if row.get("technical_failure") is True or row.get(prediction_key) == "TECHNICAL_FAILURE":
            failures += 1
            if positive:
                fn += 1
            else:
                fp += 1
            continue
        predicted = row[prediction_key] == "POSITIVE"
        if positive and predicted:
            tp += 1
        elif not positive and not predicted:
            tn += 1
        elif positive:
            fn += 1
        else:
            fp += 1
        if score_key is not None and row.get(score_key) is not None:
            auc_labels.append(int(positive))
            auc_scores.append(float(row[score_key]))
    sensitivity, specificity = tp / (tp + fn), tn / (tn + fp)
    return {
        "case_count": len(rows),
        "tp": tp,
        "tn": tn,
        "fp": fp,
        "fn": fn,
        "technical_failures": failures,
        "sensitivity": sensitivity,
        "specificity": specificity,
        "balanced_accuracy": (sensitivity + specificity) / 2.0,
        "roc_auc_computable_cases": _auc(auc_labels, auc_scores) if auc_scores else None,
        "sensitivity_ci95_wilson": _wilson(tp, tp + fn),
        "specificity_ci95_wilson": _wilson(tn, tn + fp),
        "passed_75_75": sensitivity >= 0.75 and specificity >= 0.75,
    }


def evaluate_fusion(
    *,
    fusion_root: Path,
    v23_root: Path,
    medsiglip_root: Path,
    development_labels_path: Path,
    holdout_labels_path: Path,
    radiomics_evaluation_path: Path,
    patch_evaluation_path: Path,
    output_root: Path,
) -> dict[str, Any]:
    output_root = Path(output_root).resolve()
    if output_root.exists():
        raise PipelineError("Avaliação da fusão já existe; saída é imutável.")
    output_root.mkdir(parents=True)
    freeze = _json(Path(fusion_root) / "fusion_freeze.json", "Freeze da fusão")
    unsigned = dict(freeze)
    signature = unsigned.pop("fusion_signature", None)
    if signature != canonical_sha256(unsigned):
        raise PipelineError("Assinatura da fusão diverge.")
    predictions_path = Path(fusion_root) / "oof_predictions.jsonl"
    if freeze.get("oof_predictions_sha256") != sha256_file(predictions_path):
        raise PipelineError("Predições da fusão foram alteradas.")
    predictions = _jsonl(predictions_path, "Predições da fusão")
    if any("label" in row or "ground_truth" in row for row in predictions):
        raise PipelineError("Predições da fusão contêm ground truth.")
    labels: dict[str, str] = {}
    for path in (development_labels_path, holdout_labels_path):
        for row in _jsonl(path, "Labels protegidos OpenSwissHCC"):
            labels[str(row["case_id"])] = str(row["label"])
    if set(labels) != {str(row["case_id"]) for row in predictions}:
        raise PipelineError("Labels e fusão não cobrem os mesmos 132 casos.")
    _, v23_rows = _verify_v23(Path(v23_root))
    _, medsiglip_rows = _verify_medsiglip(Path(medsiglip_root))
    v23_normalized = [
        {
            **row,
            "technical_failure": row.get("score") is None,
        }
        for row in v23_rows
    ]
    radiomics_eval = _json(radiomics_evaluation_path, "Avaliação radiômica")
    patch_eval = _json(patch_evaluation_path, "Avaliação 2.5D")
    ablations = {
        "v23_oof_full132": _metrics(v23_normalized, labels, score_key="score"),
        "medsiglip_phase5_oof_full132": _metrics(
            medsiglip_rows, labels, score_key="score"
        ),
        "v23_plus_medsiglip_phase5_fixed_80_20": _metrics(
            predictions, labels, score_key="fused_signed_margin"
        ),
        "radiomics_standalone_multicohort467": {
            **radiomics_eval["overall"],
            "comparable_cohort": False,
            "fusion_eligible": False,
            "reason": "rejected_by_phase7_gate",
        },
        "patch25d_standalone_development87": {
            **patch_eval["overall"],
            "comparable_cohort": False,
            "fusion_eligible": False,
            "reason": "rejected_by_phase8_gate",
        },
        "v23_plus_radiomics": {"executed": False, "reason": "radiomics_rejected_by_phase7_gate"},
        "medsiglip_plus_radiomics": {"executed": False, "reason": "radiomics_rejected_by_phase7_gate"},
        "v23_plus_medsiglip_plus_radiomics": {
            "executed": False,
            "reason": "radiomics_rejected_by_phase7_gate",
        },
        "complete_fusion": {
            "executed": False,
            "reason": "radiomics_and_patch25d_rejected_by_prior_gates",
        },
    }
    primary = ablations["v23_plus_medsiglip_phase5_fixed_80_20"]
    body = {
        "schema": EVALUATION_SCHEMA,
        "candidate_id": freeze["candidate_id"],
        "fusion_signature": freeze["fusion_signature"],
        "primary": primary,
        "ablations": ablations,
        "acceptance": {
            "sensitivity_minimum": 0.75,
            "specificity_minimum": 0.75,
            "passed": primary["passed_75_75"],
        },
        "methodology": {
            "source_scores_out_of_fold": True,
            "weights_frozen_before_metric_calculation": True,
            "threshold_fixed_at_zero_signed_margin": True,
            "technical_failures_count_as_errors": True,
            "retrospective_open_swiss_hcc_132": True,
            "independent_external_validation": False,
        },
        "phase5_preserved_unchanged": True,
        "v23_preserved_unchanged": True,
        "lesion_masks_read": 0,
        "research_only": True,
        "clinical_use_allowed": False,
    }
    evaluation = {**body, "evaluation_signature": canonical_sha256(body)}
    evaluation_path = output_root / "evaluation.json"
    evaluation_path.write_text(
        json.dumps(evaluation, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    report = [
        "# Fase 9 — fusão tardia v23 + MedSigLIP da Fase 5",
        "",
        "| Ablation | Sensibilidade | Especificidade | AUC |",
        "|---|---:|---:|---:|",
    ]
    for key in (
        "v23_oof_full132",
        "medsiglip_phase5_oof_full132",
        "v23_plus_medsiglip_phase5_fixed_80_20",
    ):
        item = ablations[key]
        report.append(
            f"| {key} | {100*item['sensitivity']:.2f}% | "
            f"{100*item['specificity']:.2f}% | "
            f"{item['roc_auc_computable_cases']:.4f} |"
        )
    report.extend(
        [
            "",
            "Radiômica e patches 2.5D foram mantidos como ablations documentadas,",
            "mas não entraram na fusão porque falharam seus gates anteriores.",
            "",
            f"Gate 75/75 da fusão: {'APROVADO' if primary['passed_75_75'] else 'REPROVADO'}.",
        ]
    )
    (output_root / "ablation_report.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    return evaluation
