"""Build or verify the exact OpenSwissHCC v23 signal matrix (phase 3)."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from dtwin.benchmark.v23_retrospective_multicohort_phase3 import (
    build_phase3_exact_v23_signals,
    verify_phase3_exact_v23_signals,
)
from dtwin.core import PipelineError

ROOT = Path("casos/qualification/openswisshcc_v1")


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser()
    result.add_argument("command", choices=("build", "verify"))
    result.add_argument("--workspace", type=Path, default=Path("."))
    result.add_argument(
        "--contract",
        type=Path,
        default=Path("configs/benchmark/v23_retrospective_multicohort_contract_v1.json"),
    )
    result.add_argument(
        "--baseline-lock",
        type=Path,
        default=Path("configs/benchmark/openswisshcc_v23_baseline_lock_v1.json"),
    )
    result.add_argument(
        "--phase2",
        type=Path,
        default=ROOT / "prepared/retrospective_multicohort_phase2_v1",
    )
    result.add_argument(
        "--development-v11",
        type=Path,
        default=ROOT / "runs/dev_v20_blind_fusion87/signals.jsonl",
    )
    result.add_argument(
        "--holdout-v11",
        type=Path,
        default=ROOT / "prepared/holdout_v21_raw_signals/raw_signals.jsonl",
    )
    result.add_argument(
        "--development-shapes",
        type=Path,
        default=ROOT / "prepared/development_v23_candidate_shape_full87_v1/features.jsonl",
    )
    result.add_argument(
        "--holdout-manifest",
        type=Path,
        default=ROOT / "prepared/holdout_blind_v1/manifests/holdout_inputs.jsonl",
    )
    result.add_argument(
        "--holdout-alignments",
        type=Path,
        default=ROOT / "prepared/holdout_alignment_v1",
    )
    result.add_argument(
        "--holdout-alignment-summary",
        type=Path,
        default=ROOT / "prepared/holdout_alignment_v1_summary.json",
    )
    result.add_argument(
        "--development-quality-review",
        type=Path,
        default=ROOT / "prepared/development_reviews_v9/multisequence_quality_review.json",
    )
    result.add_argument(
        "--output",
        type=Path,
        default=ROOT / "prepared/retrospective_multicohort_phase3_v1",
    )
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    common = {
        "phase3_root": args.output,
        "phase2_root": args.phase2,
        "contract_path": args.contract,
        "baseline_lock_path": args.baseline_lock,
        "workspace_root": args.workspace,
    }
    try:
        if args.command == "build":
            result = build_phase3_exact_v23_signals(
                phase2_root=args.phase2,
                contract_path=args.contract,
                baseline_lock_path=args.baseline_lock,
                workspace_root=args.workspace,
                development_v11_signals_path=args.development_v11,
                holdout_v11_signals_path=args.holdout_v11,
                development_shape_features_path=args.development_shapes,
                holdout_manifest_path=args.holdout_manifest,
                holdout_alignment_root=args.holdout_alignments,
                holdout_alignment_summary_path=args.holdout_alignment_summary,
                development_quality_review_path=args.development_quality_review,
                output_dir=args.output,
            )
        else:
            result = verify_phase3_exact_v23_signals(**common)
    except PipelineError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 2
    print(json.dumps({"ok": True, "result": result}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
