#!/usr/bin/env python3
"""Run a label-blind LLD-MMRI v23 segmentation timing pilot."""
from __future__ import annotations

import argparse
import functools
import json
import traceback
from pathlib import Path

from dtwin.benchmark.lld_mmri_v23_mask_quality import (
    MASK_QUALITY_POLICY,
    anatomically_gated_segmenter,
)
from dtwin.benchmark.lld_mmri_v23_preparation import (
    isolated_total_mr_liver_segmenter,
    total_mr_liver_segmenter,
)
from dtwin.benchmark.lld_mmri_v23_segmentation_pilot import (
    run_lld_mmri_v23_segmentation_pilot,
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
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--cases", type=int, default=5)
    parser.add_argument(
        "--selection",
        choices=("first_n", "lowest_whole_grid_support"),
        default="first_n",
    )
    parser.add_argument("--device", default="gpu")
    parser.add_argument("--fast", action="store_true")
    parser.add_argument(
        "--fallback-full",
        action="store_true",
        help="When --fast is primary, retry with full resolution after a technical or anatomical failure.",
    )
    parser.add_argument(
        "--anatomical-quality-gate",
        action="store_true",
        help="Require physical-volume, extent and connectivity plausibility and retain only the largest 3D component.",
    )
    parser.add_argument("--isolate-attempts", action="store_true")
    parser.add_argument("--attempt-timeout-seconds", type=int, default=75)
    parser.add_argument(
        "--disable-fast-fallback",
        action="store_true",
        help="Do not retry a failed full-resolution mask with the 3 mm model.",
    )
    parser.add_argument(
        "--continue-on-technical-failure",
        action="store_true",
        help="Record an automatic-segmentation failure and continue the blind audit; it counts as an error.",
    )
    args = parser.parse_args()
    segmenter_function = (
        isolated_total_mr_liver_segmenter
        if args.isolate_attempts
        else total_mr_liver_segmenter
    )
    isolated_options = (
        {"timeout_seconds": args.attempt_timeout_seconds}
        if args.isolate_attempts else {}
    )
    segmenter = functools.partial(
        segmenter_function, device=args.device, fast=args.fast, **isolated_options
    )
    fallback_segmenter = None
    if not args.fast and not args.disable_fast_fallback:
        fallback_segmenter = functools.partial(
            segmenter_function, device=args.device, fast=True, **isolated_options
        )
    elif args.fast and args.fallback_full:
        fallback_segmenter = functools.partial(
            segmenter_function, device=args.device, fast=False, **isolated_options
        )
    if args.anatomical_quality_gate:
        segmenter = functools.partial(anatomically_gated_segmenter, segmenter=segmenter)
        if fallback_segmenter is not None:
            fallback_segmenter = functools.partial(
                anatomically_gated_segmenter, segmenter=fallback_segmenter
            )
    try:
        with block_optional_module_for_spawn("pyarrow"):
            result = run_lld_mmri_v23_segmentation_pilot(
                protocol_root=args.protocol_root,
                download_root=args.download_root,
                geometry_audit_root=args.geometry_audit,
                failed_audit_root=args.failed_audit,
                harmonization_root=args.harmonization,
                output_root=args.output,
                segment_liver=segmenter,
                fallback_segment_liver=fallback_segmenter,
                case_count=args.cases,
                selection=args.selection,
                continue_on_technical_failure=args.continue_on_technical_failure,
                primary_attempt_name=(
                    "primary_fast_3mm" if args.fast else "primary_full_resolution"
                ),
                fallback_attempt_name=(
                    "fallback_full_resolution" if args.fast else "fallback_fast_3mm"
                ),
                mask_quality_policy=(
                    MASK_QUALITY_POLICY
                    if args.anatomical_quality_gate
                    else "legacy_voxel_geometry_v1"
                ),
                progress=lambda item: print(json.dumps(item, sort_keys=True), flush=True),
            )
    except PipelineError as exc:
        traceback.print_exc()
        print(f"[ABORTADO] {exc}")
        return 1
    print(json.dumps(result, ensure_ascii=True, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
