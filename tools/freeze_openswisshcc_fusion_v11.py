"""Freeze the OpenSwissHCC v11 fusion protocol before protected labels."""
import argparse
import json
from pathlib import Path

from dtwin.benchmark.openswisshcc_v11_fusion import create_fusion_protocol


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--expected-case-count", type=int, default=87)
    args = parser.parse_args()
    result = create_fusion_protocol(
        bundle_root=args.bundle, output_path=args.out, expected_case_count=args.expected_case_count
    )
    print(json.dumps({
        "protocol_signature": result["protocol_signature"],
        "case_count": result["case_count"],
        "ground_truth_read": result["ground_truth_read"],
        "holdout_opened": result["holdout_opened"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
