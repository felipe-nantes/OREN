"""Build the reviewed OpenSwissHCC development cohort with complete coverage."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from dtwin.benchmark.openswisshcc_volumetric_batch import (
    build_volumetric_candidate_cohort,
)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs", type=Path, required=True)
    parser.add_argument("--alignments", type=Path, required=True)
    parser.add_argument("--source-panels", type=Path, required=True)
    parser.add_argument("--source-review", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--multiphase-config", type=Path, required=True)
    parser.add_argument("--fallback-config", type=Path, required=True)
    parser.add_argument("--high-contrast-fallback-config", type=Path, required=True)
    parser.add_argument("--source-high-contrast-config", type=Path, required=True)
    parser.add_argument("--profile", type=Path, default=Path("profiles/figado.yaml"))
    parser.add_argument("--expected-case-count", type=int, default=88)
    args = parser.parse_args(argv)
    result = build_volumetric_candidate_cohort(
        input_root=args.inputs,
        alignment_root=args.alignments,
        source_panel_root=args.source_panels,
        source_review_path=args.source_review,
        output_root=args.out,
        multiphase_config=args.multiphase_config,
        fallback_config=args.fallback_config,
        high_contrast_fallback_config=args.high_contrast_fallback_config,
        source_high_contrast_config=args.source_high_contrast_config,
        profile_path=args.profile,
        expected_case_count=args.expected_case_count,
    )
    print(
        json.dumps(
            {
                "case_count": result["case_count"],
                "panel_image_count": result["panel_image_count"],
                "max_panels_per_case": result["max_panels_per_case"],
                "cohort_signature": result["cohort_signature"],
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

