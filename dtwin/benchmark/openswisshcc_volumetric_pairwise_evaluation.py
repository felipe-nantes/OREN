"""Development-only evaluation of blind volumetric MedGemma pairwise scores."""
from __future__ import annotations

import csv
import json
import statistics
from pathlib import Path
from typing import Any

from dtwin.benchmark.openswisshcc_alignment import _load_json, _sha256
from dtwin.benchmark.openswisshcc_evaluation import _load_labels_after_inference
from dtwin.benchmark.openswisshcc_volumetric_evaluation import (
    _best_threshold,
    _loocv,
    _repeated_stratified_cv,
)
from dtwin.benchmark.openswisshcc_volumetric_fusion import _nested_repeated_cv
from dtwin.benchmark.openswisshcc_volumetric_pairwise import (
    CASE_SCHEMA,
    PAIR_BANK,
    RUN_SCHEMA,
)
from dtwin.core import PipelineError


def _rolling_max(values: list[float], width: int) -> float:
    if len(values) < width:
        return statistics.fmean(values)
    return max(
        statistics.fmean(values[index:index + width])
        for index in range(len(values) - width + 1)
    )


def _case_features(case_dir: Path, summary: dict[str, Any]) -> dict[str, float]:
    manifest_path = case_dir / "pairwise_manifest.json"
    scores_path = case_dir / "pairwise_panel_scores.json"
    manifest = _load_json(manifest_path)
    if (
        manifest.get("schema") != CASE_SCHEMA
        or manifest.get("status") != "scores_only_no_decision"
        or manifest.get("experiment_signature") != summary["experiment_signature"]
        or manifest.get("pair_bank_sha256") != summary["pair_bank_sha256"]
        or manifest.get("scores_sha256") != _sha256(scores_path)
        or manifest.get("final_decision") is not None
        or manifest.get("ground_truth_read") is not False
        or manifest.get("metrics_calculated") is not False
    ):
        raise PipelineError(f"Manifesto pairwise invalido: {case_dir.name}.")
    panels = json.loads(scores_path.read_text(encoding="utf-8"))
    if not isinstance(panels, list) or len(panels) != manifest.get("panel_image_count"):
        raise PipelineError(f"Quantidade de paineis pairwise invalida: {case_dir.name}.")
    by_pair = {pair["pair_id"]: [] for pair in PAIR_BANK}
    panel_means: list[float] = []
    for expected_number, panel in enumerate(panels, start=1):
        if panel.get("panel_number") != expected_number:
            raise PipelineError(f"Ordem de paineis pairwise invalida: {case_dir.name}.")
        score = panel.get("score")
        rows = score.get("pairs") if isinstance(score, dict) else None
        if (
            not isinstance(rows, list) or len(rows) != len(PAIR_BANK)
            or score.get("final_decision") is not None
            or score.get("ground_truth_read") is not False
        ):
            raise PipelineError(f"Score pairwise invalido: {case_dir.name}.")
        values = []
        for expected, row in zip(PAIR_BANK, rows, strict=True):
            value = row.get("positive_probability")
            if (
                row.get("pair_id") != expected["pair_id"]
                or not isinstance(value, (int, float))
                or not 0.0 <= float(value) <= 1.0
            ):
                raise PipelineError(f"Par pairwise invalido: {case_dir.name}.")
            by_pair[expected["pair_id"]].append(float(value))
            values.append(float(value))
        panel_means.append(statistics.fmean(values))
    ordered = sorted(panel_means, reverse=True)
    features = {
        "pw_panel_mean": statistics.fmean(panel_means),
        "pw_panel_median": statistics.median(panel_means),
        "pw_panel_max": max(panel_means),
        "pw_panel_min": min(panel_means),
        "pw_panel_top2_mean": statistics.fmean(ordered[:min(2, len(ordered))]),
        "pw_panel_top3_mean": statistics.fmean(ordered[:min(3, len(ordered))]),
        "pw_panel_focality": max(panel_means) - statistics.median(panel_means),
        "pw_panel_adjacent2_max_mean": _rolling_max(panel_means, 2),
        "pw_panel_adjacent3_max_mean": _rolling_max(panel_means, 3),
        "pw_panel_fraction_over_050": sum(value >= 0.5 for value in panel_means) / len(panel_means),
    }
    for pair_id, values in by_pair.items():
        pair_ordered = sorted(values, reverse=True)
        features[f"pw_{pair_id}_mean"] = statistics.fmean(values)
        features[f"pw_{pair_id}_max"] = max(values)
        features[f"pw_{pair_id}_top2_mean"] = statistics.fmean(
            pair_ordered[:min(2, len(pair_ordered))]
        )
    return features


