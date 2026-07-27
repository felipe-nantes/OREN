#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from dtwin.benchmark.openswisshcc_v11_v13_complementarity import (
    analyze_v11_v13_complementarity,
)
from dtwin.core import PipelineError


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Compara erros v11 LOOCV e v13 somente no desenvolvimento."
    )
    parser.add_argument("--v11-bundle-root", required=True, type=Path)
    parser.add_argument("--v11-protocol", required=True, type=Path)
    parser.add_argument("--v13-cases", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        result = analyze_v11_v13_complementarity(
            v11_bundle_root=args.v11_bundle_root,
            v11_protocol_path=args.v11_protocol,
            v13_cases_path=args.v13_cases,
        )
    except PipelineError as exc:
        print(f"[ABORTADO] {exc}", flush=True)
        return 1
    public = {key: value for key, value in result.items() if key != "case_rows"}
    print(json.dumps(public, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

