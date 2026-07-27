#!/usr/bin/env python3
"""Build label-blind LLD-MMRI v23 uniform-9 panels or gallery."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from dtwin.benchmark.lld_mmri_v23_panels import (
    build_lld_mmri_v23_uniform9_gallery,
    build_lld_mmri_v23_uniform9_panels,
)
from dtwin.core import PipelineError


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    panels = commands.add_parser("panels")
    panels.add_argument("--protocol-root", type=Path, required=True)
    panels.add_argument("--prepared-root", type=Path, required=True)
    panels.add_argument("--output-root", type=Path, required=True)
    panels.add_argument("--config", type=Path, required=True)
    panels.add_argument("--profile", type=Path, required=True)
    panels.add_argument("--preparation-signature")
    gallery = commands.add_parser("gallery")
    gallery.add_argument("--panel-root", type=Path, required=True)
    gallery.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == "panels":
            result = build_lld_mmri_v23_uniform9_panels(
                protocol_root=args.protocol_root,
                prepared_root=args.prepared_root,
                output_root=args.output_root,
                config_path=args.config,
                profile_path=args.profile,
                expected_preparation_signature=args.preparation_signature,
            )
        else:
            result = build_lld_mmri_v23_uniform9_gallery(
                panel_root=args.panel_root,
                output_dir=args.output_dir,
            )
    except (PipelineError, OSError) as exc:
        print(f"[ABORTADO] {exc}")
        return 1
    print(json.dumps(result, ensure_ascii=True, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
