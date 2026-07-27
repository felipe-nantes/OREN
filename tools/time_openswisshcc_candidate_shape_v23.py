#!/usr/bin/env python3
"""Measure the deterministic v23 shape overhead on the frozen full87 bundle."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from dtwin.benchmark.openswisshcc_candidate_shape_timing import measure_candidate_shape_timing
from dtwin.core import PipelineError


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--shape-root", type=Path, required=True)
    parser.add_argument("--localizer-root", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = measure_candidate_shape_timing(
            shape_root=args.shape_root,
            localizer_root=args.localizer_root,
            output_path=args.out,
        )
    except PipelineError as exc:
        print(f"[ABORTADO] {exc}")
        return 1
    print(json.dumps({
        "case_count": result["case_count"],
        "maximum_seconds": result["seconds"]["maximum"],
        "conservative_sum_seconds": result["conservative_precomputed_pipeline_seconds"]["sum"],
        "passed_180_seconds": result["conservative_precomputed_pipeline_seconds"]["passed_180_seconds"],
        "raw_dicom_end_to_end_proven": result["raw_dicom_end_to_end_180_seconds_proven"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
