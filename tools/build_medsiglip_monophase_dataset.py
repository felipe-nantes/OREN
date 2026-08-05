"""Build the label-blind single-phase MedSigLIP candidate dataset."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from dtwin.learning.monophase_candidate_dataset import (
    derive_monophase_candidate_dataset,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("configs/training/medsiglip_monophase_representation_v1.yaml"),
    )
    parser.add_argument(
        "--source-candidates",
        type=Path,
        default=Path("casos/qualification/hybrid_v1/candidate_dataset_stage_a_v1"),
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
        default=Path("casos/qualification/hybrid_v1/medsiglip_monophase_candidates_v1"),
    )
    parser.add_argument("--workspace-root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    result = derive_monophase_candidate_dataset(
        config_path=args.config,
        source_candidate_root=args.source_candidates,
        protocol_path=args.protocol,
        splits_path=args.splits,
        workspace_root=args.workspace_root,
        output_root=args.out,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
