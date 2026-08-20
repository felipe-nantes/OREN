"""Evaluate the frozen full87 localizer protocol after explicit authorization."""
import argparse
import json
from pathlib import Path

from dtwin.benchmark.openswisshcc_lesion_localizer_evaluation import (
    evaluate_full_development,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--labels", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--expected-case-count", type=int, default=87)
    parser.add_argument("--allow-protected-development-labels", action="store_true")
    args = parser.parse_args()
    result = evaluate_full_development(
        run_root=args.run,
        protocol_path=args.protocol,
        labels_path=args.labels,
        output_dir=args.out,
        allow_protected_development_labels=args.allow_protected_development_labels,
        expected_case_count=args.expected_case_count,
    )
    print(json.dumps({"status": result["status"], "development_gate_passed": result["development_gate_passed"], "loocv": result["primary_loocv_metrics"], "holdout_opened": result["holdout_opened"], "qualified": result["qualified"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
