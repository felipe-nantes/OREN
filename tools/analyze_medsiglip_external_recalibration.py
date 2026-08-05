"""Development-only threshold audit followed by untouched holdout evaluation."""
from __future__ import annotations

import json
from pathlib import Path


def _rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _metrics(rows: list[dict], predictions: dict[str, dict], threshold: float) -> tuple[float, float]:
    positives = [row for row in rows if row["label"] == "POSITIVE"]
    negatives = [row for row in rows if row["label"] == "NEGATIVE"]
    sensitivity = sum(
        not predictions[row["case_id"]]["technical_failure"]
        and float(predictions[row["case_id"]]["score"]) >= threshold
        for row in positives
    ) / len(positives)
    specificity = sum(
        not predictions[row["case_id"]]["technical_failure"]
        and float(predictions[row["case_id"]]["score"]) < threshold
        for row in negatives
    ) / len(negatives)
    return sensitivity, specificity


def main() -> int:
    predictions = {
        row["case_id"]: row for row in _rows(Path(
            "casos/qualification/hybrid_v1/"
            "medsiglip_monophase_delayed_openswiss_predictions_v1/predictions.jsonl"
        ))
    }
    development = _rows(Path(
        "casos/qualification/openswisshcc_v1/prepared/development_v1/"
        "protected_ground_truth/development_labels.jsonl"
    ))
    holdout = _rows(Path(
        "casos/qualification/openswisshcc_v1/prepared/"
        "holdout_v21_protected_labels/holdout_labels.jsonl"
    ))
    thresholds = sorted(
        float(row["score"])
        for row in predictions.values()
        if not row["technical_failure"]
        and any(case["case_id"] == row["case_id"] for case in development)
    )
    candidates = []
    for threshold in thresholds:
        sensitivity, specificity = _metrics(development, predictions, threshold)
        candidates.append((min(sensitivity, specificity), sensitivity + specificity,
                           threshold, sensitivity, specificity))
    best = max(candidates)
    feasible = [item for item in candidates if item[3] >= 0.75 and item[4] >= 0.75]
    holdout_sensitivity, holdout_specificity = _metrics(holdout, predictions, best[2])
    print(json.dumps({
        "selection_data": "openswisshcc_development_only",
        "holdout_used_for_selection": False,
        "development_feasible_75_75_threshold_count": len(feasible),
        "selected_threshold": best[2],
        "development_sensitivity": best[3],
        "development_specificity": best[4],
        "holdout_sensitivity_at_frozen_threshold": holdout_sensitivity,
        "holdout_specificity_at_frozen_threshold": holdout_specificity,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
