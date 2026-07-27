#!/usr/bin/env python3
"""Harmonize LLD-MMRI v23 dynamic T1 grids to the venous physical grid."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from dtwin.benchmark.lld_mmri_v23_harmonization import (
    harmonize_lld_mmri_v23_dynamic_t1,
    verify_lld_mmri_v23_harmonization,
)
from dtwin.core import PipelineError


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol-root", type=Path, required=True)
    parser.add_argument("--download-root", type=Path, required=True)
    parser.add_argument("--failed-audit", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()
    try:
        if args.verify_only:
            result = verify_lld_mmri_v23_harmonization(
                protocol_root=args.protocol_root,
                download_root=args.download_root,
                failed_audit_root=args.failed_audit,
                harmonization_root=args.output,
            )
        else:
            result = harmonize_lld_mmri_v23_dynamic_t1(
                protocol_root=args.protocol_root,
                download_root=args.download_root,
                failed_audit_root=args.failed_audit,
                output_root=args.output,
            )
    except PipelineError as exc:
        print(f"[ABORTADO] {exc}")
        return 1
    print(json.dumps(result, ensure_ascii=True, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
