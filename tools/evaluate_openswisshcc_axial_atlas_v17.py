#!/usr/bin/env python3
"""Congela e executa a avaliação protegida do axial-atlas v17."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dtwin.benchmark.openswisshcc_axial_atlas_evaluation import (  # noqa: E402
    evaluate_development,
    freeze_evaluation_protocol,
)
from dtwin.core import PipelineError  # noqa: E402


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    commands = result.add_subparsers(dest="command", required=True)
    freeze = commands.add_parser("freeze")
    freeze.add_argument("--scores", required=True, type=Path)
    freeze.add_argument("--score-protocol", required=True, type=Path)
    freeze.add_argument("--out", required=True, type=Path)
    evaluate = commands.add_parser("evaluate")
    evaluate.add_argument("--scores", required=True, type=Path)
    evaluate.add_argument("--score-protocol", required=True, type=Path)
    evaluate.add_argument("--protocol", required=True, type=Path)
    evaluate.add_argument("--labels", required=True, type=Path)
    evaluate.add_argument("--out", required=True, type=Path)
    evaluate.add_argument("--allow-protected-development-labels", action="store_true")
    return result


def main(argv=None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.command == "freeze":
            payload = freeze_evaluation_protocol(
                score_root=args.scores,
                score_protocol_path=args.score_protocol,
                output_path=args.out,
            )
        else:
            payload = evaluate_development(
                score_root=args.scores,
                score_protocol_path=args.score_protocol,
                protocol_path=args.protocol,
                labels_path=args.labels,
                output_dir=args.out,
                allow_protected_development_labels=args.allow_protected_development_labels,
            )
    except PipelineError as exc:
        print(f"[ABORTADO] {exc}", file=sys.stderr)
        return 2
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
