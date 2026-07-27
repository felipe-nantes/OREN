#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from dtwin.benchmark.openswisshcc_highdimensional_batch import (
    prepare_highdimensional_blind_bundle,
)
from dtwin.core import PipelineError


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Prepara o bundle cego high-dimensional.")
    parser.add_argument("--source-summary", required=True, type=Path)
    parser.add_argument("--inputs-manifest", required=True, type=Path)
    parser.add_argument("--input-root", required=True, type=Path)
    parser.add_argument("--out-root", required=True, type=Path)
    parser.add_argument("--max-slices", type=int, default=50)
    args = parser.parse_args(argv)
    try:
        bundle = prepare_highdimensional_blind_bundle(
            source_summary_path=args.source_summary,
            inputs_manifest_path=args.inputs_manifest,
            input_root=args.input_root,
            out_root=args.out_root,
            maximum_slices=args.max_slices,
        )
    except PipelineError as exc:
        print(f"[ABORTADO] {exc}")
        return 1
    print(json.dumps({
        "case_count": bundle["case_count"],
        "maximum_slices": bundle["maximum_slices"],
        "bundle_signature": bundle["bundle_signature"],
        "ground_truth_read": bundle["ground_truth_read"],
        "holdout_opened": bundle["holdout_opened"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
