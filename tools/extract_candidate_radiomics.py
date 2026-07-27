"""Build or verify label-blind hybrid-v1 multiphase radiomics."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from dtwin.learning.radiomics_features import (
    build_radiomics_features,
    verify_radiomics_features,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("extract", "verify"))
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("configs/training/radiomics_v1.yaml"),
    )
    parser.add_argument(
        "--candidates",
        type=Path,
        default=Path(
            "casos/qualification/hybrid_v1/candidate_dataset_stage_a_v1"
        ),
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("casos/qualification/hybrid_v1/radiomics_features_v1"),
    )
    parser.add_argument("--workspace-root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    if args.command == "extract":
        result = build_radiomics_features(
            config_path=args.config,
            candidate_root=args.candidates,
            workspace_root=args.workspace_root,
            output_root=args.out,
        )
    else:
        result = verify_radiomics_features(
            candidate_root=args.candidates,
            workspace_root=args.workspace_root,
            output_root=args.out,
        )
    print(
        json.dumps(
            {
                "status": "ok",
                "radiomics_signature": result["radiomics_signature"],
                "feature_case_count": result["feature_case_count"],
                "feature_count": result["feature_count"],
                "technical_failure_count": result["technical_failure_count"],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
