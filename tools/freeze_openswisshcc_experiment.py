"""CLI para congelar o experimento OpenSwissHCC antes da revisão/inferência."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from dtwin.benchmark.openswisshcc_configs import parse_extra_configs
from dtwin.benchmark.openswisshcc_freeze import (
    create_experiment_freeze,
    verify_experiment_freeze,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Congela painéis e configs resolvidas.")
    parser.add_argument("--panels", required=True, type=Path)
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
    parser.add_argument(
        "--experiment-version",
        default="openswisshcc-development-medgemma-4b-v1",
    )
    args = parser.parse_args()
    additional_configs = parse_extra_configs(args.extra_config)
    result = create_experiment_freeze(
        panel_root=args.panels,
        multiphase_config=args.multiphase_config,
        fallback_config=args.fallback_config,
        output_path=args.out,
        expected_case_count=args.expected_case_count,
        experiment_version=args.experiment_version,
        additional_configs=additional_configs,
    )
    verify_experiment_freeze(
        freeze_path=args.out,
        panel_root=args.panels,
        multiphase_config=args.multiphase_config,
        fallback_config=args.fallback_config,
        expected_case_count=args.expected_case_count,
        additional_configs=additional_configs,
    )
    print(
        json.dumps(
            {
                "case_count": result["case_count"],
                "experiment_signature": result["experiment_signature"],
                "ground_truth_read": result["ground_truth_read"],
                "verified": True,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
