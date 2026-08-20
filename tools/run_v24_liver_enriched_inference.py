#!/usr/bin/env python3
"""Freeze, run, resume, and verify OpenSwissHCC v24 4B inference."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from dtwin.benchmark.v24_liver_enriched_inference import (
    freeze_v24_liver_enriched_inference_protocol,
    run_v24_liver_enriched_inference,
    verify_v24_liver_enriched_inference_protocol,
    verify_v24_liver_enriched_inference_run,
)
from dtwin.core import PipelineError

ROOT = Path("casos/qualification/openswisshcc_v1/prepared")


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("command", choices=("freeze", "verify", "run", "verify-run"))
    result.add_argument(
        "--source-protocol",
        type=Path,
        default=ROOT / "v24_liver_enriched_protocol_v1.json",
    )
    result.add_argument(
        "--review",
        type=Path,
        default=ROOT / "v24_liver_enriched_review_v1.json",
    )
    result.add_argument(
        "--gallery",
        type=Path,
        default=ROOT / "v24_liver_enriched_gallery10_v1",
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
        default=ROOT / "v24_liver_enriched_full130_v1",
    )
    result.add_argument(
        "--full-verification",
        type=Path,
        default=ROOT / "v24_liver_enriched_full130_verification_v1.json",
    )
    result.add_argument(
        "--protocol",
        type=Path,
        default=ROOT / "v24_liver_enriched_inference_protocol_v1.json",
    )
    result.add_argument(
        "--output",
        type=Path,
        default=ROOT / "v24_liver_enriched_inference130_v1",
    )
    result.add_argument(
        "--run-verification",
        type=Path,
        default=ROOT / "v24_liver_enriched_inference130_verification_v1.json",
    )
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    common = {
        "source_protocol_path": args.source_protocol,
        "review_path": args.review,
        "gallery_root": args.gallery,
        "config_path": args.config,
        "panel_root": args.panels,
        "full_verification_path": args.full_verification,
        "panel_config_path": args.panel_config,
        "candidate_id": args.candidate_id,
        "predecessor_evaluation_path": args.predecessor_evaluation,
    }
    try:
        if args.command == "freeze":
            value = freeze_v24_liver_enriched_inference_protocol(
                **common, output_path=args.protocol
            )
        elif args.command == "verify":
            value, _cohort, _config = (
                verify_v24_liver_enriched_inference_protocol(
                    **common, inference_protocol_path=args.protocol
                )
            )
        elif args.command == "run":
            value = run_v24_liver_enriched_inference(
                **common,
                inference_protocol_path=args.protocol,
                output_root=args.output,
            )
        else:
            value = verify_v24_liver_enriched_inference_run(
                **common,
                inference_protocol_path=args.protocol,
                output_root=args.output,
                verification_output_path=args.run_verification,
            )
    except (PipelineError, OSError, RuntimeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 2
    print(json.dumps({"ok": True, "result": value}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
