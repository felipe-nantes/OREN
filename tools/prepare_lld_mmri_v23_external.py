#!/usr/bin/env python3
"""Prepare verified LLD-MMRI images with automatic label-blind liver masks."""
from __future__ import annotations

import argparse
import functools
import json
from pathlib import Path

from dtwin.benchmark.lld_mmri_v23_preparation import (
    prepare_lld_mmri_v23_blind_inputs,
    total_mr_liver_segmenter,
)
from dtwin.benchmark.windows_spawn_guard import block_optional_module_for_spawn
from dtwin.core import PipelineError


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol-root", type=Path, required=True)
    parser.add_argument("--download-root", type=Path, required=True)
    parser.add_argument("--geometry-audit", type=Path)
    parser.add_argument("--failed-audit", type=Path)
    parser.add_argument("--harmonization", type=Path)
    parser.add_argument("--segmentation-audit", type=Path)
    parser.add_argument("--segmentation-audit-signature")
    parser.add_argument("--technical-amendment", type=Path)
    parser.add_argument("--technical-amendment-signature")
    parser.add_argument("--config", type=Path)
    parser.add_argument("--profile", type=Path)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--device", default="gpu")
    parser.add_argument("--fast", action="store_true")
    args = parser.parse_args()
    segmenter = functools.partial(
        total_mr_liver_segmenter,
        device=args.device,
        fast=args.fast,
    )
    try:
        with block_optional_module_for_spawn("pyarrow"):
            result = prepare_lld_mmri_v23_blind_inputs(
                protocol_root=args.protocol_root,
                download_root=args.download_root,
                geometry_audit_root=args.geometry_audit,
                failed_audit_root=args.failed_audit,
                harmonization_root=args.harmonization,
                segmentation_audit_root=args.segmentation_audit,
                expected_segmentation_audit_signature=args.segmentation_audit_signature,
                technical_amendment_root=args.technical_amendment,
                expected_technical_amendment_signature=args.technical_amendment_signature,
                config_path=args.config,
                profile_path=args.profile,
                output_root=args.output_root,
                segment_liver=segmenter,
            )
    except (PipelineError, OSError) as exc:
        print(f"[ABORTADO] {exc}")
        return 1
    print(
        json.dumps(
            {
                "status": result["status"],
                "case_count": result["case_count"],
                "preparation_signature": result["preparation_signature"],
                "fast": args.fast,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
