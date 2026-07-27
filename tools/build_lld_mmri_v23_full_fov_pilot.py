#!/usr/bin/env python3
"""Build the label-blind LLD-MMRI v23 full-FOV pilot and gallery."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from dtwin.benchmark.lld_mmri_v23_full_fov_pilot import (
    build_full_fov_gallery,
    build_full_fov_pilot,
)
from dtwin.core import PipelineError


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    panels = commands.add_parser("panels")
    panels.add_argument("--prepared-root", type=Path, required=True)
    panels.add_argument("--output-root", type=Path, required=True)
    panels.add_argument("--config", type=Path, required=True)
    panels.add_argument("--case-id", action="append", required=True)
    gallery = commands.add_parser("gallery")
    gallery.add_argument("--panel-root", type=Path, required=True)
    gallery.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = (
            build_full_fov_pilot(
                prepared_root=args.prepared_root,
                output_root=args.output_root,
                config_path=args.config,
                case_ids=args.case_id,
            )
            if args.command == "panels"
            else build_full_fov_gallery(panel_root=args.panel_root, output_root=args.output_root)
        )
    except (PipelineError, OSError) as exc:
        print(f"[ABORTADO] {exc}")
        return 1
    print(json.dumps(result, indent=2, ensure_ascii=True, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
