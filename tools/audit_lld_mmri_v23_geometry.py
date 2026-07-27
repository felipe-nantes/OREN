#!/usr/bin/env python3
"""Audit all selected LLD-MMRI v23 images before automatic liver segmentation."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from dtwin.benchmark.lld_mmri_v23_geometry_audit import audit_lld_mmri_v23_geometry
from dtwin.core import PipelineError


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol-root", type=Path, required=True)
    parser.add_argument("--download-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        summary = audit_lld_mmri_v23_geometry(
            protocol_root=args.protocol_root,
            download_root=args.download_root,
            output_root=args.output,
        )
    except PipelineError as exc:
        print(f"[ABORTADO] {exc}")
        return 1
    print(json.dumps(summary, ensure_ascii=True, indent=2, sort_keys=True))
    return 0 if summary["technical_gate_passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
