#!/usr/bin/env python3
"""Congela ou executa o scorer em blocos v18."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dtwin.benchmark.openswisshcc_axial_atlas_chunk_score import (
    freeze_chunk_protocol,
    run_chunk_batch,
)
from dtwin.core import PipelineError


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    commands = result.add_subparsers(dest="command", required=True)
    freeze = commands.add_parser("freeze")
    freeze.add_argument("--atlas-root", required=True, type=Path)
    freeze.add_argument("--v17-score-protocol", required=True, type=Path)
    freeze.add_argument("--config", required=True, type=Path)
    freeze.add_argument("--out", required=True, type=Path)
    run = commands.add_parser("run")
    run.add_argument("--atlas-root", required=True, type=Path)
    run.add_argument("--protocol", required=True, type=Path)
    run.add_argument("--config", required=True, type=Path)
    run.add_argument("--out", required=True, type=Path)
    run.add_argument("--max-new-cases", type=int)
    return result


def main(argv=None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.command == "freeze":
            value = freeze_chunk_protocol(atlas_root=args.atlas_root, v17_score_protocol_path=args.v17_score_protocol, config_path=args.config, output_path=args.out)
        else:
            value = run_chunk_batch(
                atlas_root=args.atlas_root,
                protocol_path=args.protocol,
                config_path=args.config,
                output_root=args.out,
                max_new_cases=args.max_new_cases,
                progress_callback=lambda item: print(json.dumps(item, ensure_ascii=False), flush=True),
            )
    except PipelineError as exc:
        print(f"[ABORTADO] {exc}", file=sys.stderr)
        return 2
    print(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
