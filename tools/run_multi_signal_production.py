from __future__ import annotations

import argparse
import json
from pathlib import Path

from dtwin.learning.multi_signal_production import (
    evaluate_external_fusion,
    predict_external_fusion,
    train_fusion_production_bundle,
)


def _mapping(values: list[str]) -> dict[str, Path]:
    result: dict[str, Path] = {}
    for value in values:
        if "=" not in value:
            raise SystemExit(f"Mapeamento invalido: {value}")
        name, path = value.split("=", 1)
        result[name] = Path(path)
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("train", "predict", "evaluate"))
    parser.add_argument("--fusion-config", type=Path)
    parser.add_argument("--protocol-config", type=Path, default=Path("configs/training/hybrid_v1_protocol.yaml"))
    parser.add_argument("--protocol", type=Path, default=Path("configs/training/hybrid_v1_protocol.lock.json"))
    parser.add_argument("--splits", type=Path, default=Path("configs/training/hybrid_v1_nested_splits.json"))
    parser.add_argument("--signal-root", action="append", default=[])
    parser.add_argument("--base-bundle", action="append", default=[])
    parser.add_argument("--bundle", type=Path)
    parser.add_argument("--prediction-root", type=Path)
    parser.add_argument("--protected-dataset-id", action="append", default=[])
    parser.add_argument("--workspace-root", type=Path, default=Path.cwd())
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.action == "train":
        result = train_fusion_production_bundle(
            fusion_config_path=args.fusion_config,
            training_protocol_config_path=args.protocol_config,
            training_protocol_path=args.protocol, splits_path=args.splits,
            signal_roots=_mapping(args.signal_root),
            base_bundle_roots=_mapping(args.base_bundle),
            workspace_root=args.workspace_root, output_root=args.out,
        )
    elif args.action == "predict":
        result = predict_external_fusion(
            bundle_root=args.bundle, signal_prediction_roots=_mapping(args.signal_root),
            output_root=args.out,
        )
    else:
        result = evaluate_external_fusion(
            prediction_root=args.prediction_root,
            training_protocol_config_path=args.protocol_config,
            workspace_root=args.workspace_root,
            protected_dataset_ids=set(args.protected_dataset_id), output_root=args.out,
        )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
