#!/usr/bin/env python
"""Constrói, congela ou avalia a fusão cega OpenSwissHCC v20."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from dtwin.benchmark.openswisshcc_v20_fusion import (
    build_blind_fusion_bundle,
    create_fusion_protocol,
    evaluate_fusion_development,
)
from dtwin.core import PipelineError


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    build = commands.add_parser("build")
    build.add_argument("--v11-bundle", type=Path, required=True)
    build.add_argument("--v11-protocol", type=Path, required=True)
    build.add_argument("--v19-scores", type=Path, required=True)
    build.add_argument("--v19-protocol", type=Path, required=True)
    build.add_argument("--out", type=Path, required=True)
    freeze = commands.add_parser("freeze")
    freeze.add_argument("--bundle", type=Path, required=True)
    freeze.add_argument("--out", type=Path, required=True)
    evaluate = commands.add_parser("evaluate")
    evaluate.add_argument("--bundle", type=Path, required=True)
    evaluate.add_argument("--protocol", type=Path, required=True)
    evaluate.add_argument("--labels", type=Path, required=True)
    evaluate.add_argument("--out", type=Path, required=True)
    evaluate.add_argument("--allow-protected-development-labels", action="store_true")
    return parser


def main() -> int:
    args = _parser().parse_args()
    try:
        if args.command == "build":
            result = build_blind_fusion_bundle(
                v11_bundle_root=args.v11_bundle,
                v11_protocol_path=args.v11_protocol,
                v19_score_root=args.v19_scores,
                v19_score_protocol_path=args.v19_protocol,
                output_root=args.out,
            )
        elif args.command == "freeze":
            result = create_fusion_protocol(bundle_root=args.bundle, output_path=args.out)
        else:
            result = evaluate_fusion_development(
                bundle_root=args.bundle,
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

