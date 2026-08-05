"""Generate and evaluate nested OOF pairwise subtype predictions."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from dtwin.learning.medsiglip_pairwise_subtype import (
    evaluate_pairwise_oof_predictions,
    generate_pairwise_oof_predictions,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("predict-oof", "evaluate"))
    parser.add_argument("--pairwise-config", type=Path, required=True)
    parser.add_argument("--training-config", type=Path, default=Path("configs/training/hybrid_v1_protocol.yaml"))
    parser.add_argument("--protocol", type=Path, default=Path("configs/training/hybrid_v1_protocol.lock.json"))
    parser.add_argument("--splits", type=Path, default=Path("configs/training/hybrid_v1_nested_splits.json"))
    parser.add_argument("--embeddings", type=Path, required=True)
    parser.add_argument("--candidates", type=Path, required=True)
    parser.add_argument("--predictions", type=Path, required=True)
    parser.add_argument("--evaluation", type=Path, required=True)
    parser.add_argument("--workspace-root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    if args.command == "predict-oof":
        result = generate_pairwise_oof_predictions(
            pairwise_config_path=args.pairwise_config,
            training_protocol_config_path=args.training_config,
            training_protocol_path=args.protocol,
            splits_path=args.splits,
            embedding_root=args.embeddings,
            candidate_root=args.candidates,
            workspace_root=args.workspace_root,
            output_root=args.predictions,
        )
    else:
        result = evaluate_pairwise_oof_predictions(
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
