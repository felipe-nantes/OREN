"""Freeze, evaluate, or verify OpenSwissHCC phase-4 OOF predictions."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from dtwin.benchmark.v23_retrospective_multicohort_phase4 import (
    evaluate_phase4_predictions,
    freeze_phase4_oof_predictions,
    verify_phase4_evaluation,
    verify_phase4_prediction_freeze,
)
from dtwin.core import PipelineError


ROOT = Path("casos/qualification/openswisshcc_v1")


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser()
    result.add_argument("command", choices=("freeze", "verify-freeze", "evaluate", "verify"))
    result.add_argument("--workspace", type=Path, default=Path("."))
    result.add_argument("--contract", type=Path, default=Path("configs/benchmark/v23_retrospective_multicohort_contract_v1.json"))
    result.add_argument("--baseline-lock", type=Path, default=Path("configs/benchmark/openswisshcc_v23_baseline_lock_v1.json"))
    result.add_argument("--phase2", type=Path, default=ROOT / "prepared/retrospective_multicohort_phase2_v1")
    result.add_argument("--phase3", type=Path, default=ROOT / "prepared/retrospective_multicohort_phase3_v1")
    result.add_argument("--calibrator", type=Path, default=ROOT / "prepared/development_freezes_v23/shape_fusion_calibrator_v1.json")
    result.add_argument("--predictions", type=Path, default=ROOT / "prepared/retrospective_multicohort_phase4_predictions_v1")
    result.add_argument("--evaluation", type=Path, default=ROOT / "evaluation/retrospective_multicohort_phase4_v1")
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    verification = {
        "prediction_root": args.predictions,
        "phase3_root": args.phase3,
        "phase2_root": args.phase2,
        "contract_path": args.contract,
        "baseline_lock_path": args.baseline_lock,
        "workspace_root": args.workspace,
    }
    try:
        if args.command == "freeze":
            value = freeze_phase4_oof_predictions(
                **{key: value for key, value in verification.items() if key != "prediction_root"},
                calibrator_path=args.calibrator,
                output_dir=args.predictions,
            )
        elif args.command == "verify-freeze":
            value, _ = verify_phase4_prediction_freeze(**verification)
        elif args.command == "evaluate":
            value = evaluate_phase4_predictions(
                **verification,
                output_dir=args.evaluation,
            )
        else:
            value = verify_phase4_evaluation(
                evaluation_root=args.evaluation,
                **verification,
            )
    except PipelineError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 2
    print(json.dumps({"ok": True, "result": value}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
