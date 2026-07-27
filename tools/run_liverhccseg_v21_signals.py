#!/usr/bin/env python3
"""Run reviewed LiverHccSeg v21 signals in separate GPU-safe stages."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from dtwin.benchmark.liverhccseg_v21_signals import (
    assemble_v21_raw_signals,
    build_v21_localizer_input_manifest,
    run_v21_medgemma_scores,
    run_v21_medsiglip_scores,
    verify_v21_signal_context,
)
from dtwin.benchmark.openswisshcc_lesion_localizer import (
    TotalSegmentatorMRLesionLocalizer,
    run_localizer_scores,
)
from dtwin.core import PipelineError
from dtwin.benchmark.windows_spawn_guard import (
    PYARROW_GUARD_ID,
    block_optional_module_for_spawn,
)
from dtwin.medgemma_client import HTTPJSONMedGemmaClient
from dtwin.medsiglip_zero_shot import MedSigLIPScorer


class HTTPChoiceScorer:
    def __init__(self, config):
        self.client = HTTPJSONMedGemmaClient(config)
        self.model_id = str(config["medgemma"]["model_id"])
        self.model_version = str(config["medgemma"]["model_version"])

    def score_panel(self, panel_path: Path, prompt: str):
        self.client.generate(panel_path, prompt)
        probabilities = self.client.last_response_audit.get("choice_probabilities")
        return {"choice_probabilities": probabilities}


def _add_context(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--panels", type=Path, required=True)
    parser.add_argument("--gallery", type=Path, required=True)
    parser.add_argument("--review", type=Path, required=True)
    parser.add_argument("--prepared", type=Path, required=True)
    parser.add_argument("--medgemma-config", type=Path, required=True)
    parser.add_argument("--medsiglip-config", type=Path, required=True)
    parser.add_argument("--expected-case-count", type=int, default=14)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    manifest = commands.add_parser("localizer-manifest")
    _add_context(manifest); manifest.add_argument("--out", type=Path, required=True)
    localizer = commands.add_parser("localizer")
    _add_context(localizer); localizer.add_argument("--manifest", type=Path, required=True); localizer.add_argument("--out", type=Path, required=True)
    medsiglip = commands.add_parser("medsiglip")
    _add_context(medsiglip); medsiglip.add_argument("--out", type=Path, required=True); medsiglip.add_argument("--device", choices=("cpu", "cuda"), default="cuda")
    medgemma = commands.add_parser("medgemma")
    _add_context(medgemma); medgemma.add_argument("--out", type=Path, required=True)
    assemble = commands.add_parser("assemble")
    _add_context(assemble); assemble.add_argument("--medgemma", type=Path, required=True); assemble.add_argument("--medsiglip", type=Path, required=True); assemble.add_argument("--localizer", type=Path, required=True); assemble.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    common = dict(
        panel_root=args.panels, gallery_root=args.gallery, review_path=args.review,
        prepared_root=args.prepared, medgemma_config_path=args.medgemma_config,
        medsiglip_config_path=args.medsiglip_config, expected_case_count=args.expected_case_count,
    )
    try:
        if args.command == "localizer-manifest":
            result = build_v21_localizer_input_manifest(**common, output_path=args.out)
        else:
            context = verify_v21_signal_context(**common)
            if args.command == "localizer":
                with block_optional_module_for_spawn("pyarrow") as guarded:
                    model = TotalSegmentatorMRLesionLocalizer()
                    result = run_localizer_scores(
                        manifest_path=args.manifest, input_root=args.prepared, output_root=args.out,
                        case_ids=context["case_ids"], localizer=model,
                        expected_source_case_count=args.expected_case_count, max_localizer_seconds=90.0,
                        selection_signature=context["review_signature"],
                        runtime_guard=PYARROW_GUARD_ID if guarded else None,
                        progress=lambda item: print(json.dumps(item, sort_keys=True), flush=True),
                    )
            elif args.command == "medsiglip":
                scorer = MedSigLIPScorer(context["medsiglip_config"], local_files_only=True, device=args.device)
                result = run_v21_medsiglip_scores(context=context, panel_root=args.panels, output_root=args.out, scorer=scorer)
            elif args.command == "medgemma":
                scorer = HTTPChoiceScorer(context["medgemma_config"])
                result = run_v21_medgemma_scores(context=context, panel_root=args.panels, output_root=args.out, scorer=scorer)
            else:
                result = assemble_v21_raw_signals(
                    context=context, medgemma_root=args.medgemma, medsiglip_root=args.medsiglip,
                    localizer_root=args.localizer, output_dir=args.out,
                )
    except PipelineError as exc:
        print(f"[ABORTADO] {exc}")
        return 1
    print(json.dumps(result, ensure_ascii=True, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
