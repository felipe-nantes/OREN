#!/usr/bin/env python3
"""Create or verify the signed LLD-MMRI v23 technical review."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from dtwin.benchmark.lld_mmri_v23_review import (
    create_lld_mmri_v23_review,
    verify_lld_mmri_v23_review,
)
from dtwin.core import PipelineError


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--panels", type=Path, required=True)
    parser.add_argument("--gallery", type=Path, required=True)
    parser.add_argument("--review", type=Path, required=True)
    parser.add_argument("--reviewer")
    parser.add_argument("--note", default="")
    parser.add_argument("--approve", action="store_true")
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()
    try:
        if args.verify_only:
            result = verify_lld_mmri_v23_review(
                panel_root=args.panels,
                gallery_root=args.gallery,
                review_path=args.review,
                expected_reviewer=args.reviewer,
            )
        else:
            result = create_lld_mmri_v23_review(
                panel_root=args.panels,
                gallery_root=args.gallery,
                output_path=args.review,
                reviewer=args.reviewer or "",
                approved=args.approve,
                note=args.note,
            )
    except (PipelineError, OSError) as exc:
        print(f"[ABORTADO] {exc}")
        return 1
    print(json.dumps(result, ensure_ascii=True, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
