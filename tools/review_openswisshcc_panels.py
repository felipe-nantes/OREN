"""Registra e verifica a revisão humana dos painéis OpenSwissHCC."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from dtwin.benchmark.openswisshcc_review import (
    create_panel_review,
    ready_case_ids,
    verify_panel_review,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Cria uma aprovação imutável ligada aos hashes dos painéis revisados."
    )
    parser.add_argument("--panels", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--reviewer", required=True)
    selection = parser.add_mutually_exclusive_group(required=True)
    selection.add_argument("--all-ready", action="store_true")
    selection.add_argument("--case-id", action="append")
    parser.add_argument("--confirm-no-visible-phi", action="store_true")
    parser.add_argument("--confirm-alignment", action="store_true")
    parser.add_argument("--confirm-liver-framing", action="store_true")
    args = parser.parse_args()

    case_ids = ready_case_ids(args.panels) if args.all_ready else args.case_id
    result = create_panel_review(
        panel_root=args.panels,
        case_ids=case_ids,
        output_path=args.out,
        reviewer=args.reviewer,
        confirmations={
            "no_visible_phi": args.confirm_no_visible_phi,
            "multiphase_alignment_acceptable": args.confirm_alignment,
            "liver_framing_acceptable": args.confirm_liver_framing,
        },
    )
    verify_panel_review(
        review_path=args.out,
        panel_root=args.panels,
        required_case_ids=case_ids,
    )
    print(
        json.dumps(
            {
                "review_manifest": str(args.out.resolve()),
                "panel_count": result["panel_count"],
                "review_signature": result["review_signature"],
                "verified": True,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
