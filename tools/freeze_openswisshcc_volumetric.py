"""Freeze reviewed OpenSwissHCC volumetric panels and MedGemma 4B configs."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from dtwin.benchmark.openswisshcc_volumetric_gate import (
    create_volumetric_freeze,
    verify_volumetric_freeze,
)


def _configs(args: argparse.Namespace) -> dict[str, Path]:
    return {
        "multiphase": args.multiphase_config,
        "venous": args.venous_config,
        "venous_high_contrast": args.venous_high_contrast_config,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--panels", required=True, type=Path)
    parser.add_argument("--review", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--multiphase-config", required=True, type=Path)
    parser.add_argument("--venous-config", required=True, type=Path)
    parser.add_argument("--venous-high-contrast-config", required=True, type=Path)
    parser.add_argument("--experiment-version", required=True)
    parser.add_argument("--expected-case-count", type=int, default=88)
    parser.add_argument("--max-case-seconds", type=float, default=180.0)
    args = parser.parse_args()
    freeze = create_volumetric_freeze(
        panel_root=args.panels,
        review_path=args.review,
        config_paths=_configs(args),
        output_path=args.out,
        experiment_version=args.experiment_version,
        expected_case_count=args.expected_case_count,
        max_case_seconds=args.max_case_seconds,
    )
    verify_volumetric_freeze(
        freeze_path=args.out,
        panel_root=args.panels,
        review_path=args.review,
        config_paths=_configs(args),
        expected_case_count=args.expected_case_count,
    )
    print(json.dumps({
        "freeze_manifest": str(args.out.resolve()),
        "case_count": freeze["case_count"],
        "panel_image_count": freeze["panel_image_count"],
        "experiment_signature": freeze["experiment_signature"],
        "verified": True,
    }, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
