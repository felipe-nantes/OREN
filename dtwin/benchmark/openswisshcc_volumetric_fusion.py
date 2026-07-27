"""Development-only MedGemma/MedSigLIP signal and fusion robustness analysis."""
from __future__ import annotations

import csv
import json
import random
import statistics
from pathlib import Path
from typing import Any

from dtwin.benchmark.openswisshcc_alignment import _load_json, _sha256
from dtwin.benchmark.openswisshcc_evaluation import _load_labels_after_inference
from dtwin.benchmark.openswisshcc_volumetric_evaluation import (
    _best_threshold,
    _binary_metrics,
    _loocv,
    _repeated_stratified_cv,
)
from dtwin.benchmark.openswisshcc_volumetric_medsiglip import RUN_SCHEMA
from dtwin.core import PipelineError


def _rolling_max(values: list[float], width: int) -> float:
    if not values:
        raise PipelineError("Serie axial MedSigLIP vazia.")
    if len(values) < width:
        return statistics.fmean(values)
    return max(statistics.fmean(values[i:i + width]) for i in range(len(values) - width + 1))


def _medsiglip_features(case_dir: Path) -> dict[str, float]:
    manifest = _load_json(case_dir / "medsiglip_manifest.json")
    scores_path = case_dir / "medsiglip_panel_scores.json"
    if _sha256(scores_path) != manifest.get("scores_sha256"):
        raise PipelineError(f"Hash MedSigLIP divergente: {case_dir.name}.")
    panels = json.loads(scores_path.read_text(encoding="utf-8"))
    axial_by_index: dict[int, float] = {}
    coronal: list[float] = []
    sagittal: list[float] = []
    for panel in panels:
        rows = panel.get("score", {}).get("scores")
        indices = panel.get("axial_indices")
        real_count = panel.get("real_axial_tile_count")
        if (
            not isinstance(rows, list) or len(rows) != 11
            or not isinstance(indices, list) or real_count != len(indices)
        ):
            raise PipelineError(f"Scores/tiles MedSigLIP invalidos: {case_dir.name}.")
        for index, row in zip(indices, rows[:real_count], strict=True):
            if index in axial_by_index:
                raise PipelineError(f"Indice axial MedSigLIP duplicado: {case_dir.name}.")
            axial_by_index[int(index)] = float(row["positive_probability"])
        coronal.append(float(rows[9]["positive_probability"]))
        sagittal.append(float(rows[10]["positive_probability"]))
    axial = [axial_by_index[index] for index in sorted(axial_by_index)]
    ordered = sorted(axial, reverse=True)
    mean = statistics.fmean(axial)
    median = statistics.median(axial)
    top2 = statistics.fmean(ordered[:2])
    top5 = statistics.fmean(ordered[:min(5, len(ordered))])
    return {
        "ms_axial_mean": mean,
        "ms_axial_median": median,
        "ms_axial_max": max(axial),
        "ms_axial_top2_mean": top2,
        "ms_axial_top5_mean": top5,
        "ms_focality_max_minus_median": max(axial) - median,
        "ms_focality_top2_minus_mean": top2 - mean,
        "ms_adjacent2_max_mean": _rolling_max(axial, 2),
        "ms_adjacent3_max_mean": _rolling_max(axial, 3),
        "ms_adjacent5_max_mean": _rolling_max(axial, 5),
        "ms_fraction_over_050": sum(value >= 0.50 for value in axial) / len(axial),
        "ms_fraction_over_060": sum(value >= 0.60 for value in axial) / len(axial),
        "ms_coronal_mean": statistics.fmean(coronal),
        "ms_sagittal_mean": statistics.fmean(sagittal),
        "ms_inverse_coronal_mean": -statistics.fmean(coronal),
        "ms_inverse_sagittal_mean": -statistics.fmean(sagittal),
    }


def _percentile_ranks(values: list[float]) -> list[float]:
    ordered = sorted((value, index) for index, value in enumerate(values))
    ranks = [0.0] * len(values)
    start = 0
    while start < len(ordered):
        end = start + 1
        while end < len(ordered) and ordered[end][0] == ordered[start][0]:
            end += 1
        rank = ((start + end - 1) / 2) / max(1, len(values) - 1)
        for _, index in ordered[start:end]:
            ranks[index] = rank
        start = end
    return ranks


