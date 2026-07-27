#!/usr/bin/env python3
"""Audit a frozen v22 arterial-union pilot against authorized development masks."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from dtwin.benchmark.openswisshcc_multiphase_localizer_audit import (
    audit_arterial_union_pilot,
)
from dtwin.core import PipelineError


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--union-localizer-root", type=Path, required=True)
    parser.add_argument("--venous-localizer-root", type=Path, required=True)
    parser.add_argument("--authorized-extraction-root", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = audit_arterial_union_pilot(
            union_localizer_root=args.union_localizer_root,
            venous_localizer_root=args.venous_localizer_root,
            authorized_extraction_root=args.authorized_extraction_root,
            output_root=args.out,
        )
    except PipelineError as exc:
        print(f"[ABORTADO] {exc}")
        return 1
    print(json.dumps(result, ensure_ascii=True, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
