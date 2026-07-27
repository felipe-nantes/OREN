"""Score all frozen OpenSwissHCC volumetric panels with local MedSigLIP."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from dtwin.benchmark.openswisshcc_volumetric_medsiglip import (
    run_volumetric_medsiglip_scores,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--panels", required=True, type=Path)
    parser.add_argument("--review", required=True, type=Path)
    parser.add_argument("--freeze", required=True, type=Path)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--model", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--multiphase-config", required=True, type=Path)
    parser.add_argument("--venous-config", required=True, type=Path)
    parser.add_argument("--venous-high-contrast-config", required=True, type=Path)
    parser.add_argument("--expected-case-count", type=int, default=88)
    parser.add_argument("--device", choices=("cpu", "cuda"), default="cuda")
    args = parser.parse_args()

    def progress(value: dict) -> None:
        print(json.dumps(value, ensure_ascii=False, sort_keys=True), flush=True)

    result = run_volumetric_medsiglip_scores(
        panel_root=args.panels, review_path=args.review, freeze_path=args.freeze,
        medgemma_config_paths={
            "multiphase": args.multiphase_config,
            "venous": args.venous_config,
            "venous_high_contrast": args.venous_high_contrast_config,
        },
        medsiglip_config_path=args.config, local_model_path=args.model,
        output_root=args.out, expected_case_count=args.expected_case_count,
        device=args.device, progress=progress,
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True), flush=True)
    return 0 if result["status"] == "complete" else 2


if __name__ == "__main__":
    raise SystemExit(main())
