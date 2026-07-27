"""Nested OOF training and evaluation for the 2.5D patch classifier."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from dtwin.learning.patch25d_classifier import evaluate_oof, generate_oof


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("predict-oof", "evaluate"))
    parser.add_argument("--config", type=Path, default=Path("configs/training/patch25d_classifier_v1.yaml"))
    parser.add_argument("--splits", type=Path, default=Path("configs/training/hybrid_v1_nested_splits.json"))
    parser.add_argument("--candidates", type=Path, default=Path("casos/qualification/hybrid_v1/patch25d_candidate_dataset_v1"))
    parser.add_argument("--embeddings", type=Path, default=Path("casos/qualification/hybrid_v1/patch25d_medsiglip_embeddings_v1"))
    parser.add_argument("--targets", type=Path, default=Path("casos/qualification/hybrid_v1/patch25d_protected_targets_v1"))
    parser.add_argument("--predictions", type=Path, default=Path("casos/qualification/hybrid_v1/patch25d_oof_predictions_v1"))
    parser.add_argument("--evaluation", type=Path, default=Path("casos/qualification/hybrid_v1/patch25d_oof_evaluation_v1"))
    args = parser.parse_args()
    if args.command == "predict-oof":
        result = generate_oof(
            config_path=args.config, splits_path=args.splits, candidate_root=args.candidates,
            embedding_root=args.embeddings, target_root=args.targets, output_root=args.predictions,
        )
    else:
        result = evaluate_oof(
            prediction_root=args.predictions,
            embedding_root=args.embeddings,
            target_root=args.targets,
            output_root=args.evaluation,
        )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
