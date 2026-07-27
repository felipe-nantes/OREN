"""Infer one case from a frozen OpenSwissHCC volumetric experiment."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from dtwin.benchmark.openswisshcc_volumetric_inference import (
    infer_frozen_volumetric_case,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--panels", required=True, type=Path)
    parser.add_argument("--review", required=True, type=Path)
    parser.add_argument("--freeze", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--multiphase-config", required=True, type=Path)
    parser.add_argument("--venous-config", required=True, type=Path)
    parser.add_argument("--venous-high-contrast-config", required=True, type=Path)
    parser.add_argument("--expected-case-count", type=int, default=88)
    args = parser.parse_args()
    result = infer_frozen_volumetric_case(
        case_id=args.case_id,
        panel_root=args.panels,
        review_path=args.review,
        freeze_path=args.freeze,
        config_paths={
            "multiphase": args.multiphase_config,
            "venous": args.venous_config,
            "venous_high_contrast": args.venous_high_contrast_config,
        },
        output_root=args.out,
        expected_case_count=args.expected_case_count,
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
