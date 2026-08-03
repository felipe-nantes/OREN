#!/usr/bin/env python3
"""Run the frozen visual classifier on synthetic external stress v1."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from dtwin.benchmark.synthetic_external_stress_v1_eval import evaluate_synthetic_stress
from dtwin.core import PipelineError
from dtwin.learning.exam_to_panels import DEFAULT_LIVER_ENRICHED_PANEL_CONFIG
from dtwin.learning.visual_inference import DEFAULT_EMBEDDING_CONFIG


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cohort", type=Path, required=True)
    parser.add_argument(
        "--bundle",
        type=Path,
        default=Path("casos/qualification/hybrid_v1/medsiglip_multiclass_production_bundle_v1"),
    )
    parser.add_argument("--panel-config", type=Path, default=Path(DEFAULT_LIVER_ENRICHED_PANEL_CONFIG))
    parser.add_argument("--embedding-config", type=Path, default=Path(DEFAULT_EMBEDDING_CONFIG))
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()
    try:
        report = evaluate_synthetic_stress(
            cohort_root=args.cohort,
            bundle_root=args.bundle,
            panel_config_path=args.panel_config,
            embedding_config_path=args.embedding_config,
            output_root=args.out,
            limit=args.limit,
        )
    except (PipelineError, OSError, RuntimeError, ValueError) as exc:
        print(f"[ABORTED] {exc}")
        return 1
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

