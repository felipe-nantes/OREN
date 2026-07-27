#!/usr/bin/env python3
"""Run one label-blind TotalSegmentator liver fallback and report only technical gates."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import SimpleITK as sitk

from dtwin.benchmark.lld_mmri_v23_preparation import (
    _same_geometry,
    liver_segments_mr_union_segmenter,
    total_mr_liver_segmenter,
)
from dtwin.benchmark.windows_spawn_guard import block_optional_module_for_spawn
from dtwin.core import PipelineError


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--device", default="gpu")
    parser.add_argument("--fast", action="store_true")
    parser.add_argument(
        "--mode",
        choices=("total_mr", "liver_segments_mr"),
        default="total_mr",
    )
    args = parser.parse_args()
    try:
        reference = sitk.ReadImage(str(args.input.resolve()))
        with block_optional_module_for_spawn("pyarrow"):
            if args.mode == "liver_segments_mr":
                receipt = liver_segments_mr_union_segmenter(
                    args.input, args.output, device=args.device
                )
            else:
                receipt = total_mr_liver_segmenter(
                    args.input,
                    args.output,
                    device=args.device,
                    fast=args.fast,
                )
        mask = sitk.ReadImage(str(args.output.resolve()))
        voxels = int((np.asarray(sitk.GetArrayFromImage(mask)) > 0).sum())
        result = {
            "status": "complete_label_blind_technical_diagnostic",
            "same_geometry": _same_geometry(reference, mask),
            "liver_voxels": voxels,
            "minimum_liver_voxels": 300,
            "gate_passed": _same_geometry(reference, mask) and voxels >= 300,
            "receipt": receipt,
            "ground_truth_read": False,
            "lesion_masks_read": 0,
        }
    except (PipelineError, OSError, RuntimeError) as exc:
        print(f"[ABORTADO] {exc}")
        return 1
    print(json.dumps(result, ensure_ascii=True, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
