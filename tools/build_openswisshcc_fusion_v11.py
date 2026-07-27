"""Build the label-blind OpenSwissHCC v11 three-signal bundle."""
import argparse
import json
from pathlib import Path

from dtwin.benchmark.openswisshcc_v11_fusion import build_blind_signal_bundle


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--medgemma-v4", type=Path, required=True)
    parser.add_argument("--medsiglip-v5", type=Path, required=True)
    parser.add_argument("--localizer-v10", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--expected-case-count", type=int, default=87)
    args = parser.parse_args()
    result = build_blind_signal_bundle(
        medgemma_v4_root=args.medgemma_v4,
        medsiglip_v5_root=args.medsiglip_v5,
        localizer_v10_root=args.localizer_v10,
        output_dir=args.out,
        expected_case_count=args.expected_case_count,
    )
    print(json.dumps({
        "status": result["status"],
        "case_count": result["case_count"],
        "time_gate_180_seconds_passed": result["time_gate_180_seconds_passed"],
        "ground_truth_read": result["ground_truth_read"],
        "holdout_opened": result["holdout_opened"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
