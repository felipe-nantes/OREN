"""Phase-10 robustness diagnostics over an already-frozen nested-OOF candidate.

Read-only relative to any candidate's frozen ``prediction_freeze.json`` +
``oof_predictions.jsonl`` (Phase 5, Phase 13 stages, or the new multi-signal
fusion — they all share that shape). Labels are re-opened only here, at
evaluation time, exactly like every other evaluator in this package; nothing
computed here can leak back into a candidate's own score.

Three diagnostics, all candidate-agnostic:

- ``leave_one_dataset_out``: metrics computed separately per ``dataset_id``,
  using data already present on every prediction row — no new label source.
- ``bootstrap_confidence_interval``: patient-grouped bootstrap (resampling by
  ``patient_group_id``, never by loose case) for a 95% CI that respects the
  same "one paciente, one vote" rule used throughout the split generator.
- ``subgroup_metrics``: breakdown by ``negative_subtype`` / ``positive_subtype``
  / ``phenotype_tags``, joined from the protected label source only at this
  evaluation step. Coverage is reported honestly: several of this protocol's
  label sources do not populate clinical subtypes, and this module says so
  instead of assuming full coverage.
"""
from __future__ import annotations

import json
import math
import random
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

from dtwin.core import PipelineError
from dtwin.learning.protocol import canonical_sha256, load_protected_cases, sha256_file
from dtwin.learning.schemas import ProtectedTrainingCase


def _json(path: Path, description: str) -> Any:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PipelineError(f"{description} ausente ou inválido: {path}") from exc


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
        raise PipelineError(f"{description} contém registro inválido.")
    return rows


