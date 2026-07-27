#!/usr/bin/env python3
"""Build label-blind LiverHccSeg v21 panels or their technical gallery."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from dtwin.benchmark.liverhccseg_v21_panels import (
    build_liverhccseg_uniform9_gallery,
    build_liverhccseg_uniform9_panels,
)
from dtwin.core import PipelineError


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    panels = commands.add_parser("panels")
    panels.add_argument("--prepared", type=Path, required=True)
    panels.add_argument("--out", type=Path, required=True)
    panels.add_argument("--config", type=Path, required=True)
    panels.add_argument("--profile", type=Path, default=Path("profiles/figado.yaml"))
    panels.add_argument("--expected-case-count", type=int, default=14)
    panels.add_argument("--expected-prepared-signature")
    gallery = commands.add_parser("gallery")
    gallery.add_argument("--panels", type=Path, required=True)
    gallery.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == "panels":
            result = build_liverhccseg_uniform9_panels(
                prepared_root=args.prepared,
                output_root=args.out,
                config_path=args.config,
                profile_path=args.profile,
                expected_case_count=args.expected_case_count,
                expected_prepared_signature=args.expected_prepared_signature,
            )
        else:
            result = build_liverhccseg_uniform9_gallery(panel_root=args.panels, output_dir=args.out)
    except PipelineError as exc:
        print(f"[ABORTADO] {exc}")
        return 1
    print(json.dumps(result, ensure_ascii=True, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

