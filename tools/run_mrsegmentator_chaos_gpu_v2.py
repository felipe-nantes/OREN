"""Run/verify the frozen 20-case CHAOS MRSegmentator GPU benchmark."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from dtwin.benchmark.mrsegmentator_chaos_runner import run_cohort, verify_run  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("run", "verify"))
    parser.add_argument(
        "--cohort", type=Path, default=REPO / "data/prepared/chaos_v21_blind"
    )
    parser.add_argument(
        "--output", type=Path, default=REPO / "experiments/mrsegmentator_chaos_gpu_fast_v2"
    )
    parser.add_argument(
        "--mrsegmentator-exe",
        type=Path,
        default=REPO / ".venv-mrseg/Scripts/mrsegmentator.exe",
    )
    parser.add_argument(
        "--python-exe", type=Path, default=REPO / ".venv-mrseg/Scripts/python.exe"
    )
    parser.add_argument("--timeout-seconds", type=int, default=180)
    parser.add_argument("--source-name", default="t1_in.nii.gz")
    args = parser.parse_args()
    if args.command == "verify":
        result = verify_run(args.output)
    else:
        result = run_cohort(
            cohort_root=args.cohort,
            output_root=args.output,
            mrsegmentator_exe=args.mrsegmentator_exe,
            python_exe=args.python_exe,
            timeout_seconds=args.timeout_seconds,
            source_name=args.source_name,
        )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