def evaluate_volumetric_pairwise(
    *, pairwise_root: Path, labels_path: Path, output_dir: Path,
    expected_positive: int = 39, expected_negative: int = 49,
) -> dict[str, Any]:
    pairwise_root = Path(pairwise_root).resolve()
    output_dir = Path(output_dir).resolve()
    if output_dir.exists():
        raise PipelineError("Diretorio de avaliacao pairwise ja existe.")
    summary_path = pairwise_root / "summary.json"
    summary = _load_json(summary_path)
    if (
        summary.get("schema") != RUN_SCHEMA
        or summary.get("status") != "complete"
        or summary.get("case_count") != expected_positive + expected_negative
        or summary.get("success_count") != summary.get("case_count")
        or summary.get("failure_count") != 0
        or summary.get("final_decision") is not None
        or summary.get("ground_truth_read") is not False
        or summary.get("metrics_calculated") is not False
    ):
        raise PipelineError("Lote pairwise nao esta completo e cego.")
    case_dirs = sorted(
        path for path in pairwise_root.iterdir()
        if path.is_dir() and not path.name.startswith(".")
    )
    if len(case_dirs) != summary["case_count"]:
        raise PipelineError("Diretorios pairwise nao cobrem toda a coorte.")

    # Verify every blind artifact before labels are opened.
    features = {case_dir.name: _case_features(case_dir, summary) for case_dir in case_dirs}
    case_ids = sorted(features)
    labels, labels_hash = _load_labels_after_inference(
        labels_path, expected_ids=case_ids,
        expected_positive=expected_positive, expected_negative=expected_negative,
    )
    truth = [labels[case_id]["label"] == "POSITIVE" for case_id in case_ids]
    matrix = {
        name: [features[case_id][name] for case_id in case_ids]
        for name in sorted(next(iter(features.values())))
    }
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
        ),
        reverse=True,
    )
    nested = _nested_repeated_cv(matrix, truth)
    qualified = bool(
        analyses
        and analyses[0]["loocv"]["passed_75_75"]
        and analyses[0]["repeated_5fold"]["runs_passing_75_75"] == 50
        and nested["runs_passing_75_75"] == 50
        and float(summary["max_case_seconds"]) <= 180.0
    )
    result = {
        "schema": "argos-openswisshcc-volumetric-pairwise-evaluation-v1",
        "status": "qualified_development_candidate" if qualified else "development_only_not_qualified",
        "case_count": len(case_ids),
        "positive_count": expected_positive,
        "negative_count": expected_negative,
        "protected_ground_truth_sha256": labels_hash,
        "pairwise_summary_sha256": _sha256(summary_path),
        "pair_bank_sha256": summary["pair_bank_sha256"],
        "observed_mean_case_seconds": summary["mean_case_seconds"],
        "observed_max_case_seconds": summary["max_case_seconds"],
        "time_gate_180_seconds_passed": float(summary["max_case_seconds"]) <= 180.0,
        "holdout_opened": False,
        "feature_count": len(matrix),
        "analyses": analyses,
        "nested_repeated_stratified_5fold": nested,
        "qualified": qualified,
        "research_only": True,
        "clinical_use_allowed": False,
        "requires_human_review": True,
    }
    output_dir.mkdir(parents=True)
    (output_dir / "pairwise_evaluation.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    with (output_dir / "case_features.csv").open("w", encoding="utf-8", newline="") as handle:
        fieldnames = ["case_id", "label", *sorted(next(iter(features.values())))]
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for case_id in case_ids:
            writer.writerow({"case_id": case_id, "label": labels[case_id]["label"], **features[case_id]})
    return result
