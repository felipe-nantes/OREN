#!/usr/bin/env python3
"""Run the reviewed OpenSwissHCC holdout v21 in GPU-safe label-blind stages."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from dtwin.benchmark.openswisshcc_holdout_signals import (
    assemble_holdout_v21_raw_signals,
    build_holdout_v21_localizer_input_manifest,
    context_preflight_summary,
    freeze_holdout_v21_predictions,
    run_holdout_v21_medgemma_scores,
    run_holdout_v21_medsiglip_scores,
    score_holdout_v21_blind,
    verify_holdout_v21_signal_context,
)
from dtwin.benchmark.openswisshcc_lesion_localizer import (
    TotalSegmentatorMRLesionLocalizer,
    run_localizer_scores,
)
from dtwin.benchmark.windows_spawn_guard import (
    PYARROW_GUARD_ID,
    block_optional_module_for_spawn,
)
from dtwin.core import PipelineError
from dtwin.medgemma_client import HTTPJSONMedGemmaClient
from dtwin.medsiglip_zero_shot import MedSigLIPScorer


class HTTPChoiceScorer:
    def __init__(self, config):
        self.client = HTTPJSONMedGemmaClient(config)
        self.model_id = str(config["medgemma"]["model_id"])
        self.model_version = str(config["medgemma"]["model_version"])

    def score_panel(self, panel_path: Path, prompt: str):
        self.client.generate(panel_path, prompt)
        return {
            "choice_probabilities": self.client.last_response_audit.get("choice_probabilities")
        }


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
    parser.add_argument("--expected-case-count", type=int, default=44)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    preflight = commands.add_parser("preflight")
    _add_context(preflight)
    manifest = commands.add_parser("localizer-manifest")
    _add_context(manifest)
    manifest.add_argument("--out", type=Path, required=True)
    localizer = commands.add_parser("localizer")
    _add_context(localizer)
    localizer.add_argument("--manifest", type=Path, required=True)
    localizer.add_argument("--out", type=Path, required=True)
    medsiglip = commands.add_parser("medsiglip")
    _add_context(medsiglip)
    medsiglip.add_argument("--out", type=Path, required=True)
    medsiglip.add_argument("--device", choices=("cpu", "cuda"), default="cuda")
    medgemma = commands.add_parser("medgemma")
    _add_context(medgemma)
    medgemma.add_argument("--out", type=Path, required=True)
    assemble = commands.add_parser("assemble")
    _add_context(assemble)
    assemble.add_argument("--medgemma", type=Path, required=True)
    assemble.add_argument("--medsiglip", type=Path, required=True)
    assemble.add_argument("--localizer", type=Path, required=True)
    assemble.add_argument("--out", type=Path, required=True)
    score = commands.add_parser("score")
    _add_context(score)
    score.add_argument("--signals", type=Path, required=True)
    score.add_argument("--out", type=Path, required=True)
    freeze = commands.add_parser("freeze")
    _add_context(freeze)
    freeze.add_argument("--raw-signals", type=Path, required=True)
    freeze.add_argument("--scores", type=Path, required=True)
    freeze.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    common = {
        "panel_root": args.panels,
        "gallery_root": args.gallery,
        "review_path": args.review,
        "prepared_root": args.prepared,
        "prepared_audit_path": args.prepared_audit,
        "multiphase_config_path": args.multiphase_config,
        "fallback_config_path": args.fallback_config,
        "medsiglip_config_path": args.medsiglip_config,
        "calibrator_path": args.calibrator,
        "expected_case_count": args.expected_case_count,
    }
    try:
        context = verify_holdout_v21_signal_context(**common)
        if args.command == "preflight":
            result = context_preflight_summary(context)
        elif args.command == "localizer-manifest":
            result = build_holdout_v21_localizer_input_manifest(
                context=context, prepared_root=args.prepared, output_path=args.out
            )
        elif args.command == "localizer":
            with block_optional_module_for_spawn("pyarrow") as guarded:
                model = TotalSegmentatorMRLesionLocalizer()
                result = run_localizer_scores(
                    manifest_path=args.manifest,
                    input_root=Path(args.prepared).resolve() / "inputs",
                    output_root=args.out,
                    case_ids=context["case_ids"],
                    localizer=model,
                    expected_source_case_count=44,
                    max_localizer_seconds=90.0,
                    selection_signature=context["review_signature"],
                    runtime_guard=PYARROW_GUARD_ID if guarded else None,
                    progress=lambda item: print(json.dumps(item, sort_keys=True), flush=True),
                )
        elif args.command == "medsiglip":
            scorer = MedSigLIPScorer(
                context["medsiglip_config"], local_files_only=True, device=args.device
            )
            result = run_holdout_v21_medsiglip_scores(
                context=context,
                panel_root=args.panels,
                output_root=args.out,
                scorer=scorer,
            )
        elif args.command == "medgemma":
            multiphase = HTTPChoiceScorer(context["multiphase_config"])
            fallback = HTTPChoiceScorer(context["fallback_config"])
            result = run_holdout_v21_medgemma_scores(
                context=context,
                panel_root=args.panels,
                output_root=args.out,
                multiphase_scorer=multiphase,
                fallback_scorer=fallback,
            )
        elif args.command == "assemble":
            result = assemble_holdout_v21_raw_signals(
                context=context,
                medgemma_root=args.medgemma,
                medsiglip_root=args.medsiglip,
                localizer_root=args.localizer,
                output_dir=args.out,
            )
        elif args.command == "score":
            result = score_holdout_v21_blind(
                context=context, signals_path=args.signals, output_dir=args.out
            )
        else:
            result = freeze_holdout_v21_predictions(
                context=context,
                raw_signal_root=args.raw_signals,
                score_root=args.scores,
                output_path=args.out,
            )
    except PipelineError as exc:
        print(f"[ABORTADO] {exc}")
        return 1
    print(json.dumps(result, ensure_ascii=True, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
