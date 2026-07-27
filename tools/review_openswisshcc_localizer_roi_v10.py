"""Sign the explicit human approval of paired OpenSwissHCC v10 ROI galleries."""
import argparse
import json
from pathlib import Path

from dtwin.benchmark.openswisshcc_localizer_roi_gate import REQUIRED_CONFIRMATIONS, create_paired_review, verify_paired_review


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--morphology", type=Path, required=True)
    parser.add_argument("--enhancement", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--reviewer", required=True)
    parser.add_argument("--expected-case-count", type=int, default=10)
    args = parser.parse_args()
    review = create_paired_review(morphology_root=args.morphology, enhancement_root=args.enhancement, output_path=args.out, reviewer=args.reviewer, confirmations={key: True for key in REQUIRED_CONFIRMATIONS}, expected_case_count=args.expected_case_count)
    verify_paired_review(morphology_root=args.morphology, enhancement_root=args.enhancement, review_path=args.out, expected_case_count=args.expected_case_count)
    print(json.dumps({"case_count": review["case_count"], "panel_pairs": review["panel_pairs"], "reviewer": review["reviewer"], "review_signature": review["review_signature"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
