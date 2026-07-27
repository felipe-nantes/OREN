#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from dtwin.benchmark.openswisshcc_v15_fusion import build_blind_fusion_bundle
from dtwin.core import PipelineError


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Constroi o bundle cego combinado v11 + v15.")
    parser.add_argument("--v11-bundle-root", required=True, type=Path)
    parser.add_argument("--v11-protocol", required=True, type=Path)
    parser.add_argument("--v15-run-root", required=True, type=Path)
    parser.add_argument("--v15-protocol", required=True, type=Path)
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument("--expected-case-count", type=int, default=87)
    args = parser.parse_args(argv)
    try:
        result = build_blind_fusion_bundle(
            v11_bundle_root=args.v11_bundle_root,
            v11_protocol_path=args.v11_protocol,
            v15_run_root=args.v15_run_root,
            v15_protocol_path=args.v15_protocol,
            output_root=args.output_root,
            expected_case_count=args.expected_case_count,
        )
    except PipelineError as exc:
        print(f"[ABORTADO] {exc}", flush=True)
        return 1
    print(json.dumps(result, ensure_ascii=False, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
