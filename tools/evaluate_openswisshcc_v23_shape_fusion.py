#!/usr/bin/env python3
"""Evaluate the retrospective v23 shape fusion on development only."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from dtwin.benchmark.openswisshcc_v23_shape_fusion import evaluate_shape_fusion_development
from dtwin.core import PipelineError


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--v20-bundle", type=Path, required=True)
    parser.add_argument("--v20-protocol", type=Path, required=True)
    parser.add_argument("--shape-root", type=Path, required=True)
    parser.add_argument("--labels", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--allow-protected-development-labels", action="store_true")
    args = parser.parse_args()
    try:
        result = evaluate_shape_fusion_development(
            v20_bundle_root=args.v20_bundle,
            v20_protocol_path=args.v20_protocol,
            shape_root=args.shape_root,
            labels_path=args.labels,
            output_dir=args.out,
            allow_protected_development_labels=args.allow_protected_development_labels,
        )
    except PipelineError as exc:
        print(f"[ABORTADO] {exc}")
        return 1
    print(json.dumps(result, ensure_ascii=True, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
