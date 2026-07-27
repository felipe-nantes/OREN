"""Analyze development-only MedGemma and MedSigLIP volumetric score fusion."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from dtwin.benchmark.openswisshcc_volumetric_fusion import analyze_volumetric_fusion


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--medgemma-signals", required=True, type=Path)
    parser.add_argument("--medsiglip", required=True, type=Path)
    parser.add_argument("--labels", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    result = analyze_volumetric_fusion(
        medgemma_signals_path=args.medgemma_signals,
        medsiglip_root=args.medsiglip,
        labels_path=args.labels,
        output_dir=args.out,
    )
    best = result["analyses"][0]
    print(json.dumps({
        "qualified": result["qualified"],
        "best_feature": best["feature"],
        "best_apparent": best["apparent"],
        "best_loocv": best["loocv"],
        "nested_cv": result["nested_repeated_stratified_5fold"],
        "output": str(args.out.resolve()),
    }, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
