"""Build or verify the OpenSwissHCC phase-2 inventory and split protocol."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from dtwin.benchmark.v23_retrospective_multicohort_phase2 import (
    build_phase2_openswisshcc_inventory,
    verify_phase2_openswisshcc_inventory,
)
from dtwin.core import PipelineError

ROOT = Path("casos/qualification/openswisshcc_v1")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("build", "verify"))
    parser.add_argument("--workspace", type=Path, default=Path("."))
    parser.add_argument(
        "--contract",
        type=Path,
        default=Path(
            "configs/benchmark/v23_retrospective_multicohort_contract_v1.json"
        ),
    )
    parser.add_argument(
        "--baseline-lock",
        type=Path,
        default=Path("configs/benchmark/openswisshcc_v23_baseline_lock_v1.json"),
    )
    parser.add_argument(
        "--development-manifest",
        type=Path,
        default=ROOT / "prepared/development_v1/manifests/development_inputs.jsonl",
    )
    parser.add_argument(
        "--development-labels",
        type=Path,
        default=ROOT
        / "prepared/development_v1/protected_ground_truth/development_labels.jsonl",
    )
    parser.add_argument(
        "--holdout-manifest",
        type=Path,
        default=ROOT / "prepared/holdout_blind_v1/manifests/holdout_inputs.jsonl",
    )
    parser.add_argument(
        "--holdout-labels",
        type=Path,
        default=ROOT / "prepared/holdout_v21_protected_labels/holdout_labels.jsonl",
    )
    parser.add_argument(
        "--development-v11-signals",
        type=Path,
        default=ROOT / "runs/dev_v20_blind_fusion87/signals.jsonl",
    )
    parser.add_argument(
        "--holdout-v11-signals",
        type=Path,
        default=ROOT / "prepared/holdout_v21_raw_signals/raw_signals.jsonl",
    )
    parser.add_argument(
        "--development-shape-features",
        type=Path,
        default=ROOT
        / "prepared/development_v23_candidate_shape_full87_v1/features.jsonl",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "prepared/retrospective_multicohort_phase2_v1",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "build":
            result = build_phase2_openswisshcc_inventory(
                contract_path=args.contract,
                baseline_lock_path=args.baseline_lock,
                workspace_root=args.workspace,
                development_manifest_path=args.development_manifest,
                development_labels_path=args.development_labels,
                holdout_manifest_path=args.holdout_manifest,
                holdout_labels_path=args.holdout_labels,
                development_v11_signals_path=args.development_v11_signals,
                holdout_v11_signals_path=args.holdout_v11_signals,
                development_shape_features_path=args.development_shape_features,
                output_dir=args.output,
            )
        else:
            result = verify_phase2_openswisshcc_inventory(
                phase2_root=args.output,
                contract_path=args.contract,
                baseline_lock_path=args.baseline_lock,
                workspace_root=args.workspace,
            )
    except PipelineError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 2
    print(json.dumps({"ok": True, "result": result}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
