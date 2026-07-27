#!/usr/bin/env python
"""Congela ou executa a avaliação protegida do OpenSwissHCC v19."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from dtwin.benchmark.openswisshcc_axial_atlas_rag_evaluation import (
    evaluate_development,
    freeze_evaluation_protocol,
)
from dtwin.core import PipelineError


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    freeze = commands.add_parser("freeze")
    freeze.add_argument("--scores", type=Path, required=True)
    freeze.add_argument("--score-protocol", type=Path, required=True)
    freeze.add_argument("--out", type=Path, required=True)
    evaluate = commands.add_parser("evaluate")
    evaluate.add_argument("--scores", type=Path, required=True)
    evaluate.add_argument("--score-protocol", type=Path, required=True)
    evaluate.add_argument("--protocol", type=Path, required=True)
    evaluate.add_argument("--labels", type=Path, required=True)
    evaluate.add_argument("--out", type=Path, required=True)
    evaluate.add_argument("--allow-protected-development-labels", action="store_true")
    return parser


def main() -> int:
    args = _parser().parse_args()
    try:
        if args.command == "freeze":
            result = freeze_evaluation_protocol(
                score_root=args.scores,
                score_protocol_path=args.score_protocol,
                output_path=args.out,
            )
        else:
            result = evaluate_development(
                score_root=args.scores,
                score_protocol_path=args.score_protocol,
                protocol_path=args.protocol,
                labels_path=args.labels,
                output_dir=args.out,
                allow_protected_development_labels=args.allow_protected_development_labels,
            )
    except PipelineError as exc:
        print(f"[ABORTADO] {exc}")
        return 1
    print(json.dumps(result, ensure_ascii=True, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

