"""Run/resume frozen OpenSwissHCC volumetric inference with MedGemma 1.5 4B."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from dtwin.benchmark.openswisshcc_volumetric_inference import (
    run_frozen_volumetric_inference,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--panels", required=True, type=Path)
    parser.add_argument("--review", required=True, type=Path)
    parser.add_argument("--freeze", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--multiphase-config", required=True, type=Path)
    parser.add_argument("--venous-config", required=True, type=Path)
    parser.add_argument("--venous-high-contrast-config", required=True, type=Path)
    parser.add_argument("--expected-case-count", type=int, default=88)
    args = parser.parse_args()

    def progress(value: dict) -> None:
        print(json.dumps(value, ensure_ascii=False, sort_keys=True), flush=True)

    summary = run_frozen_volumetric_inference(
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
        progress=progress,
    )
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True), flush=True)
    return 0 if summary["status"] == "complete" else 2


if __name__ == "__main__":
    raise SystemExit(main())
