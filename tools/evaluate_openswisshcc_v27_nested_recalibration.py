#!/usr/bin/env python3
"""Freeze and evaluate nested recalibration of frozen v23-v26 signals."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from dtwin.benchmark.openswisshcc_v27_nested_recalibration import (
    evaluate_predictions,
    freeze_predictions,
    freeze_protocol,
    verify_protocol,
)
from dtwin.core import PipelineError


ROOT = Path("casos/qualification/openswisshcc_v1")
PREPARED = ROOT / "prepared"


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument(
        "command", choices=("freeze-protocol", "verify-protocol", "freeze", "evaluate")
    )
    result.add_argument("--workspace", type=Path, default=Path("."))
    result.add_argument(
        "--phase2", type=Path, default=PREPARED / "retrospective_multicohort_phase2_v1"
    )
    result.add_argument(
        "--phase3", type=Path, default=PREPARED / "retrospective_multicohort_phase3_v1"
    )
    result.add_argument(
        "--v24", type=Path, default=PREPARED / "v24_liver_enriched_inference130_v1"
    )
    result.add_argument(
        "--v25", type=Path, default=PREPARED / "v25_pathology_target_inference130_v1"
    )
    result.add_argument(
        "--v26",
        type=Path,
        default=PREPARED / "v26_pathology_target_rag_inference130_v1",
    )
    result.add_argument(
        "--protocol",
        type=Path,
        default=Path(
            "configs/benchmark/openswisshcc_v27_nested_recalibration_protocol_v1.json"
        ),
    )
    result.add_argument(
        "--predictions",
        type=Path,
        default=PREPARED / "v27_nested_recalibration_predictions_v1",
    )
    result.add_argument(
        "--v23-evaluation",
        type=Path,
        default=ROOT / "evaluation/retrospective_multicohort_phase4_v1/evaluation.json",
    )
    result.add_argument(
        "--evaluation",
        type=Path,
        default=ROOT / "evaluation/v27_nested_recalibration_v1",
    )
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    common = {
        "protocol_path": args.protocol,
        "phase3_root": args.phase3,
        "v24_root": args.v24,
        "v25_root": args.v25,
        "v26_root": args.v26,
        "workspace_root": args.workspace,
    }
    try:
        if args.command == "freeze-protocol":
            value = freeze_protocol(
                phase3_root=args.phase3,
                v24_root=args.v24,
                v25_root=args.v25,
                v26_root=args.v26,
                workspace_root=args.workspace,
                output_path=args.protocol,
            )
        elif args.command == "verify-protocol":
            value = verify_protocol(**common)
        elif args.command == "freeze":
            value = freeze_predictions(
                **common,
                phase2_root=args.phase2,
                output_root=args.predictions,
            )
        else:
            value = evaluate_predictions(
                **common,
                prediction_root=args.predictions,
                phase2_root=args.phase2,
                v23_evaluation_path=args.v23_evaluation,
                output_root=args.evaluation,
            )
    except (PipelineError, OSError, RuntimeError, KeyError, ValueError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 2
    print(json.dumps({"ok": True, "result": value}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
