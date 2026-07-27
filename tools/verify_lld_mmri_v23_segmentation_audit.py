#!/usr/bin/env python3
"""Independently verify a completed label-blind LLD-MMRI v23 segmentation audit."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from dtwin.benchmark.lld_mmri_v23_segmentation_pilot import (
    verify_lld_mmri_v23_segmentation_pilot,
)
from dtwin.core import PipelineError


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol-root", type=Path, required=True)
    parser.add_argument("--download-root", type=Path, required=True)
    parser.add_argument("--geometry-audit", type=Path)
    parser.add_argument("--failed-audit", type=Path)
    parser.add_argument("--harmonization", type=Path)
    parser.add_argument("--segmentation-audit", type=Path, required=True)
    parser.add_argument("--expected-signature")
    args = parser.parse_args()
    try:
        result = verify_lld_mmri_v23_segmentation_pilot(
            protocol_root=args.protocol_root,
            download_root=args.download_root,
            geometry_audit_root=args.geometry_audit,
            failed_audit_root=args.failed_audit,
            harmonization_root=args.harmonization,
            pilot_root=args.segmentation_audit,
            expected_pilot_signature=args.expected_signature,
        )
    except (PipelineError, OSError) as exc:
        print(f"[ABORTADO] {exc}")
        return 1
    print(
        json.dumps(
            {
                "status": "verified_label_blind_segmentation_audit",
                "case_count": result["case_count"],
                "pilot_signature": result["pilot_signature"],
                "fallback_case_count": result.get("segmentation_fallback_case_count", 0),
                "technical_failure_case_count": result.get("segmentation_technical_failure_case_count", 0),
                "ground_truth_read": result["ground_truth_read"],
                "lesion_masks_read": result["lesion_masks_read"],
            },
            ensure_ascii=True,
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
