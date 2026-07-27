"""CLI de avaliação tardia do desenvolvimento OpenSwissHCC."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from dtwin.benchmark.openswisshcc_configs import parse_extra_configs
from dtwin.benchmark.openswisshcc_evaluation import evaluate_reviewed_development_run


def main() -> int:
    parser = argparse.ArgumentParser(description="Anexa ground truth após a inferência completa.")
    parser.add_argument("--panels", required=True, type=Path)
    parser.add_argument("--review", required=True, type=Path)
    parser.add_argument("--freeze", required=True, type=Path)
    parser.add_argument("--inference", required=True, type=Path)
    parser.add_argument("--protected-labels", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument(
        "--multiphase-config",
        type=Path,
        default=Path("configs/medgemma_local_4b_multiphase_fast_pathology.yaml"),
    )
    parser.add_argument(
        "--fallback-config",
        type=Path,
        default=Path("configs/medgemma_local_4b_venous_fallback_pathology.yaml"),
    )
    parser.add_argument("--expected-case-count", type=int, default=88)
    parser.add_argument("--extra-config", action="append", default=[])
    parser.add_argument("--expected-positive", type=int, default=39)
    parser.add_argument("--expected-negative", type=int, default=49)
    parser.add_argument("--max-case-seconds", type=float, default=180.0)
    args = parser.parse_args()
    additional_configs = parse_extra_configs(args.extra_config)
    result = evaluate_reviewed_development_run(
        panel_root=args.panels,
        review_path=args.review,
        freeze_path=args.freeze,
        inference_root=args.inference,
        protected_labels_path=args.protected_labels,
        output_dir=args.out,
        multiphase_config=args.multiphase_config,
        fallback_config=args.fallback_config,
        additional_configs=additional_configs,
        expected_case_count=args.expected_case_count,
        expected_positive=args.expected_positive,
        expected_negative=args.expected_negative,
        max_case_seconds=args.max_case_seconds,
    )
    print(
        json.dumps(
            {
                "passed": result["passed"],
                "sensitivity": result["metrics"]["primary"]["sensitivity"],
                "specificity": result["metrics"]["primary"]["specificity"],
                "max_seconds": result["timing"]["max_seconds"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
