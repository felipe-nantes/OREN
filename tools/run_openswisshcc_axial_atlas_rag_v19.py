#!/usr/bin/env python
"""Congela ou executa o scorer cego RAG v19 do atlas axial OpenSwissHCC."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from dtwin.benchmark.openswisshcc_axial_atlas_rag_score import (
    freeze_rag_protocol,
    run_rag_batch,
)
from dtwin.core import PipelineError


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    freeze = commands.add_parser("freeze")
    freeze.add_argument("--atlas-root", type=Path, required=True)
    freeze.add_argument("--v17-protocol", type=Path, required=True)
    freeze.add_argument("--config", type=Path, required=True)
    freeze.add_argument("--out", type=Path, required=True)
    run = commands.add_parser("run")
    run.add_argument("--atlas-root", type=Path, required=True)
    run.add_argument("--protocol", type=Path, required=True)
    run.add_argument("--config", type=Path, required=True)
    run.add_argument("--out", type=Path, required=True)
    run.add_argument("--max-new-cases", type=int)
    return parser


def main() -> int:
    args = _parser().parse_args()
    try:
        if args.command == "freeze":
            result = freeze_rag_protocol(
                atlas_root=args.atlas_root,
                v17_score_protocol_path=args.v17_protocol,
                config_path=args.config,
                output_path=args.out,
            )
        else:
            result = run_rag_batch(
                atlas_root=args.atlas_root,
                protocol_path=args.protocol,
                config_path=args.config,
                output_root=args.out,
                max_new_cases=args.max_new_cases,
                progress_callback=lambda value: print(
                    json.dumps(value, ensure_ascii=True, sort_keys=True), flush=True
                ),
            )
    except PipelineError as exc:
        print(f"[ABORTADO] {exc}")
        return 1
    # O PowerShell legado pode usar cp1252; escapar Unicode mantém o CLI
    # transportável sem modificar o JSON persistido em UTF-8.
    print(json.dumps(result, ensure_ascii=True, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
