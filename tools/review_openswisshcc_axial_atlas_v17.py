#!/usr/bin/env python
"""Registra o gate humano assinado do atlas axial v17."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from dtwin.benchmark.openswisshcc_axial_atlas import (
    REQUIRED_REVIEW_CONFIRMATIONS,
    record_axial_atlas_review,
)
from dtwin.core import PipelineError


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gallery-root", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--reviewer", required=True)
    parser.add_argument(
        "--scope",
        choices=("full87_generation", "blind_4b_scoring"),
        default="full87_generation",
    )
    decision = parser.add_mutually_exclusive_group(required=True)
    decision.add_argument("--approve", action="store_true")
    decision.add_argument("--reject", action="store_true")
    parser.add_argument("--notes", default="")
    for key in REQUIRED_REVIEW_CONFIRMATIONS:
        parser.add_argument(f"--confirm-{key.replace('_', '-')}", action="store_true")
    args = parser.parse_args()
    confirmations = {
        key: bool(getattr(args, f"confirm_{key}"))
        for key in REQUIRED_REVIEW_CONFIRMATIONS
    }
    try:
        review = record_axial_atlas_review(
            gallery_root=args.gallery_root,
            out_path=args.out,
            reviewer=args.reviewer,
            confirmations=confirmations,
            approved=args.approve,
            notes=args.notes,
            approval_scope=args.scope,
        )
    except PipelineError as exc:
        print(f"[ABORTADO] {exc}")
        return 1
    print(
        json.dumps(
            {
                "status": review["status"],
                "reviewer": review["reviewer"],
                "review_signature": review["review_signature"],
                "case_count": review["case_count"],
                "frame_count": review["frame_count"],
                "ground_truth_read": review["ground_truth_read"],
                "holdout_read": review["holdout_read"],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
