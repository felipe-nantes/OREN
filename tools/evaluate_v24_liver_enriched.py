#!/usr/bin/env python3
"""Freeze and evaluate the OpenSwissHCC v24 liver-enriched candidate."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from dtwin.benchmark.v24_liver_enriched_evaluation import (
    evaluate_v24_oof_predictions,
    freeze_v24_oof_predictions,
)
from dtwin.core import PipelineError


ROOT = Path("casos/qualification/openswisshcc_v1")
PREPARED = ROOT / "prepared"


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("command", choices=("freeze", "evaluate"))
    result.add_argument("--workspace", type=Path, default=Path("."))
    result.add_argument(
        "--phase2", type=Path, default=PREPARED / "retrospective_multicohort_phase2_v1"
    )
    result.add_argument(
        "--phase3", type=Path, default=PREPARED / "retrospective_multicohort_phase3_v1"
    )
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
        "--source-protocol",
        type=Path,
        default=PREPARED / "v24_liver_enriched_protocol_v1.json",
    )
    result.add_argument(
        "--review",
        type=Path,
        default=PREPARED / "v24_liver_enriched_review_v1.json",
    )
    result.add_argument(
        "--gallery",
        type=Path,
        default=PREPARED / "v24_liver_enriched_gallery10_v1",
    )
    result.add_argument(
        "--config",
        type=Path,
        default=Path(
            "configs/medgemma_local_4b_openswiss_v24_liver_enriched_choice.yaml"
        ),
    )
    result.add_argument("--panel-config", type=Path)
    result.add_argument(
        "--candidate-id", default="v24_candidate_1_v23_plus_liver_enriched"
    )
    result.add_argument("--predecessor-evaluation", type=Path)
    result.add_argument(
        "--panels",
        type=Path,
        default=PREPARED / "v24_liver_enriched_full130_v1",
    )
    result.add_argument(
        "--full-verification",
        type=Path,
        default=PREPARED / "v24_liver_enriched_full130_verification_v1.json",
    )
    result.add_argument(
        "--inference-protocol",
        type=Path,
        default=PREPARED / "v24_liver_enriched_inference_protocol_v1.json",
    )
    result.add_argument(
        "--inference",
        type=Path,
        default=PREPARED / "v24_liver_enriched_inference130_v1",
    )
    result.add_argument(
        "--inference-verification",
        type=Path,
        default=PREPARED / "v24_liver_enriched_inference130_verification_v1.json",
    )
    result.add_argument(
        "--predictions",
        type=Path,
        default=PREPARED / "v24_liver_enriched_predictions_v1",
    )
    result.add_argument(
        "--evaluation",
        type=Path,
        default=ROOT / "evaluation/v24_liver_enriched_v1",
    )
    result.add_argument(
        "--v23-predictions",
        type=Path,
        default=PREPARED / "retrospective_multicohort_phase4_predictions_v1",
    )
    result.add_argument(
        "--v23-evaluation",
        type=Path,
        default=ROOT / "evaluation/retrospective_multicohort_phase4_v1",
    )
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.command == "freeze":
            value = freeze_v24_oof_predictions(
                phase3_root=args.phase3,
                phase2_root=args.phase2,
                contract_path=args.contract,
                baseline_lock_path=args.baseline_lock,
                workspace_root=args.workspace,
                source_protocol_path=args.source_protocol,
                review_path=args.review,
                gallery_root=args.gallery,
                config_path=args.config,
                panel_root=args.panels,
                full_verification_path=args.full_verification,
                inference_protocol_path=args.inference_protocol,
                inference_root=args.inference,
                inference_verification_path=args.inference_verification,
                output_root=args.predictions,
                panel_config_path=args.panel_config,
                candidate_id=args.candidate_id,
                predecessor_evaluation_path=args.predecessor_evaluation,
            )
        else:
            value = evaluate_v24_oof_predictions(
                prediction_root=args.predictions,
                phase2_root=args.phase2,
                v23_evaluation_root=args.v23_evaluation,
                v23_prediction_root=args.v23_predictions,
                phase3_root=args.phase3,
                contract_path=args.contract,
                baseline_lock_path=args.baseline_lock,
                workspace_root=args.workspace,
                output_root=args.evaluation,
            )
    except (PipelineError, OSError, RuntimeError, KeyError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 2
    print(json.dumps({"ok": True, "result": value}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
