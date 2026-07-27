#!/usr/bin/env python3
"""Download and verify the official CHAOS v1.03 train archive."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from dtwin.core import PipelineError
from dtwin.datasets.chaos_download import download_chaos_train


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--accepted-by", required=True)
    parser.add_argument("--accept-license", action="store_true")
    args = parser.parse_args()
    try:
        result = download_chaos_train(
            output_dir=args.out,
            accept_license=args.accept_license,
            accepted_by=args.accepted_by,
        )
    except PipelineError as exc:
        print(f"[ABORTADO] {exc}")
        return 1
    print(json.dumps(result, ensure_ascii=True, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

