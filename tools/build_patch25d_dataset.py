"""Build label-blind 2.5D patches or protected candidate targets."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from dtwin.learning.patch25d_dataset import (
    build_label_blind_dataset,
    build_protected_targets,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("images", "targets"))
    parser.add_argument("--config", type=Path, default=Path("configs/training/patch25d_v1.yaml"))
    parser.add_argument("--workspace-root", type=Path, default=Path.cwd())
    parser.add_argument(
        "--candidates",
        type=Path,
        default=Path("casos/qualification/hybrid_v1/patch25d_candidate_dataset_v1"),
    )
    parser.add_argument(
        "--proposal-root",
        type=Path,
        default=Path("casos/qualification/openswisshcc_v1/calibration/dev_v22_enhancement_localizer_full87_v1"),
    )
    parser.add_argument(
        "--labels",
        type=Path,
        default=Path("casos/qualification/openswisshcc_v1/prepared/development_v1/protected_ground_truth/development_labels.jsonl"),
    )
    parser.add_argument(
        "--lesion-extraction",
        type=Path,
        default=Path("casos/qualification/openswisshcc_v1/authorized_ground_truth_v16/venous_masks_v1"),
    )
    parser.add_argument(
        "--targets",
        type=Path,
        default=Path("casos/qualification/hybrid_v1/patch25d_protected_targets_v1"),
    )
    args = parser.parse_args()
    if args.command == "images":
        result = build_label_blind_dataset(
            config_path=args.config,
            workspace_root=args.workspace_root,
            output_root=args.candidates,
        )
    else:
        result = build_protected_targets(
            candidate_root=args.candidates,
            proposal_root=args.proposal_root,
            labels_path=args.labels,
            lesion_extraction_root=args.lesion_extraction,
            output_root=args.targets,
        )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
