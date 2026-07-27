#!/usr/bin/env python3
"""Freeze, verify, or run the label-blind LLD-MMRI full-FOV 3x9 timing pilot."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from dtwin.benchmark.lld_mmri_v23_full_fov_timing import (
    freeze_full_fov_timing_protocol,
    run_full_fov_timing_pilot,
    verify_full_fov_timing_protocol,
)
from dtwin.core import PipelineError


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("freeze", "verify", "run"):
        command = commands.add_parser(name)
        command.add_argument("--panels", type=Path, required=True)
        command.add_argument("--gallery", type=Path, required=True)
        command.add_argument("--review", type=Path, required=True)
        command.add_argument("--config", type=Path, required=True)
        command.add_argument("--protocol", type=Path, required=True)
        if name == "run":
            command.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        common = {
            "panel_root": args.panels,
            "gallery_root": args.gallery,
            "review_path": args.review,
            "config_path": args.config,
        }
        if args.command == "freeze":
            result = freeze_full_fov_timing_protocol(
                **common, output_path=args.protocol, maximum_seconds=180.0,
            )
        elif args.command == "verify":
            result, _cohort, _config = verify_full_fov_timing_protocol(
                **common, protocol_path=args.protocol,
            )
        else:
            result = run_full_fov_timing_pilot(
                **common, protocol_path=args.protocol, output_root=args.output,
            )
    except (PipelineError, OSError) as exc:
        print(f"[ABORTADO] {exc}")
        return 1
    print(json.dumps(result, ensure_ascii=True, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
