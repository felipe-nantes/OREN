"""Run the disabled phase-aware segmentation-v2 adapter on one prepared case."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from dtwin.segmentation_shadow import run_phase_aware_shadow  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case-root", type=Path, required=True)
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--arterial", type=Path)
    parser.add_argument(
        "--mrsegmentator-exe",
        type=Path,
        default=REPO / ".venv-mrseg/Scripts/mrsegmentator.exe",
    )
    parser.add_argument("--timeout-seconds", type=int, default=180)
    parser.add_argument(
        "--acknowledge-experimental-shadow",
        action="store_true",
        help="Required acknowledgement: output is visualization-only and not diagnostic.",
    )
    args = parser.parse_args()
    if not args.acknowledge_experimental_shadow:
        parser.error("--acknowledge-experimental-shadow is required")
    phase_paths = {"t1_arterial": args.arterial} if args.arterial else {}
    result = run_phase_aware_shadow(
        case_root=args.case_root,
        phase_paths=phase_paths,
        reference_volume=args.reference,
        mrsegmentator_exe=args.mrsegmentator_exe,
        timeout_seconds=args.timeout_seconds,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
