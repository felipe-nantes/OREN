#!/usr/bin/env python3
"""Freeze independent LLD-MMRI HCC-versus-benign validation metadata."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from dtwin.benchmark.lld_mmri_v23_external import freeze_lld_mmri_v23_external_protocol
from dtwin.core import PipelineError


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--annotation", type=Path, required=True)
    parser.add_argument("--calibrator", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = freeze_lld_mmri_v23_external_protocol(
            annotation_path=args.annotation,
            calibrator_path=args.calibrator,
            output_dir=args.out,
        )
    except PipelineError as exc:
        print(f"[ABORTADO] {exc}")
        return 1
    print(json.dumps({
        "status": result["status"],
        "case_count": result["case_count"],
        "positive_count": result["positive_count"],
        "negative_count": result["negative_count"],
        "protocol_signature": result["protocol_signature"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
