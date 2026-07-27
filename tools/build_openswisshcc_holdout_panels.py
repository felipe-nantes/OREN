#!/usr/bin/env python3
"""Build label-blind OpenSwissHCC holdout panels or their technical gallery."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from dtwin.benchmark.openswisshcc_holdout_panels import (
    build_holdout_uniform9_gallery,
    build_holdout_uniform9_panels,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    panels = sub.add_parser("panels")
    panels.add_argument("--prepared", type=Path, required=True)
    panels.add_argument("--prepared-audit", type=Path, required=True)
    panels.add_argument("--alignment", type=Path, required=True)
    panels.add_argument("--alignment-summary", type=Path, required=True)
    panels.add_argument("--multiphase-config", type=Path, required=True)
    panels.add_argument("--fallback-config", type=Path, required=True)
    panels.add_argument("--profile", type=Path, required=True)
    panels.add_argument("--out", type=Path, required=True)
    gallery = sub.add_parser("gallery")
    gallery.add_argument("--panels", type=Path, required=True)
    gallery.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.command == "panels":
        result = build_holdout_uniform9_panels(
            prepared_root=args.prepared,
            prepared_audit_path=args.prepared_audit,
            alignment_root=args.alignment,
            alignment_summary_path=args.alignment_summary,
            multiphase_config_path=args.multiphase_config,
            fallback_config_path=args.fallback_config,
            profile_path=args.profile,
            output_root=args.out,
        )
    else:
        result = build_holdout_uniform9_gallery(panel_root=args.panels, output_dir=args.out)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
