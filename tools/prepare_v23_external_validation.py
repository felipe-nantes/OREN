#!/usr/bin/env python3
"""Freeze the v23 external contract or preflight a fresh balanced cohort."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from dtwin.benchmark.v23_external_validation import (
    freeze_v23_external_validation_contract,
    preflight_v23_external_validation,
)
from dtwin.core import PipelineError


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--baseline-lock",
        type=Path,
        default=Path("configs/benchmark/openswisshcc_v23_baseline_lock_v1.json"),
    )
    common.add_argument("--workspace", type=Path, default=Path("."))
    freeze = subparsers.add_parser("freeze-contract", parents=[common])
    freeze.add_argument("--out", type=Path, required=True)
    preflight = subparsers.add_parser("preflight", parents=[common])
    preflight.add_argument("--contract", type=Path, required=True)
    preflight.add_argument("--images", type=Path, required=True)
    preflight.add_argument("--protected-labels", type=Path, required=True)
    preflight.add_argument("--forbidden-fingerprints", type=Path)
    preflight.add_argument("--out", type=Path, required=True)
    preflight.add_argument(
        "--allow-protected-label-inventory",
        action="store_true",
    )
    args = parser.parse_args()
    try:
        if args.command == "freeze-contract":
            result = freeze_v23_external_validation_contract(
                baseline_lock_path=args.baseline_lock,
                workspace_root=args.workspace,
                output_path=args.out,
            )
        else:
            result = preflight_v23_external_validation(
                contract_path=args.contract,
                baseline_lock_path=args.baseline_lock,
                image_manifest_path=args.images,
                protected_labels_path=args.protected_labels,
                workspace_root=args.workspace,
                output_dir=args.out,
                forbidden_fingerprints_path=args.forbidden_fingerprints,
                allow_protected_label_inventory=(
                    args.allow_protected_label_inventory
                ),
            )
    except PipelineError as exc:
        print(f"[ABORTADO] {exc}")
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
