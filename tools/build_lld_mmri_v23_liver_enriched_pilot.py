#!/usr/bin/env python3
"""Build the label-blind LLD-MMRI v23 liver-enriched pilot and gallery."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from dtwin.benchmark.lld_mmri_v23_liver_enriched_pilot import (
    build_liver_enriched_full_cohort,
    build_liver_enriched_gallery,
    build_liver_enriched_pilot,
    verify_liver_enriched_full_cohort,
)
from dtwin.core import PipelineError
from dtwin.medgemma_screening import _write_json_atomic


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    panels = commands.add_parser("panels")
    panels.add_argument("--prepared-root", type=Path, required=True)
    panels.add_argument("--output-root", type=Path, required=True)
    panels.add_argument("--config", type=Path, required=True)
    selection = panels.add_mutually_exclusive_group(required=True)
    selection.add_argument("--case-id", action="append")
    selection.add_argument("--all-prepared", action="store_true")
    gallery = commands.add_parser("gallery")
    gallery.add_argument("--panel-root", type=Path, required=True)
    gallery.add_argument("--output-root", type=Path, required=True)
    verify = commands.add_parser("verify")
    verify.add_argument("--panel-root", type=Path, required=True)
    verify.add_argument("--prepared-root", type=Path, required=True)
    verify.add_argument("--config", type=Path, required=True)
    verify.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = (
            (build_liver_enriched_full_cohort(
                prepared_root=args.prepared_root,
                output_root=args.output_root,
                config_path=args.config,
            ) if args.all_prepared else build_liver_enriched_pilot(
                prepared_root=args.prepared_root,
                output_root=args.output_root,
                config_path=args.config,
                case_ids=args.case_id,
            ))
            if args.command == "panels"
            else (
                build_liver_enriched_gallery(panel_root=args.panel_root, output_root=args.output_root)
                if args.command == "gallery"
                else verify_liver_enriched_full_cohort(
                    panel_root=args.panel_root,
                    prepared_root=args.prepared_root,
                    config_path=args.config,
                )
            )
        )
        if args.command == "verify":
            _write_json_atomic(args.out, result)
    except (PipelineError, OSError, json.JSONDecodeError) as exc:
        print(f"[ABORTADO] {exc}")
        return 1
    print(json.dumps(result, ensure_ascii=True, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
