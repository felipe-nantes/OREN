"""Build or verify the label-blind hybrid-v1 visual dataset."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from dtwin.learning.candidate_dataset import (
    build_candidate_dataset,
    verify_candidate_dataset,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("build", "verify"))
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("configs/training/hybrid_v1_candidate_dataset.yaml"),
    )
    parser.add_argument(
        "--protocol",
        type=Path,
        default=Path("configs/training/hybrid_v1_protocol.lock.json"),
    )
    parser.add_argument(
        "--splits",
        type=Path,
        default=Path("configs/training/hybrid_v1_nested_splits.json"),
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path(
            "casos/qualification/hybrid_v1/candidate_dataset_stage_a_v1"
        ),
    )
    parser.add_argument("--workspace-root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    common = {
        "protocol_path": args.protocol,
        "splits_path": args.splits,
        "workspace_root": args.workspace_root,
        "output_root": args.out,
    }
    result = (
        build_candidate_dataset(config_path=args.config, **common)
        if args.command == "build"
        else verify_candidate_dataset(**common)
    )
    print(
        json.dumps(
            {
                "status": "ok",
                "dataset_signature": result["dataset_signature"],
                "materialized_case_count": result[
                    "materialized_case_count"
                ],
                "technical_failure_count": result[
                    "technical_failure_count"
                ],
                "candidate_record_count": result["candidate_record_count"],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
