"""Evaluate a complete frozen OpenSwissHCC volumetric development run."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from dtwin.benchmark.openswisshcc_volumetric_evaluation import (
    evaluate_volumetric_development_run,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--panels", required=True, type=Path)
    parser.add_argument("--review", required=True, type=Path)
    parser.add_argument("--freeze", required=True, type=Path)
    parser.add_argument("--inference", required=True, type=Path)
    parser.add_argument("--labels", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--multiphase-config", required=True, type=Path)
    parser.add_argument("--venous-config", required=True, type=Path)
    parser.add_argument("--venous-high-contrast-config", required=True, type=Path)
    parser.add_argument("--expected-case-count", type=int, default=88)
    parser.add_argument("--expected-positive", type=int, default=39)
    parser.add_argument("--expected-negative", type=int, default=49)
    args = parser.parse_args()
    result = evaluate_volumetric_development_run(
        panel_root=args.panels, review_path=args.review, freeze_path=args.freeze,
        inference_root=args.inference, protected_labels_path=args.labels, output_dir=args.out,
        config_paths={
            "multiphase": args.multiphase_config,
            "venous": args.venous_config,
            "venous_high_contrast": args.venous_high_contrast_config,
        },
        expected_case_count=args.expected_case_count,
        expected_positive=args.expected_positive,
        expected_negative=args.expected_negative,
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
