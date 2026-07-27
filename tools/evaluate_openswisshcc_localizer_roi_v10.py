"""Evaluate a completed blind v10 paired-ROI pilot after opening development labels."""
import argparse
import json
from pathlib import Path

from dtwin.benchmark.openswisshcc_localizer_roi_evaluation import evaluate_roi_pilot


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--morphology", type=Path, required=True)
    parser.add_argument("--enhancement", type=Path, required=True)
    parser.add_argument("--review", type=Path, required=True)
    parser.add_argument("--freeze", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--localizer-run", type=Path, required=True)
    parser.add_argument("--scores", type=Path, required=True)
    parser.add_argument("--labels", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--expected-case-count", type=int, default=10)
    parser.add_argument("--expected-positive", type=int, default=4)
    parser.add_argument("--expected-negative", type=int, default=6)
    args = parser.parse_args()
    result = evaluate_roi_pilot(morphology_root=args.morphology, enhancement_root=args.enhancement, review_path=args.review, freeze_path=args.freeze, config_path=args.config, localizer_run=args.localizer_run, scores_root=args.scores, labels_path=args.labels, output_dir=args.out, expected_case_count=args.expected_case_count, expected_positive=args.expected_positive, expected_negative=args.expected_negative)
    primary = result["analyses"][0]
    print(json.dumps({"status": result["status"], "primary_feature": result["primary_feature"], "apparent": primary["apparent"], "loocv": primary["loocv"], "holdout_opened": result["holdout_opened"], "qualified": result["qualified"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
