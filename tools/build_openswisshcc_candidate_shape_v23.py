#!/usr/bin/env python3
"""Build label-blind physical-shape features for v23 candidates."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from dtwin.benchmark.openswisshcc_candidate_shape import (
    _stderr_progress,
    build_candidate_shape_cohort,
)
from dtwin.core import PipelineError


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--inputs-root", type=Path, required=True)
    parser.add_argument("--selection-manifest", type=Path, required=True)
    parser.add_argument("--localizer-root", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = build_candidate_shape_cohort(
            input_manifest_path=args.manifest,
            input_root=args.inputs_root,
            selection_manifest_path=args.selection_manifest,
            localizer_root=args.localizer_root,
            output_dir=args.out,
            progress=_stderr_progress,
        )
    except PipelineError as exc:
        print(f"[ABORTADO] {exc}")
        return 1
    print(json.dumps(result, ensure_ascii=True, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
