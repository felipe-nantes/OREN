"""Record immutable human approval of all OpenSwissHCC volumetric panels."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from dtwin.benchmark.openswisshcc_volumetric_gate import (
    create_volumetric_review,
    verify_volumetric_review,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--panels", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--reviewer", required=True)
    parser.add_argument("--expected-case-count", type=int, default=88)
    parser.add_argument("--confirm-no-visible-phi", action="store_true")
    parser.add_argument("--confirm-all-panels", action="store_true")
    parser.add_argument("--confirm-liver-framing", action="store_true")
    parser.add_argument("--confirm-alignment", action="store_true")
    parser.add_argument("--confirm-volumetric-sequence", action="store_true")
    args = parser.parse_args()
    review = create_volumetric_review(
        panel_root=args.panels,
        output_path=args.out,
        reviewer=args.reviewer,
        expected_case_count=args.expected_case_count,
        confirmations={
            "no_visible_phi": args.confirm_no_visible_phi,
            "all_panels_open_and_uncorrupted": args.confirm_all_panels,
            "liver_framing_acceptable": args.confirm_liver_framing,
            "multiphase_alignment_acceptable": args.confirm_alignment,
            "volumetric_sequence_acceptable": args.confirm_volumetric_sequence,
        },
    )
    verify_volumetric_review(
        review_path=args.out,
        panel_root=args.panels,
        expected_case_count=args.expected_case_count,
    )
    print(json.dumps({
        "review_manifest": str(args.out.resolve()),
        "case_count": review["case_count"],
        "panel_image_count": review["panel_image_count"],
        "review_signature": review["review_signature"],
        "verified": True,
    }, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
