"""Freeze and render the OpenSwissHCC v24 liver-enriched pilot."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from dtwin.benchmark.v24_liver_enriched_openswisshcc import (
    approve_v24_liver_enriched_gallery,
    build_v24_liver_enriched_full_cohort,
    build_v24_liver_enriched_gallery,
    build_v24_liver_enriched_pilot,
    freeze_v24_liver_enriched_protocol,
    verify_v24_liver_enriched_full_cohort,
    verify_v24_liver_enriched_protocol,
)
from dtwin.core import PipelineError

ROOT = Path("casos/qualification/openswisshcc_v1")


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser()
    result.add_argument(
        "command",
        choices=(
            "freeze",
            "verify",
            "pilot",
            "gallery",
            "approve",
            "full",
            "verify-full",
        ),
    )
    result.add_argument("--workspace", type=Path, default=Path("."))
    result.add_argument("--contract", type=Path, default=Path("configs/benchmark/v23_retrospective_multicohort_contract_v1.json"))
    result.add_argument("--baseline-lock", type=Path, default=Path("configs/benchmark/openswisshcc_v23_baseline_lock_v1.json"))
    result.add_argument("--phase2", type=Path, default=ROOT / "prepared/retrospective_multicohort_phase2_v1")
    result.add_argument("--phase3", type=Path, default=ROOT / "prepared/retrospective_multicohort_phase3_v1")
    result.add_argument("--phase4-predictions", type=Path, default=ROOT / "prepared/retrospective_multicohort_phase4_predictions_v1")
    result.add_argument("--phase4-evaluation", type=Path, default=ROOT / "evaluation/retrospective_multicohort_phase4_v1")
    result.add_argument("--development-manifest", type=Path, default=ROOT / "prepared/development_v1/manifests/development_inputs.jsonl")
    result.add_argument("--holdout-manifest", type=Path, default=ROOT / "prepared/holdout_blind_v1/manifests/holdout_inputs.jsonl")
    result.add_argument("--development-modes", type=Path, default=ROOT / "prepared/development_v16_full87_v1/cohort_manifest.json")
    result.add_argument("--holdout-alignment-summary", type=Path, default=ROOT / "prepared/holdout_alignment_v1_summary.json")
    result.add_argument("--development-alignments", type=Path, default=ROOT / "prepared/development_alignment_v1")
    result.add_argument("--holdout-alignments", type=Path, default=ROOT / "prepared/holdout_alignment_v1")
    result.add_argument("--config", type=Path, default=Path("configs/medgemma_local_4b_openswiss_v24_liver_enriched_choice.yaml"))
    result.add_argument("--protocol", type=Path, default=ROOT / "prepared/v24_liver_enriched_protocol_v1.json")
    result.add_argument("--pilot-root", type=Path, default=ROOT / "prepared/v24_liver_enriched_pilot10_v1")
    result.add_argument("--gallery-root", type=Path, default=ROOT / "prepared/v24_liver_enriched_gallery10_v1")
    result.add_argument("--reviewer", default="jm")
    result.add_argument(
        "--review",
        type=Path,
        default=ROOT / "prepared/v24_liver_enriched_review_v1.json",
    )
    result.add_argument(
        "--full-root",
        type=Path,
        default=ROOT / "prepared/v24_liver_enriched_full130_v1",
    )
    result.add_argument(
        "--full-verification",
        type=Path,
        default=ROOT / "prepared/v24_liver_enriched_full130_verification_v1.json",
    )
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.command == "freeze":
            value = freeze_v24_liver_enriched_protocol(
                phase4_evaluation_root=args.phase4_evaluation,
                phase4_prediction_root=args.phase4_predictions,
                phase3_root=args.phase3,
                phase2_root=args.phase2,
                contract_path=args.contract,
                baseline_lock_path=args.baseline_lock,
                workspace_root=args.workspace,
                development_manifest=args.development_manifest,
                holdout_manifest=args.holdout_manifest,
                development_mode_manifest=args.development_modes,
                holdout_alignment_summary=args.holdout_alignment_summary,
                config_path=args.config,
                output_path=args.protocol,
            )
        elif args.command == "verify":
            value = verify_v24_liver_enriched_protocol(
                protocol_path=args.protocol, config_path=args.config
            )
        elif args.command == "pilot":
            value = build_v24_liver_enriched_pilot(
                protocol_path=args.protocol,
                config_path=args.config,
                development_manifest=args.development_manifest,
                holdout_manifest=args.holdout_manifest,
                development_mode_manifest=args.development_modes,
                holdout_alignment_summary=args.holdout_alignment_summary,
                development_alignment_root=args.development_alignments,
                holdout_alignment_root=args.holdout_alignments,
                output_root=args.pilot_root,
            )
        elif args.command == "gallery":
            value = build_v24_liver_enriched_gallery(
                pilot_root=args.pilot_root, output_root=args.gallery_root
            )
        elif args.command == "approve":
            value = approve_v24_liver_enriched_gallery(
                protocol_path=args.protocol,
                config_path=args.config,
                gallery_root=args.gallery_root,
                reviewer=args.reviewer,
                output_path=args.review,
            )
        elif args.command == "full":
            value = build_v24_liver_enriched_full_cohort(
                protocol_path=args.protocol,
                review_path=args.review,
                gallery_root=args.gallery_root,
                config_path=args.config,
                development_manifest=args.development_manifest,
                holdout_manifest=args.holdout_manifest,
                development_mode_manifest=args.development_modes,
                holdout_alignment_summary=args.holdout_alignment_summary,
                development_alignment_root=args.development_alignments,
                holdout_alignment_root=args.holdout_alignments,
                output_root=args.full_root,
            )
        else:
            value = verify_v24_liver_enriched_full_cohort(
                protocol_path=args.protocol,
                review_path=args.review,
                gallery_root=args.gallery_root,
                config_path=args.config,
                panel_root=args.full_root,
                output_path=args.full_verification,
            )
    except PipelineError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 2
    print(json.dumps({"ok": True, "result": value}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
