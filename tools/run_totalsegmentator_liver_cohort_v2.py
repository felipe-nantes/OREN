"""Run/verify TotalSegmentator liver on a frozen offline cohort."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from dtwin.benchmark.totalsegmentator_liver_cohort_runner import (  # noqa: E402
    run_cohort,
    verify_run,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("run", "verify"))
    parser.add_argument("--cohort", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source-name", required=True)
    parser.add_argument("--timeout-seconds", type=int, default=180)
    parser.add_argument(
        "--python-exe", type=Path, default=REPO / ".venv-win/Scripts/python.exe"
    )
    parser.add_argument(
        "--worker", type=Path, default=REPO / "tools/single_label_segment_worker.py"
    )
    args = parser.parse_args()
    if args.command == "verify":
        result = verify_run(args.output)
    else:
        result = run_cohort(
            cohort_root=args.cohort,
            output_root=args.output,
            python_exe=args.python_exe,
            worker=args.worker,
            source_name=args.source_name,
            timeout_seconds=args.timeout_seconds,
        )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
