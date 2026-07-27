"""Freeze or verify phase 1 of the retrospective multicohort v23 protocol."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from dtwin.benchmark.v23_retrospective_multicohort import (
    build_phase1_readiness,
    freeze_retrospective_multicohort_contract,
    verify_retrospective_multicohort_contract,
)
from dtwin.core import PipelineError


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("freeze", "verify", "readiness"))
    parser.add_argument(
        "--baseline-lock",
        type=Path,
        default=Path("configs/benchmark/openswisshcc_v23_baseline_lock_v1.json"),
    )
    parser.add_argument(
        "--contract",
        type=Path,
        default=Path(
            "configs/benchmark/v23_retrospective_multicohort_contract_v1.json"
        ),
    )
    parser.add_argument("--workspace", type=Path, default=Path("."))
    parser.add_argument(
        "--readiness-output",
        type=Path,
        default=Path(
            "casos/qualification/v23_retrospective_multicohort_v1/"
            "phase1_readiness.json"
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "freeze":
            result = freeze_retrospective_multicohort_contract(
                baseline_lock_path=args.baseline_lock,
                workspace_root=args.workspace,
                output_path=args.contract,
            )
        elif args.command == "verify":
            result = verify_retrospective_multicohort_contract(
                contract_path=args.contract,
                baseline_lock_path=args.baseline_lock,
                workspace_root=args.workspace,
            )
        else:
            result = build_phase1_readiness(
                contract_path=args.contract,
                baseline_lock_path=args.baseline_lock,
                workspace_root=args.workspace,
                output_path=args.readiness_output,
            )
    except PipelineError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 2
    print(json.dumps({"ok": True, "result": result}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
