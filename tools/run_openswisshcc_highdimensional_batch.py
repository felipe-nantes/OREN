#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from dtwin.benchmark.openswisshcc_highdimensional_batch_inference import (
    run_highdimensional_blind_batch,
)
from dtwin.core import PipelineError


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Executa o batch cego high-dimensional resumível.")
    parser.add_argument("--bundle-root", required=True, type=Path)
    parser.add_argument("--protocol", required=True, type=Path)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument("--max-new-cases", type=int)
    args = parser.parse_args(argv)

    def progress(value):
        print(json.dumps(value, sort_keys=True), flush=True)

    try:
        result = run_highdimensional_blind_batch(
            bundle_root=args.bundle_root,
            protocol_path=args.protocol,
            config_path=args.config,
            output_root=args.output_root,
            max_new_cases=args.max_new_cases,
            progress_callback=progress,
        )
    except PipelineError as exc:
        print(f"[ABORTADO] {exc}", flush=True)
        return 1
    print(json.dumps({
        "status": result["status"],
        "completed_case_count": result["completed_case_count"],
        "pending_case_count": result["pending_case_count"],
        "ground_truth_read": result["ground_truth_read"],
        "holdout_opened": result["holdout_opened"],
    }, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
