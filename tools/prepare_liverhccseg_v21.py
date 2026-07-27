"""Prepare registered and label-blind LiverHccSeg v21 inputs."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from dtwin.benchmark.liverhccseg_preparation import (
    prepare_liverhccseg_blind_inputs,
    verify_liverhccseg_blind_inputs,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--selection-audit", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--expected-case-count", type=int, default=14)
    parser.add_argument("--verify-only", action="store_true")
    parser.add_argument("--expected-signature")
    args = parser.parse_args(argv)
    if args.verify_only:
        result = verify_liverhccseg_blind_inputs(
            prepared_root=args.out,
            expected_cohort_signature=args.expected_signature,
            expected_case_count=args.expected_case_count,
        )
        print(json.dumps(result, sort_keys=True))
        return 0
    result = prepare_liverhccseg_blind_inputs(
        source_root=args.source,
        protected_selection_audit_path=args.selection_audit,
        output_root=args.out,
        expected_case_count=args.expected_case_count,
    )
    print(json.dumps({
        "case_count": result["case_count"],
        "cohort_signature": result["cohort_signature"],
        "lesion_masks_copied": result["lesion_masks_copied"],
        "holdout_opened": result["holdout_opened"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
