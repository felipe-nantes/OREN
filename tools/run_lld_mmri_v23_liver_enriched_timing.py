#!/usr/bin/env python3
"""Freeze, verify, or run the signed LLD-MMRI v23 liver-enriched timing pilot."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from dtwin.benchmark.lld_mmri_v23_liver_enriched_timing import (
    freeze_liver_enriched_timing_protocol,
    run_liver_enriched_timing_pilot,
    verify_liver_enriched_timing_protocol,
    verify_liver_enriched_timing_run,
)
from dtwin.core import PipelineError


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("freeze", "verify", "run", "verify-run"))
    parser.add_argument("--panels", type=Path, required=True)
    parser.add_argument("--gallery", type=Path, required=True)
    parser.add_argument("--review", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        if args.command == "freeze":
            result = freeze_liver_enriched_timing_protocol(
                panel_root=args.panels, gallery_root=args.gallery,
                review_path=args.review, config_path=args.config,
                output_path=args.protocol,
            )
        elif args.command == "verify":
            result, _cohort, _config = verify_liver_enriched_timing_protocol(
                panel_root=args.panels, gallery_root=args.gallery,
                review_path=args.review, config_path=args.config,
                protocol_path=args.protocol,
            )
        elif args.command == "run":
            if args.output is None:
                parser.error("run exige --output")
            result = run_liver_enriched_timing_pilot(
                panel_root=args.panels, gallery_root=args.gallery,
                review_path=args.review, config_path=args.config,
                protocol_path=args.protocol, output_root=args.output,
            )
        else:
            if args.output is None:
                parser.error("verify-run exige --output")
            result = verify_liver_enriched_timing_run(
                panel_root=args.panels, gallery_root=args.gallery,
                review_path=args.review, config_path=args.config,
                protocol_path=args.protocol, output_root=args.output,
            )
    except (PipelineError, OSError, RuntimeError) as exc:
        print(f"[ABORTADO] {exc}")
        return 1
    print(json.dumps(result, ensure_ascii=True, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