def _nested_repeated_cv(
    matrix: dict[str, list[float]], truth: list[bool], *, repeats: int = 50, folds: int = 5,
) -> dict[str, Any]:
    positive = [i for i, value in enumerate(truth) if value]
    negative = [i for i, value in enumerate(truth) if not value]
    outcomes = []
    selected: dict[str, int] = {name: 0 for name in matrix}
    for repeat in range(repeats):
        rng = random.Random(20260715 + repeat)
        pos, neg = positive[:], negative[:]
        rng.shuffle(pos)
        rng.shuffle(neg)
        groups = [[] for _ in range(folds)]
        for index, item in enumerate(pos):
            groups[index % folds].append(item)
        for index, item in enumerate(neg):
            groups[index % folds].append(item)
        predicted = [False] * len(truth)
        for test_indices in groups:
            test = set(test_indices)
            train = [i for i in range(len(truth)) if i not in test]
            candidates = []
            for name, values in matrix.items():
                threshold, metrics = _best_threshold(
                    [values[i] for i in train], [truth[i] for i in train]
                )
                candidates.append((
                    metrics["minimum_gate_metric"], metrics["balanced_accuracy"],
                    -abs(metrics["sensitivity"] - metrics["specificity"]), name, threshold,
                ))
            *_quality, name, threshold = max(candidates)
            selected[name] += 1
            for i in test_indices:
                predicted[i] = matrix[name][i] >= threshold
        outcomes.append(_binary_metrics(truth, predicted))
    return {
        "repeats": repeats,
        "folds": folds,
        "feature_and_threshold_selected_inside_each_training_fold": True,
        "runs_passing_75_75": sum(item["passed_75_75"] for item in outcomes),
        "median_sensitivity": statistics.median(item["sensitivity"] for item in outcomes),
        "median_specificity": statistics.median(item["specificity"] for item in outcomes),
        "minimum_sensitivity": min(item["sensitivity"] for item in outcomes),
        "minimum_specificity": min(item["specificity"] for item in outcomes),
        "selection_counts": {key: value for key, value in selected.items() if value},
    }


def analyze_volumetric_fusion(
    *, medgemma_signals_path: Path, medsiglip_root: Path,
    labels_path: Path, output_dir: Path, expected_positive: int = 39,
    expected_negative: int = 49,
) -> dict[str, Any]:
    output_dir = Path(output_dir).resolve()
    if output_dir.exists():
        raise PipelineError("Diretorio de analise de fusao ja existe.")
    rows = [json.loads(line) for line in Path(medgemma_signals_path).read_text(encoding="utf-8").splitlines() if line]
    case_ids = sorted(str(row["case_id"]) for row in rows)
    if len(case_ids) != len(set(case_ids)) or len(case_ids) != 88:
        raise PipelineError("Sinais MedGemma nao cobrem 88 casos unicos.")
    labels, labels_hash = _load_labels_after_inference(
        labels_path, expected_ids=case_ids,
        expected_positive=expected_positive, expected_negative=expected_negative,
    )
    summary = _load_json(Path(medsiglip_root) / "summary.json")
    if (
        summary.get("schema") != RUN_SCHEMA or summary.get("status") != "complete"
        or summary.get("case_count") != 88 or summary.get("failure_count") != 0
        or summary.get("final_decision") is not None
        or summary.get("ground_truth_read") is not False
        or summary.get("metrics_calculated") is not False
    ):
        raise PipelineError("Lote MedSigLIP nao esta completo e cego.")
    by_id = {str(row["case_id"]): row for row in rows}
    features: dict[str, dict[str, float]] = {}
    for case_id in case_ids:
        ms = _medsiglip_features(Path(medsiglip_root) / case_id)
        mg = {
            f"mg_{key}": float(value)
            for key, value in by_id[case_id].items()
            if key not in {"case_id", "label"}
        }
        features[case_id] = {**mg, **ms}
    truth = [labels[case_id]["label"] == "POSITIVE" for case_id in case_ids]
    matrix = {
        name: [features[case_id][name] for case_id in case_ids]
        for name in sorted(next(iter(features.values())))
    }
    mg_anchor = _percentile_ranks(matrix["mg_top2_mean_positive"])
    for name in sorted(key for key in matrix if key.startswith("ms_")):
        ranks = _percentile_ranks(matrix[name])
        matrix[f"fusion_equal_rank__{name}"] = [
            (left + right) / 2 for left, right in zip(mg_anchor, ranks, strict=True)
        ]

    analyses = []
    for name, values in matrix.items():
        threshold, apparent = _best_threshold(values, truth)
        analyses.append({
            "feature": name,
            "apparent_threshold": threshold,
            "apparent": apparent,
            "loocv": _loocv(values, truth),
            "repeated_5fold": _repeated_stratified_cv(values, truth),
        })
    analyses.sort(
        key=lambda item: (
            item["loocv"]["minimum_gate_metric"],
            item["loocv"]["balanced_accuracy"],
        ), reverse=True,
    )
    nested = _nested_repeated_cv(matrix, truth)
    result = {
        "schema": "argos-openswisshcc-volumetric-fusion-analysis-v1",
        "status": "development_only_not_qualified",
        "case_count": 88,
        "protected_ground_truth_sha256": labels_hash,
        "medsiglip_summary_sha256": _sha256(Path(medsiglip_root) / "summary.json"),
        "medgemma_signals_sha256": _sha256(Path(medgemma_signals_path)),
        "holdout_opened": False,
        "candidate_feature_count": len(matrix),
        "analyses": analyses,
        "nested_repeated_stratified_5fold": nested,
        "qualified": bool(
            analyses and analyses[0]["loocv"]["passed_75_75"]
            and analyses[0]["repeated_5fold"]["runs_passing_75_75"] == 50
            and nested["runs_passing_75_75"] == 50
        ),
        "research_only": True,
        "clinical_use_allowed": False,
        "requires_human_review": True,
    }
    output_dir.mkdir(parents=True)
    (output_dir / "fusion_analysis.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    with (output_dir / "case_features.csv").open("w", encoding="utf-8", newline="") as handle:
        fieldnames = ["case_id", "label", *sorted(next(iter(features.values())))]
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for case_id in case_ids:
            writer.writerow({"case_id": case_id, "label": labels[case_id]["label"], **features[case_id]})
    return result
