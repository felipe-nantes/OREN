"""Freeze and evaluate Phase-9 late fusion."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from dtwin.learning.late_fusion import build_frozen_fusion, evaluate_fusion


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("freeze", "evaluate"))
    parser.add_argument("--config", type=Path, default=Path("configs/training/late_fusion_v1.yaml"))
    parser.add_argument("--v23", type=Path, default=Path("casos/qualification/openswisshcc_v1/prepared/retrospective_multicohort_phase4_predictions_v1"))
    parser.add_argument("--medsiglip", type=Path, default=Path("casos/qualification/hybrid_v1/medsiglip_oof_predictions_v1"))
    parser.add_argument("--fusion", type=Path, default=Path("casos/qualification/hybrid_v1/late_fusion_oof_predictions_v1"))
    parser.add_argument("--evaluation", type=Path, default=Path("casos/qualification/hybrid_v1/late_fusion_oof_evaluation_v1"))
    parser.add_argument("--development-labels", type=Path, default=Path("casos/qualification/openswisshcc_v1/prepared/development_v1/protected_ground_truth/development_labels.jsonl"))
    parser.add_argument("--holdout-labels", type=Path, default=Path("casos/qualification/openswisshcc_v1/prepared/holdout_v21_protected_labels/holdout_labels.jsonl"))
    parser.add_argument("--radiomics-evaluation", type=Path, default=Path("casos/qualification/hybrid_v1/radiomics_oof_evaluation_v1/evaluation.json"))
    parser.add_argument("--patch-evaluation", type=Path, default=Path("casos/qualification/hybrid_v1/patch25d_oof_evaluation_v1/evaluation.json"))
    args = parser.parse_args()
    if args.command == "freeze":
        result = build_frozen_fusion(
            config_path=args.config, v23_root=args.v23,
            medsiglip_root=args.medsiglip, output_root=args.fusion,
        )
    else:
        result = evaluate_fusion(
            fusion_root=args.fusion, v23_root=args.v23, medsiglip_root=args.medsiglip,
            development_labels_path=args.development_labels,
            holdout_labels_path=args.holdout_labels,
            radiomics_evaluation_path=args.radiomics_evaluation,
            patch_evaluation_path=args.patch_evaluation,
            output_root=args.evaluation,
        )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
