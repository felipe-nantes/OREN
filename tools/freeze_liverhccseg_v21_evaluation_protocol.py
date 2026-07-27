#!/usr/bin/env python3
"""Freeze the label-blind LiverHccSeg v21 evaluation authorization protocol."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from dtwin.benchmark.public_independent_v21_evaluation import (
    freeze_liverhccseg_v21_evaluation_protocol,
)
from dtwin.core import PipelineError


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scores", type=Path, required=True)
    parser.add_argument("--calibrator", type=Path, required=True)
    parser.add_argument("--prepared", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--expected-case-count", type=int, default=14)
    args = parser.parse_args()
    try:
        result = freeze_liverhccseg_v21_evaluation_protocol(
            scored_root=args.scores,
            calibrator_path=args.calibrator,
            prepared_root=args.prepared,
            output_path=args.out,
            expected_case_count=args.expected_case_count,
        )
    except PipelineError as exc:
        print(f"[ABORTADO] {exc}")
        return 1
    print(json.dumps(result, ensure_ascii=True, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
