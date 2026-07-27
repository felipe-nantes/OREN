"""Profile the exact approved label-free OpenSwissHCC v10 ROI path."""
import argparse
import json
from pathlib import Path

from dtwin.benchmark.openswisshcc_localizer_roi_timing import profile_approved_roi_path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--morphology", type=Path, required=True)
    parser.add_argument("--enhancement", type=Path, required=True)
    parser.add_argument("--review", type=Path, required=True)
    parser.add_argument("--freeze", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--localizer-run", type=Path, required=True)
    parser.add_argument("--scores", type=Path, required=True)
    parser.add_argument("--input-manifest", type=Path, required=True)
    parser.add_argument("--input-root", type=Path, required=True)
    parser.add_argument("--registration-root", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--expected-case-count", type=int, default=10)
    parser.add_argument("--limit-seconds", type=float, default=180.0)
    args = parser.parse_args()
    result = profile_approved_roi_path(
        morphology_root=args.morphology,
        enhancement_root=args.enhancement,
        review_path=args.review,
        freeze_path=args.freeze,
        config_path=args.config,
        localizer_run=args.localizer_run,
        scores_root=args.scores,
        input_manifest=args.input_manifest,
        input_root=args.input_root,
        registration_root=args.registration_root,
        output_root=args.out,
        expected_case_count=args.expected_case_count,
        limit_seconds=args.limit_seconds,
    )
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
