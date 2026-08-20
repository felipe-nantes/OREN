"""Freeze the reviewed OpenSwissHCC v10 paired-ROI MedGemma 4B experiment."""
import argparse
import json
from pathlib import Path

from dtwin.benchmark.openswisshcc_localizer_roi_freeze import (
    create_roi_freeze,
    verify_roi_freeze,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--morphology", type=Path, required=True)
    parser.add_argument("--enhancement", type=Path, required=True)
    parser.add_argument("--review", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--experiment-version", required=True)
    parser.add_argument("--expected-case-count", type=int, default=10)
    args = parser.parse_args()
    freeze = create_roi_freeze(morphology_root=args.morphology, enhancement_root=args.enhancement, review_path=args.review, config_path=args.config, output_path=args.out, experiment_version=args.experiment_version, expected_case_count=args.expected_case_count)
    verify_roi_freeze(morphology_root=args.morphology, enhancement_root=args.enhancement, review_path=args.review, config_path=args.config, freeze_path=args.out, expected_case_count=args.expected_case_count)
    print(json.dumps({"experiment_version": freeze["experiment_version"], "case_count": freeze["case_count"], "panel_pairs": freeze["panel_pairs"], "experiment_signature": freeze["experiment_signature"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
