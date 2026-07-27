from __future__ import annotations

import argparse
import json
from pathlib import Path

from dtwin.benchmark.openswisshcc_candidate_volume_review import (
    REQUIRED_CONFIRMATIONS,
    record_candidate_volume_review,
)
from dtwin.core import PipelineError


def main() -> int:
    parser = argparse.ArgumentParser(description="Registra a revisao humana tecnica da galeria v16.")
    parser.add_argument("--bundle-root", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--reviewer", required=True)
    decision = parser.add_mutually_exclusive_group(required=True)
    decision.add_argument("--approve", action="store_true")
    decision.add_argument("--reject", action="store_true")
    parser.add_argument("--notes", default="")
    for key in REQUIRED_CONFIRMATIONS:
        parser.add_argument(f"--confirm-{key.replace('_', '-')}", action="store_true")
    args = parser.parse_args()
    confirmations = {
        key: bool(getattr(args, f"confirm_{key}"))
        for key in REQUIRED_CONFIRMATIONS
    }
    try:
        result = record_candidate_volume_review(
            bundle_root=args.bundle_root,
            out_path=args.out,
            reviewer=args.reviewer,
            confirmations=confirmations,
            approved=args.approve,
            notes=args.notes,
        )
    except PipelineError as exc:
        print(f"[ABORTADO] {exc}")
        return 1
    print(json.dumps({
        "status": result["status"],
        "reviewer": result["reviewer"],
        "review_signature": result["review_signature"],
        "ground_truth_read": result["ground_truth_read"],
        "holdout_opened": result["holdout_opened"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

