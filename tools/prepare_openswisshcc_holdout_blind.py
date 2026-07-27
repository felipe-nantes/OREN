#!/usr/bin/env python3
"""Prepare OpenSwissHCC subjects 045–088 without reading labels or lesion masks."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from dtwin.benchmark.openswisshcc_holdout import prepare_holdout_dataset_label_blind


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--allowed-derivatives", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = prepare_holdout_dataset_label_blind(
        archive=args.archive,
        allowed_derivatives_dir=args.allowed_derivatives,
        output_dir=args.out,
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
