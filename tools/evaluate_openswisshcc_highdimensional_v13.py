#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from dtwin.benchmark.openswisshcc_highdimensional_evaluation import (
    evaluate_highdimensional_development,
)
from dtwin.core import PipelineError


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Avalia as 87 predições 3D v13 após autorização explícita."
    )
    parser.add_argument("--bundle-root", required=True, type=Path)
    parser.add_argument("--protocol", required=True, type=Path)
    parser.add_argument("--inference-root", required=True, type=Path)
    parser.add_argument("--protected-labels", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--expected-excluded-case-id", required=True)
    parser.add_argument("--allow-protected-development-labels", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = evaluate_highdimensional_development(
            bundle_root=args.bundle_root,
            protocol_path=args.protocol,
            inference_root=args.inference_root,
            protected_labels_path=args.protected_labels,
            output_dir=args.output_dir,
            allow_protected_development_labels=(
                args.allow_protected_development_labels
            ),
            expected_excluded_case_id=args.expected_excluded_case_id,
        )
    except PipelineError as exc:
        print(f"[ABORTADO] {exc}", flush=True)
        return 1
    print(json.dumps({
        "passed": result["passed"],
        "sensitivity": result["metrics"]["primary"]["sensitivity"],
        "specificity": result["metrics"]["primary"]["specificity"],
        "max_seconds": result["timing"]["max_seconds"],
        "holdout_opened": result["holdout_opened"],
        "output_dir": result["output_dir"],
    }, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

