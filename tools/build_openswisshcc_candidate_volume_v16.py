"""Build the blind OpenSwissHCC v16 candidate-volume technical pilot."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from dtwin.benchmark.openswisshcc_candidate_volume import build_candidate_volume_pilot


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--review", type=Path, required=True)
    parser.add_argument("--localizer-run", type=Path, required=True)
    parser.add_argument("--input-manifest", type=Path, required=True)
    parser.add_argument("--input-root", type=Path, required=True)
    parser.add_argument("--registration-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--expected-source-case-count", type=int, default=88)
    parser.add_argument("--minimum-candidates", type=int, default=3)
    parser.add_argument("--maximum-candidates", type=int, default=5)
    parser.add_argument("--candidate-target-fraction", type=float, default=0.75)
    args = parser.parse_args()
    result = build_candidate_volume_pilot(
        review_path=args.review,
        localizer_run=args.localizer_run,
        input_manifest=args.input_manifest,
        input_root=args.input_root,
        registration_root=args.registration_root,
        output_root=args.output_root,
        expected_source_case_count=args.expected_source_case_count,
        minimum_candidates=args.minimum_candidates,
        maximum_candidates=args.maximum_candidates,
        candidate_target_fraction=args.candidate_target_fraction,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
