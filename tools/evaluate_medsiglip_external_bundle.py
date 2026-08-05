"""Predict and evaluate the frozen delayed-monophase MedSigLIP bundle."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from dtwin.learning.external_bundle_evaluation import (
    evaluate_external_bundle,
    predict_external_bundle,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("predict", "evaluate"))
    parser.add_argument("--bundle", type=Path, default=Path(
        "casos/qualification/hybrid_v1/medsiglip_monophase_delayed_production_bundle_v2"
    ))
    parser.add_argument("--candidates", type=Path, default=Path(
        "casos/qualification/hybrid_v1/medsiglip_monophase_delayed_candidates_v1"
    ))
    parser.add_argument("--embeddings", type=Path, default=Path(
        "casos/qualification/hybrid_v1/medsiglip_monophase_delayed_embeddings_v1"
    ))
    parser.add_argument("--protocol-config", type=Path, default=Path(
        "configs/training/hybrid_v1_protocol.yaml"
    ))
    parser.add_argument("--protocol", type=Path, default=Path(
        "configs/training/hybrid_v1_protocol.lock.json"
    ))
    parser.add_argument("--splits", type=Path, default=Path(
        "configs/training/hybrid_v1_nested_splits.json"
    ))
    parser.add_argument("--predictions", type=Path, default=Path(
        "casos/qualification/hybrid_v1/medsiglip_monophase_delayed_openswiss_predictions_v1"
    ))
    parser.add_argument("--evaluation", type=Path, default=Path(
        "casos/qualification/hybrid_v1/medsiglip_monophase_delayed_openswiss_evaluation_v1"
    ))
    parser.add_argument("--workspace-root", type=Path, default=Path.cwd())
    parser.add_argument("--case-manifest", type=Path)
    parser.add_argument("--dataset-id", default="openswisshcc")
    parser.add_argument("--failure-case-prefix", default="anon-openswiss-")
    parser.add_argument("--expected-case-count", type=int, default=132)
    parser.add_argument(
        "--protected-dataset-id", action="append",
        dest="protected_dataset_ids",
    )
    args = parser.parse_args()
    if args.action == "predict":
        result = predict_external_bundle(
            bundle_root=args.bundle, candidate_root=args.candidates,
            embedding_root=args.embeddings, protocol_path=args.protocol,
            splits_path=args.splits, workspace_root=args.workspace_root,
            dataset_id=args.dataset_id, failure_case_prefix=args.failure_case_prefix,
            expected_case_count=args.expected_case_count, output_root=args.predictions,
            case_manifest_path=args.case_manifest,
        )
    else:
        result = evaluate_external_bundle(
            bundle_root=args.bundle, prediction_root=args.predictions,
            training_protocol_config_path=args.protocol_config,
            workspace_root=args.workspace_root,
            protected_dataset_ids=set(args.protected_dataset_ids or (
                "openswisshcc_development", "openswisshcc_consumed_holdout"
            )),
            output_root=args.evaluation,
        )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
