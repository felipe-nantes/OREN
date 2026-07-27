#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from dtwin.benchmark.openswisshcc_v15_fusion import create_fusion_protocol
from dtwin.core import PipelineError


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Congela a avaliacao v15 antes dos labels protegidos.")
    parser.add_argument("--bundle-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--expected-case-count", type=int, default=87)
    args = parser.parse_args(argv)
    try:
        result = create_fusion_protocol(
            bundle_root=args.bundle_root,
            output_path=args.output,
            expected_case_count=args.expected_case_count,
        )
    except PipelineError as exc:
        print(f"[ABORTADO] {exc}", flush=True)
        return 1
    print(json.dumps(result, ensure_ascii=False, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
