#!/usr/bin/env python3
"""Isolated one-shot TotalSegmentator worker for label-blind LLD-MMRI v23."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from dtwin.benchmark.lld_mmri_v23_preparation import total_mr_liver_segmenter
from dtwin.benchmark.windows_spawn_guard import block_optional_module_for_spawn


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--device", default="gpu")
    parser.add_argument("--fast", action="store_true")
    args = parser.parse_args()
    with block_optional_module_for_spawn("pyarrow"):
        receipt = total_mr_liver_segmenter(
            args.source,
            args.output,
            device=args.device,
            fast=args.fast,
        )
    args.receipt.write_text(
        json.dumps(receipt, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
