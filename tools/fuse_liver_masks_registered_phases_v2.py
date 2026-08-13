"""Build or verify label-blind liver-mask fusion across registered MR phases."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from dtwin.benchmark.liver_mask_phase_fusion import run_fusion, verify_fusion  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("run", "verify"))
    parser.add_argument("--cohort", type=Path, required=True)
    parser.add_argument("--native-run", type=Path, required=True)
    parser.add_argument("--arterial-run", type=Path, required=True)
    parser.add_argument("--venous-run", type=Path, required=True)
    parser.add_argument("--delayed-run", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--policy",
        choices=(
            "majority_2_of_4",
            "venous_fill_largest",
            "venous_guarded_union_fill_12mm",
        ),
        required=True,
    )
    args = parser.parse_args()
    if args.command == "verify":
        result = verify_fusion(args.output)
    else:
        result = run_fusion(
            cohort_root=args.cohort,
            phase_runs={
                "native": args.native_run,
                "arterial": args.arterial_run,
                "venous": args.venous_run,
                "delayed": args.delayed_run,
            },
            output_root=args.output,
            policy=args.policy,
        )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
