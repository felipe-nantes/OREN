#!/usr/bin/env python3
"""Evaluate frozen LLD-MMRI v23 predictions against protected public labels."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from dtwin.benchmark.lld_mmri_v23_evaluation import evaluate_lld_mmri_v23_after_prediction_freeze
from dtwin.core import PipelineError


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol-root", type=Path, required=True)
    parser.add_argument("--predictions", type=Path, required=True)
    parser.add_argument("--protected-labels", type=Path, required=True)
    parser.add_argument("--timing", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--allow-protected-public-labels", action="store_true")
    args = parser.parse_args()
    try:
        result = evaluate_lld_mmri_v23_after_prediction_freeze(
            protocol_root=args.protocol_root,
            prediction_root=args.predictions,
            protected_labels_path=args.protected_labels,
            output_root=args.output,
            allow_protected_public_labels=args.allow_protected_public_labels,
            end_to_end_timing_path=args.timing,
        )
    except PipelineError as exc:
        print(f"[ABORTADO] {exc}")
        return 1
    print(json.dumps(result, ensure_ascii=True, indent=2, sort_keys=True))
    return 0 if result["qualified"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
