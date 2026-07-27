#!/usr/bin/env python3
"""Prepare or verify the label-blind CHAOS v21 negative stress arm."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from dtwin.benchmark.chaos_v21_preparation import (
    prepare_chaos_v21_blind_inputs,
    verify_chaos_v21_blind_inputs,
)
from dtwin.core import PipelineError


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--extracted-root", type=Path)
    parser.add_argument("--bundle", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--expected-public-protocol-signature")
    parser.add_argument("--expected-prepared-signature")
    parser.add_argument("--expected-case-count", type=int, default=20)
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()
    try:
        if args.verify_only:
            result = verify_chaos_v21_blind_inputs(
                prepared_root=args.out,
                expected_cohort_signature=args.expected_prepared_signature,
                expected_case_count=args.expected_case_count,
            )
        else:
            if not args.extracted_root or not args.bundle or not args.expected_public_protocol_signature:
                parser.error("preparacao exige --extracted-root, --bundle e assinatura publica")
            result = prepare_chaos_v21_blind_inputs(
                extracted_root=args.extracted_root,
                bundle_root=args.bundle,
                output_root=args.out,
                expected_protocol_signature=args.expected_public_protocol_signature,
                expected_case_count=args.expected_case_count,
            )
    except PipelineError as exc:
        print(f"[ABORTADO] {exc}")
        return 1
    print(json.dumps(result, ensure_ascii=True, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

