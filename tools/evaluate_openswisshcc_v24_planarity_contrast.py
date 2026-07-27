#!/usr/bin/env python3
"""Freeze or evaluate the nested v24 planarity-contrast hypothesis."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from dtwin.benchmark.openswisshcc_v24_planarity_contrast import (
    evaluate_v24_planarity_contrast,
    freeze_v24_planarity_protocol,
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
    common.add_argument(
        "--audit-summary",
        type=Path,
        default=Path(
            "casos/qualification/openswisshcc_v1/audits/"
            "dev_v23_error_audit_v3/summary.json"
        ),
    )
    common.add_argument("--workspace", type=Path, default=Path("."))
    freeze = subparsers.add_parser("freeze", parents=[common])
    freeze.add_argument("--out", type=Path, required=True)
    evaluate = subparsers.add_parser("evaluate", parents=[common])
    evaluate.add_argument("--protocol", type=Path, required=True)
    evaluate.add_argument("--out", type=Path, required=True)
    evaluate.add_argument(
        "--allow-protected-development-labels",
        action="store_true",
    )
    args = parser.parse_args()
    try:
        if args.command == "freeze":
            result = freeze_v24_planarity_protocol(
                baseline_lock_path=args.baseline_lock,
                audit_summary_path=args.audit_summary,
                workspace_root=args.workspace,
                output_path=args.out,
            )
        else:
            result = evaluate_v24_planarity_contrast(
                protocol_path=args.protocol,
                baseline_lock_path=args.baseline_lock,
                audit_summary_path=args.audit_summary,
                workspace_root=args.workspace,
                output_dir=args.out,
                allow_protected_development_labels=(
                    args.allow_protected_development_labels
                ),
            )
    except PipelineError as exc:
        print(f"[ABORTADO] {exc}")
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
