#!/usr/bin/env python3
"""Freeze the v11 external calibrator or apply it to blind v21 signals."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from dtwin.benchmark.public_independent_v21_calibrator import (
    freeze_v11_external_calibrator,
    score_external_signals,
)
from dtwin.core import PipelineError


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    freeze = commands.add_parser("freeze")
    freeze.add_argument("--bundle", type=Path, required=True)
    freeze.add_argument("--protocol", type=Path, required=True)
    freeze.add_argument("--development-evaluation", type=Path, required=True)
    freeze.add_argument("--out", type=Path, required=True)
    freeze.add_argument("--expected-case-count", type=int, default=87)
    score = commands.add_parser("score")
    score.add_argument("--calibrator", type=Path, required=True)
    score.add_argument("--signals", type=Path, required=True)
    score.add_argument("--out", type=Path, required=True)
    score.add_argument("--expected-case-count", type=int)
    args = parser.parse_args()
    try:
        if args.command == "freeze":
            result = freeze_v11_external_calibrator(
                bundle_root=args.bundle,
                protocol_path=args.protocol,
                development_evaluation_path=args.development_evaluation,
                output_path=args.out,
                expected_case_count=args.expected_case_count,
            )
        else:
            result = score_external_signals(
                calibrator_path=args.calibrator,
                signals_path=args.signals,
                output_dir=args.out,
                expected_case_count=args.expected_case_count,
            )
    except PipelineError as exc:
        print(f"[ABORTADO] {exc}")
        return 1
    print(json.dumps(result, ensure_ascii=True, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
