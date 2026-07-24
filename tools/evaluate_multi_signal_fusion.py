"""Generate and evaluate nested OOF multi-signal meta-fusion predictions."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from dtwin.learning.multi_signal_fusion import (
    evaluate_oof_predictions,
    generate_oof_predictions,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("predict-oof", "evaluate"))
    parser.add_argument(
        "--fusion-config",
        type=Path,
        default=Path("configs/training/multi_signal_fusion_v1.yaml"),
    )
    parser.add_argument(
        "--training-config",
        type=Path,
        default=Path("configs/training/hybrid_v1_protocol.yaml"),
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
        "--v23",
        type=Path,
        default=Path(
            "casos/qualification/openswisshcc_v1/prepared/retrospective_multicohort_phase4_predictions_v1"
        ),
    )
    parser.add_argument(
        "--medsiglip-phase5",
        type=Path,
        default=Path("casos/qualification/hybrid_v1/medsiglip_oof_predictions_v1"),
    )
    parser.add_argument(
        "--medsiglip-lora-stage3",
        type=Path,
        default=Path("casos/qualification/hybrid_v1/medsiglip_lora_oof_predictions_v1"),
    )
    parser.add_argument(
        "--predictions",
        type=Path,
        default=Path("casos/qualification/hybrid_v1/multi_signal_fusion_oof_predictions_v1"),
    )
    parser.add_argument(
        "--evaluation",
        type=Path,
        default=Path("casos/qualification/hybrid_v1/multi_signal_fusion_oof_evaluation_v1"),
    )
    parser.add_argument("--workspace-root", type=Path, default=Path.cwd())
    args = parser.parse_args()

    signal_roots = {
        "v23": args.v23,
        "medsiglip_phase5": args.medsiglip_phase5,
        "medsiglip_lora_stage3": args.medsiglip_lora_stage3,
    }

    if args.command == "predict-oof":
        result = generate_oof_predictions(
            fusion_config_path=args.fusion_config,
            training_protocol_config_path=args.training_config,
            training_protocol_path=args.protocol,
            splits_path=args.splits,
            signal_roots=signal_roots,
            workspace_root=args.workspace_root,
            output_root=args.predictions,
        )
    else:
        result = evaluate_oof_predictions(
            training_protocol_config_path=args.training_config,
            training_protocol_path=args.protocol,
            splits_path=args.splits,
            prediction_root=args.predictions,
            workspace_root=args.workspace_root,
            output_root=args.evaluation,
        )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
