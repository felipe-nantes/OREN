#!/usr/bin/env python3
"""Build blind whole-liver enhancement proposals for OpenSwissHCC v22."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from dtwin.benchmark.openswisshcc_enhancement_localizer import (
    build_enhancement_localizer_cohort,
)
from dtwin.core import PipelineError


def _progress(index: int, total: int, case_id: str, elapsed: float) -> None:
    print(
        f"[v22-realce-localizador] {index:02d}/{total}: {case_id} | {elapsed:.1f}s",
        file=sys.stderr,
        flush=True,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--inputs-root", type=Path, required=True)
    parser.add_argument("--alignment-root", type=Path, required=True)
    parser.add_argument("--selection-manifest", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = build_enhancement_localizer_cohort(
            input_manifest_path=args.manifest,
            input_root=args.inputs_root,
            alignment_root=args.alignment_root,
            selection_manifest_path=args.selection_manifest,
            output_root=args.out,
            progress=_progress,
        )
    except PipelineError as exc:
        print(f"[ABORTADO] {exc}")
        return 1
    print(json.dumps(result, ensure_ascii=True, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
