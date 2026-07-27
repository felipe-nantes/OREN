"""Freeze the full87 localizer evaluation protocol before protected labels."""
import argparse
import json
from pathlib import Path

from dtwin.benchmark.openswisshcc_lesion_localizer_evaluation import create_evaluation_protocol


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--expected-case-count", type=int, default=87)
    args = parser.parse_args()
    result = create_evaluation_protocol(
        run_root=args.run, output_path=args.out, expected_case_count=args.expected_case_count
    )
    print(json.dumps({"protocol_signature": result["protocol_signature"], "case_count": result["case_count"], "ground_truth_read": result["ground_truth_read"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
