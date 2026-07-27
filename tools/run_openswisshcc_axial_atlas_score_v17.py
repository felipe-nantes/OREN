#!/usr/bin/env python
"""Congela ou executa o scorer cego 4B do atlas axial v17."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from dtwin.benchmark.openswisshcc_axial_atlas_score import (
    freeze_score_protocol,
    freeze_timing_plan,
    run_blind_batch,
    run_timing_plan,
)
from dtwin.core import PipelineError


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    freeze = commands.add_parser("freeze")
    freeze.add_argument("--atlas-root", type=Path, required=True)
    freeze.add_argument("--gallery-root", type=Path, required=True)
    freeze.add_argument("--review", type=Path, required=True)
    freeze.add_argument("--config", type=Path, required=True)
    freeze.add_argument("--out", type=Path, required=True)
    run = commands.add_parser("run")
    run.add_argument("--atlas-root", type=Path, required=True)
    run.add_argument("--protocol", type=Path, required=True)
    run.add_argument("--config", type=Path, required=True)
    run.add_argument("--out", type=Path, required=True)
    run.add_argument("--max-new-cases", type=int)
    timing_freeze = commands.add_parser("timing-freeze")
    timing_freeze.add_argument("--atlas-root", type=Path, required=True)
    timing_freeze.add_argument("--protocol", type=Path, required=True)
    timing_freeze.add_argument("--out", type=Path, required=True)
    timing_run = commands.add_parser("timing-run")
    timing_run.add_argument("--atlas-root", type=Path, required=True)
    timing_run.add_argument("--protocol", type=Path, required=True)
    timing_run.add_argument("--plan", type=Path, required=True)
    timing_run.add_argument("--config", type=Path, required=True)
    timing_run.add_argument("--out", type=Path, required=True)
    timing_run.add_argument("--max-new-cases", type=int)
    return parser


def main() -> int:
    args = _parser().parse_args()
    try:
        if args.command == "freeze":
            result = freeze_score_protocol(
                atlas_root=args.atlas_root,
                gallery_root=args.gallery_root,
                review_path=args.review,
                config_path=args.config,
                out_path=args.out,
            )
        elif args.command == "run":
            result = run_blind_batch(
                atlas_root=args.atlas_root,
                protocol_path=args.protocol,
                config_path=args.config,
                output_root=args.out,
                max_new_cases=args.max_new_cases,
                progress_callback=lambda value: print(
                    json.dumps(value, ensure_ascii=False, sort_keys=True), flush=True
                ),
            )
        elif args.command == "timing-freeze":
            result = freeze_timing_plan(
                atlas_root=args.atlas_root,
                protocol_path=args.protocol,
                output_path=args.out,
            )
        else:
            result = run_timing_plan(
                atlas_root=args.atlas_root,
                protocol_path=args.protocol,
                plan_path=args.plan,
                config_path=args.config,
                output_root=args.out,
                max_new_cases=args.max_new_cases,
                progress_callback=lambda value: print(
                    json.dumps(value, ensure_ascii=False, sort_keys=True), flush=True
                ),
            )
    except PipelineError as exc:
        print(f"[ABORTADO] {exc}")
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
