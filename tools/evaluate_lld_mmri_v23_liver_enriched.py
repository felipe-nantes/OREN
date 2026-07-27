#!/usr/bin/env python3
"""Freeze and evaluate the signed LLD-MMRI liver-enriched run."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from dtwin.benchmark.lld_mmri_v23_liver_enriched_evaluation import (
    evaluate_liver_enriched_predictions,
    freeze_liver_enriched_evaluation_protocol,
    freeze_liver_enriched_predictions,
    verify_liver_enriched_predictions,
)
from dtwin.core import PipelineError


def _common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--protocol-root", type=Path, required=True)
    parser.add_argument("--panels", type=Path, required=True)
    parser.add_argument("--gallery", type=Path, required=True)
    parser.add_argument("--review", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--timing-protocol", type=Path, required=True)
    parser.add_argument("--timing-output", type=Path, required=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    freeze_protocol = sub.add_parser("freeze-protocol")
    _common(freeze_protocol)
    freeze_protocol.add_argument("--output", type=Path, required=True)
    freeze_predictions = sub.add_parser("freeze-predictions")
    _common(freeze_predictions)
    freeze_predictions.add_argument("--evaluation-protocol", type=Path, required=True)
    freeze_predictions.add_argument("--output", type=Path, required=True)
    verify_predictions = sub.add_parser("verify-predictions")
    _common(verify_predictions)
    verify_predictions.add_argument("--evaluation-protocol", type=Path, required=True)
    verify_predictions.add_argument("--predictions", type=Path, required=True)
    evaluate = sub.add_parser("evaluate")
    _common(evaluate)
    evaluate.add_argument("--evaluation-protocol", type=Path, required=True)
    evaluate.add_argument("--predictions", type=Path, required=True)
    evaluate.add_argument("--protected-labels", type=Path, required=True)
    evaluate.add_argument("--output", type=Path, required=True)
    evaluate.add_argument("--allow-protected-public-labels", action="store_true")
    args = parser.parse_args()
    common = {
        "protocol_root": args.protocol_root,
        "panel_root": args.panels,
        "gallery_root": args.gallery,
        "review_path": args.review,
        "config_path": args.config,
        "timing_protocol_path": args.timing_protocol,
        "timing_output_root": args.timing_output,
    }
    try:
        if args.command == "freeze-protocol":
            result = freeze_liver_enriched_evaluation_protocol(
                **common, output_path=args.output
            )
        elif args.command == "freeze-predictions":
            result = freeze_liver_enriched_predictions(
                **common, evaluation_protocol_path=args.evaluation_protocol,
                output_root=args.output,
            )
        elif args.command == "verify-predictions":
            result, _ = verify_liver_enriched_predictions(
                **common, evaluation_protocol_path=args.evaluation_protocol,
                prediction_root=args.predictions,
            )
        else:
            result = evaluate_liver_enriched_predictions(
                **common, evaluation_protocol_path=args.evaluation_protocol,
                prediction_root=args.predictions,
                protected_labels_path=args.protected_labels,
                output_root=args.output,
                allow_protected_public_labels=args.allow_protected_public_labels,
            )
    except PipelineError as exc:
        parser.error(str(exc))
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
