#!/usr/bin/env python3
"""Consolidate the two v21 public single-class arms without pooling metrics."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from dtwin.benchmark.public_independent_v21_consolidation import consolidate_v21_external_arms
from dtwin.core import PipelineError


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--positive-evaluation", type=Path, required=True)
    parser.add_argument("--negative-evaluation", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = consolidate_v21_external_arms(
            positive_evaluation_path=args.positive_evaluation,
            negative_evaluation_path=args.negative_evaluation,
            output_dir=args.out,
        )
    except PipelineError as exc:
        print(f"[ABORTADO] {exc}")
        return 1
    print(json.dumps(result, ensure_ascii=True, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
