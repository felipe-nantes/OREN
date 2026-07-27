#!/usr/bin/env python3
"""Freeze the label-blind technical amendment for LLD-MMRI v23."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from dtwin.benchmark.lld_mmri_v23_technical_amendment import (
    freeze_lld_mmri_v23_technical_amendment,
)
from dtwin.core import PipelineError


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol-root", type=Path, required=True)
    parser.add_argument("--download-root", type=Path, required=True)
    parser.add_argument("--failed-audit", type=Path, required=True)
    parser.add_argument("--harmonization", type=Path, required=True)
    parser.add_argument("--segmentation-audit", type=Path, required=True)
    parser.add_argument("--segmentation-audit-signature")
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = freeze_lld_mmri_v23_technical_amendment(
            protocol_root=args.protocol_root,
            download_root=args.download_root,
            failed_audit_root=args.failed_audit,
            harmonization_root=args.harmonization,
            segmentation_audit_root=args.segmentation_audit,
            expected_segmentation_audit_signature=args.segmentation_audit_signature,
            config_path=args.config,
            profile_path=args.profile,
            output_root=args.output,
        )
    except (PipelineError, OSError) as exc:
        print(f"[ABORTADO] {exc}")
        return 1
    print(json.dumps(result, ensure_ascii=True, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
