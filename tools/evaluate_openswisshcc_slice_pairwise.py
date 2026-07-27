"""Evaluate an exploratory high-resolution axial slice pilot after blind completion."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from dtwin.benchmark.openswisshcc_slice_pairwise_evaluation import evaluate_slice_pairwise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scores-root", required=True, type=Path)
    parser.add_argument("--labels", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    result = evaluate_slice_pairwise(
        scores_root=args.scores_root, labels_path=args.labels, output_path=args.out
    )
    print(json.dumps({
        "status": result["status"], "case_count": result["case_count"],
        "positive_count": result["positive_count"], "negative_count": result["negative_count"],
        "best": result["analyses"][0],
        "observed_mean_case_seconds": result["observed_mean_case_seconds"],
        "observed_max_case_seconds": result["observed_max_case_seconds"],
        "holdout_opened": result["holdout_opened"],
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
