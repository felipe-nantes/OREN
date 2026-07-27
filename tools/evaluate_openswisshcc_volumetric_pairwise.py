"""Evaluate the completed blind OpenSwissHCC volumetric pairwise run."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from dtwin.benchmark.openswisshcc_volumetric_pairwise_evaluation import (
    evaluate_volumetric_pairwise,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pairwise-root", required=True, type=Path)
    parser.add_argument("--labels", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--expected-positive", type=int, default=39)
    parser.add_argument("--expected-negative", type=int, default=49)
    args = parser.parse_args()
    result = evaluate_volumetric_pairwise(
        pairwise_root=args.pairwise_root,
        labels_path=args.labels,
        output_dir=args.out,
        expected_positive=args.expected_positive,
        expected_negative=args.expected_negative,
    )
    best = result["analyses"][0]
    print(json.dumps({
        "status": result["status"],
        "qualified": result["qualified"],
        "best_feature": best["feature"],
        "apparent": best["apparent"],
        "loocv": best["loocv"],
        "repeated_5fold": best["repeated_5fold"],
        "nested_repeated_stratified_5fold": result["nested_repeated_stratified_5fold"],
        "observed_mean_case_seconds": result["observed_mean_case_seconds"],
        "observed_max_case_seconds": result["observed_max_case_seconds"],
        "holdout_opened": result["holdout_opened"],
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