def load_frozen_oof_predictions(root: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Generic loader: works across any candidate that follows the project's
    ``prediction_freeze.json`` + ``oof_predictions.jsonl`` + ``prediction_signature``
    convention (Phase 5, every Phase 13 stage, the multi-signal fusion)."""
    freeze = _json(Path(root) / "prediction_freeze.json", f"Freeze do candidato {root}")
    unsigned = dict(freeze)
    signature = unsigned.pop("prediction_signature", None)
    if signature != canonical_sha256(unsigned):
        raise PipelineError(f"Assinatura do candidato diverge em {root}.")
    predictions_path = Path(root) / "oof_predictions.jsonl"
    if freeze.get("oof_predictions_sha256") != sha256_file(predictions_path):
        raise PipelineError(f"Predições do candidato foram alteradas em {root}.")
    if freeze.get("held_out_labels_used_for_fit_or_threshold") is not False:
        raise PipelineError(f"Candidato usou label do holdout na seleção em {root}.")
    rows = _jsonl(predictions_path, f"Predições do candidato {root}")
    if any("label" in row or "ground_truth" in row for row in rows):
        raise PipelineError(f"Predições do candidato contêm ground truth em {root}.")
    return freeze, rows


def _wilson(successes: int, total: int) -> list[float]:
    if total <= 0:
        return [0.0, 0.0]
    z = 1.959963984540054
    proportion = successes / total
    denominator = 1 + z * z / total
    center = (proportion + z * z / (2 * total)) / denominator
    margin = z * math.sqrt(proportion * (1 - proportion) / total + z * z / (4 * total * total)) / denominator
    return [max(0.0, center - margin), min(1.0, center + margin)]


def _auc(labels: list[int], scores: list[float]) -> float | None:
    positives = [score for label, score in zip(labels, scores) if label == 1]
    negatives = [score for label, score in zip(labels, scores) if label == 0]
    if not positives or not negatives:
        return None
    wins = sum(1.0 if p > n else 0.5 if p == n else 0.0 for p in positives for n in negatives)
    return wins / (len(positives) * len(negatives))


def _metrics_for(
    rows: list[dict[str, Any]], protected_by_id: dict[str, ProtectedTrainingCase]
) -> dict[str, Any]:
    tp = tn = fp = fn = failures = 0
    auc_labels: list[int] = []
    auc_scores: list[float] = []
    for row in rows:
        label = int(protected_by_id[str(row["case_id"])].label == "POSITIVE")
        if row.get("technical_failure") is True:
            failures += 1
            if label:
                fn += 1
            else:
                fp += 1
            continue
        prediction = row.get("prediction")
        if prediction == "POSITIVE" and label:
            tp += 1
        elif prediction == "NEGATIVE" and not label:
            tn += 1
        elif label:
            fn += 1
        else:
            fp += 1
        if row.get("score") is not None:
            auc_labels.append(label)
            auc_scores.append(float(row["score"]))
    sensitivity = tp / (tp + fn) if tp + fn else 0.0
    specificity = tn / (tn + fp) if tn + fp else 0.0
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
        "roc_auc_computable_cases": _auc(auc_labels, auc_scores),
        "sensitivity_ci95_wilson": _wilson(tp, tp + fn),
        "specificity_ci95_wilson": _wilson(tn, tn + fp),
        "passed_75_75": sensitivity >= 0.75 and specificity >= 0.75,
    }


def leave_one_dataset_out(
    rows: list[dict[str, Any]], protected_by_id: dict[str, ProtectedTrainingCase]
) -> dict[str, dict[str, Any]]:
    covered = {str(row["case_id"]) for row in rows}
    datasets = sorted({protected_by_id[cid].dataset_id for cid in covered})
    return {
        dataset_id: _metrics_for(
            [row for row in rows if protected_by_id[str(row["case_id"])].dataset_id == dataset_id],
            protected_by_id,
        )
        for dataset_id in datasets
    }


def _percentile(sorted_samples: list[float], fraction: float) -> float:
    if not sorted_samples:
        return 0.0
    index = min(len(sorted_samples) - 1, max(0, round(fraction * (len(sorted_samples) - 1))))
    return sorted_samples[index]


def bootstrap_confidence_interval(
    rows: list[dict[str, Any]],
    protected_by_id: dict[str, ProtectedTrainingCase],
    *,
    n_resamples: int = 2000,
    seed: int = 20260724,
) -> dict[str, Any]:
    """Patient-grouped bootstrap: resample whole patient groups with
    replacement (never individual cases), matching the same "no case moves
    independently of its patient" rule enforced by ``splits.py``."""
    by_group: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        group_id = protected_by_id[str(row["case_id"])].patient_group_id
        by_group[group_id].append(row)
    groups = sorted(by_group)
    if not groups:
        raise PipelineError("Bootstrap requer ao menos um grupo de paciente.")
    rng = random.Random(seed)
    sensitivities: list[float] = []
    specificities: list[float] = []
    for _ in range(n_resamples):
        chosen_groups = [groups[rng.randrange(len(groups))] for _ in groups]
        resampled_rows = [row for group_id in chosen_groups for row in by_group[group_id]]
        metrics = _metrics_for(resampled_rows, protected_by_id)
        sensitivities.append(metrics["sensitivity"])
        specificities.append(metrics["specificity"])
    sensitivities.sort()
    specificities.sort()
    return {
        "n_resamples": n_resamples,
        "seed": seed,
        "patient_group_count": len(groups),
        "sensitivity_bootstrap_ci95": [
            _percentile(sensitivities, 0.025),
            _percentile(sensitivities, 0.975),
        ],
        "specificity_bootstrap_ci95": [
            _percentile(specificities, 0.025),
            _percentile(specificities, 0.975),
        ],
    }


def subgroup_metrics(
    rows: list[dict[str, Any]], protected_by_id: dict[str, ProtectedTrainingCase]
) -> dict[str, Any]:
    covered = [row for row in rows if str(row["case_id"]) in protected_by_id]
    negative_rows = [row for row in covered if protected_by_id[str(row["case_id"])].label == "NEGATIVE"]
    positive_rows = [row for row in covered if protected_by_id[str(row["case_id"])].label == "POSITIVE"]

    negative_subtype_values = sorted(
        {
            protected_by_id[str(row["case_id"])].negative_subtype
            for row in negative_rows
            if protected_by_id[str(row["case_id"])].negative_subtype
        }
    )
    positive_subtype_values = sorted(
        {
            protected_by_id[str(row["case_id"])].positive_subtype
            for row in positive_rows
            if protected_by_id[str(row["case_id"])].positive_subtype
        }
    )
    phenotype_tag_values = sorted(
        {
            tag
            for row in covered
            for tag in protected_by_id[str(row["case_id"])].phenotype_tags
        }
    )

    by_negative_subtype = {
        value: _metrics_for(
            [row for row in negative_rows if protected_by_id[str(row["case_id"])].negative_subtype == value],
            protected_by_id,
        )
        for value in negative_subtype_values
    }
    by_positive_subtype = {
        value: _metrics_for(
            [row for row in positive_rows if protected_by_id[str(row["case_id"])].positive_subtype == value],
            protected_by_id,
        )
        for value in positive_subtype_values
    }
    by_phenotype_tag = {
        tag: _metrics_for(
            [row for row in covered if tag in protected_by_id[str(row["case_id"])].phenotype_tags],
            protected_by_id,
        )
        for tag in phenotype_tag_values
    }

    negative_with_subtype = sum(
        1 for row in negative_rows if protected_by_id[str(row["case_id"])].negative_subtype
    )
    positive_with_subtype = sum(
        1 for row in positive_rows if protected_by_id[str(row["case_id"])].positive_subtype
    )
    with_phenotype_tag = sum(
        1 for row in covered if protected_by_id[str(row["case_id"])].phenotype_tags
    )

    return {
        "by_negative_subtype": by_negative_subtype,
        "by_positive_subtype": by_positive_subtype,
        "by_phenotype_tag": by_phenotype_tag,
        "coverage": {
            "negative_case_count": len(negative_rows),
            "negative_cases_with_subtype": negative_with_subtype,
            "negative_subtype_coverage_fraction": (
                negative_with_subtype / len(negative_rows) if negative_rows else None
            ),
            "positive_case_count": len(positive_rows),
            "positive_cases_with_subtype": positive_with_subtype,
            "positive_subtype_coverage_fraction": (
                positive_with_subtype / len(positive_rows) if positive_rows else None
            ),
            "case_count": len(covered),
            "cases_with_phenotype_tag": with_phenotype_tag,
            "phenotype_tag_coverage_fraction": (with_phenotype_tag / len(covered) if covered else None),
        },
    }


def evaluate_robustness(
    *,
    candidate_root: Path,
    training_protocol_config_path: Path,
    workspace_root: Path,
    n_resamples: int = 2000,
    seed: int = 20260724,
) -> dict[str, Any]:
    """Run every Phase-10 diagnostic over one frozen candidate and return a
    single JSON-serializable report. Does not write any file — callers decide
    the output location, so this stays reusable both from the CLI and from
    tests."""
    freeze, rows = load_frozen_oof_predictions(candidate_root)
    protected_by_id = {
        case.case_id: case
        for case in load_protected_cases(training_protocol_config_path, workspace_root)
    }
    covered_ids = {str(row["case_id"]) for row in rows}
    if not covered_ids <= set(protected_by_id):
        raise PipelineError("Candidato cita caso fora do protocolo protegido.")

    overall = _metrics_for(rows, protected_by_id)
    lodo = leave_one_dataset_out(rows, protected_by_id)
    bootstrap = bootstrap_confidence_interval(
        rows, protected_by_id, n_resamples=n_resamples, seed=seed
    )
    subgroups = subgroup_metrics(rows, protected_by_id)

    body = {
        "schema": "argos-hybrid-robustness-report-v1",
        "candidate_id": freeze.get("candidate_id"),
        "candidate_prediction_signature": freeze.get("prediction_signature"),
        "overall": overall,
        "leave_one_dataset_out": lodo,
        "bootstrap": bootstrap,
        "subgroups": subgroups,
        "stability": {
            "worst_dataset_sensitivity": min(
                (metrics["sensitivity"] for metrics in lodo.values()), default=None
            ),
            "worst_dataset_specificity": min(
                (metrics["specificity"] for metrics in lodo.values()), default=None
            ),
            "all_datasets_pass_75_75": all(metrics["passed_75_75"] for metrics in lodo.values())
            if lodo
            else None,
        },
        "research_only": True,
        "clinical_use_allowed": False,
    }
    return {**body, "report_signature": canonical_sha256(body)}


def render_markdown_report(report: dict[str, Any]) -> str:
    overall = report["overall"]
    lines = [
        f"# Robustez — {report.get('candidate_id')}",
        "",
        "## Geral",
        "",
        f"- sensibilidade: {100*overall['sensitivity']:.2f}% "
        f"(IC95% Wilson {100*overall['sensitivity_ci95_wilson'][0]:.2f}–{100*overall['sensitivity_ci95_wilson'][1]:.2f}%)",
        f"- especificidade: {100*overall['specificity']:.2f}% "
        f"(IC95% Wilson {100*overall['specificity_ci95_wilson'][0]:.2f}–{100*overall['specificity_ci95_wilson'][1]:.2f}%)",
        f"- AUC (casos computáveis): {overall['roc_auc_computable_cases']}",
        f"- gate 75/75: {'APROVADO' if overall['passed_75_75'] else 'REPROVADO'}",
        "",
        "## Bootstrap por paciente (IC95%)",
        "",
        f"- sensibilidade: {100*report['bootstrap']['sensitivity_bootstrap_ci95'][0]:.2f}"
        f"–{100*report['bootstrap']['sensitivity_bootstrap_ci95'][1]:.2f}%",
        f"- especificidade: {100*report['bootstrap']['specificity_bootstrap_ci95'][0]:.2f}"
        f"–{100*report['bootstrap']['specificity_bootstrap_ci95'][1]:.2f}%",
        f"- resamples: {report['bootstrap']['n_resamples']}, "
        f"grupos de paciente: {report['bootstrap']['patient_group_count']}",
        "",
        "## Leave-one-dataset-out",
        "",
        "| Dataset | Casos | Sensibilidade | Especificidade | AUC | Gate |",
        "|---|---:|---:|---:|---:|---|",
    ]
    for dataset_id, metrics in sorted(report["leave_one_dataset_out"].items()):
        lines.append(
            f"| {dataset_id} | {metrics['case_count']} | {100*metrics['sensitivity']:.2f}% | "
            f"{100*metrics['specificity']:.2f}% | {metrics['roc_auc_computable_cases']} | "
            f"{'OK' if metrics['passed_75_75'] else 'FALHA'} |"
        )
    lines.extend(
        [
            "",
            f"Pior sensibilidade entre datasets: {report['stability']['worst_dataset_sensitivity']}",
            f"Pior especificidade entre datasets: {report['stability']['worst_dataset_specificity']}",
            f"Todos os datasets no gate 75/75: {report['stability']['all_datasets_pass_75_75']}",
            "",
            "## Cobertura de subtipo clínico",
            "",
            f"- negative_subtype: {report['subgroups']['coverage']['negative_subtype_coverage_fraction']}",
            f"- positive_subtype: {report['subgroups']['coverage']['positive_subtype_coverage_fraction']}",
            f"- phenotype_tags: {report['subgroups']['coverage']['phenotype_tag_coverage_fraction']}",
        ]
    )
    if report["subgroups"]["by_negative_subtype"]:
        lines += ["", "### Negativos por subtipo", "", "| Subtipo | Casos | Especificidade |", "|---|---:|---:|"]
        for name, metrics in sorted(report["subgroups"]["by_negative_subtype"].items()):
            lines.append(f"| {name} | {metrics['case_count']} | {100*metrics['specificity']:.2f}% |")
    if report["subgroups"]["by_positive_subtype"]:
        lines += ["", "### Positivos por subtipo", "", "| Subtipo | Casos | Sensibilidade |", "|---|---:|---:|"]
        for name, metrics in sorted(report["subgroups"]["by_positive_subtype"].items()):
            lines.append(f"| {name} | {metrics['case_count']} | {100*metrics['sensitivity']:.2f}% |")
    return "\n".join(lines) + "\n"
