#!/usr/bin/env python3
"""Open and evaluate OpenSwissHCC holdout labels only after a signed blind freeze."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from dtwin.benchmark.openswisshcc_holdout_evaluation import (
    evaluate_holdout_v21_same_domain,
    materialize_holdout_v21_labels_after_freeze,
)
from dtwin.benchmark.openswisshcc_holdout_signals import (
    verify_holdout_v21_signal_context,
)
from dtwin.core import PipelineError


def _add_context(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--panels", type=Path, required=True)
    parser.add_argument("--gallery", type=Path, required=True)
    parser.add_argument("--review", type=Path, required=True)
    parser.add_argument("--prepared", type=Path, required=True)
    parser.add_argument("--prepared-audit", type=Path, required=True)
    parser.add_argument("--multiphase-config", type=Path, required=True)
    parser.add_argument("--fallback-config", type=Path, required=True)
    parser.add_argument("--medsiglip-config", type=Path, required=True)
    parser.add_argument("--calibrator", type=Path, required=True)
    parser.add_argument("--raw-signals", type=Path, required=True)
    parser.add_argument("--scores", type=Path, required=True)
    parser.add_argument("--freeze", type=Path, required=True)
    parser.add_argument("--authorized-protocol-signature", required=True)
    parser.add_argument("--allow-protected-holdout-labels", action="store_true")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    materialize = commands.add_parser("materialize-labels")
    _add_context(materialize)
    materialize.add_argument("--participants", type=Path, required=True)
    materialize.add_argument("--protected-provenance", type=Path, required=True)
    materialize.add_argument("--out", type=Path, required=True)
    evaluate = commands.add_parser("evaluate")
    _add_context(evaluate)
    evaluate.add_argument("--protected-label-bundle", type=Path, required=True)
    evaluate.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    context_args = {
        "panel_root": args.panels,
        "gallery_root": args.gallery,
        "review_path": args.review,
        "prepared_root": args.prepared,
        "prepared_audit_path": args.prepared_audit,
        "multiphase_config_path": args.multiphase_config,
        "fallback_config_path": args.fallback_config,
        "medsiglip_config_path": args.medsiglip_config,
        "calibrator_path": args.calibrator,
        "expected_case_count": 44,
    }
    try:
        context = verify_holdout_v21_signal_context(**context_args)
        common = {
            "context": context,
            "raw_signal_root": args.raw_signals,
            "score_root": args.scores,
            "freeze_path": args.freeze,
            "authorized_protocol_signature": args.authorized_protocol_signature,
            "allow_protected_holdout_labels": args.allow_protected_holdout_labels,
        }
        if args.command == "materialize-labels":
            result = materialize_holdout_v21_labels_after_freeze(
                **common,
                participants_path=args.participants,
                protected_provenance_path=args.protected_provenance,
                output_dir=args.out,
            )
        else:
            result = evaluate_holdout_v21_same_domain(
                **common,
                protected_label_bundle_root=args.protected_label_bundle,
                output_dir=args.out,
            )
    except PipelineError as exc:
        print(f"[ABORTADO] {exc}")
        return 1
    print(json.dumps(result, ensure_ascii=True, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
