#!/usr/bin/env python
"""Gera o piloto cego do atlas axial OpenSwissHCC v17."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from dtwin.benchmark.openswisshcc_axial_atlas import (
    PROTOCOL_SIGNATURE,
    build_axial_atlas_cohort,
    build_axial_atlas_gallery,
    case_ids_from_cohort_manifest,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--pilot-cohort", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--gallery-root", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    case_ids = case_ids_from_cohort_manifest(args.pilot_cohort)
    cohort = build_axial_atlas_cohort(args.source_root, args.output_root, case_ids)
    gallery = build_axial_atlas_gallery(args.output_root, args.gallery_root)
    print(
        json.dumps(
            {
                "protocol_signature": PROTOCOL_SIGNATURE,
                "case_count": cohort["case_count"],
                "frame_count": cohort["frame_count"],
                "tile_count": cohort["tile_count"],
                "all_gates_passed": cohort["all_gates_passed"],
                "gallery_case_count": gallery["case_count"],
                "gallery": str((args.gallery_root / "index.html").resolve()),
                "ground_truth_read": False,
                "lesion_mask_read": False,
                "holdout_read": False,
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
