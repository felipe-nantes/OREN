from __future__ import annotations

import argparse
import json
from pathlib import Path

from dtwin.benchmark.openswisshcc_candidate_volume_full87 import build_candidate_volume_full87_gallery
from dtwin.core import PipelineError


def main() -> int:
    parser = argparse.ArgumentParser(description="Gera o bundle/galeria paginada full87 focal v16.")
    parser.add_argument("--timing-bundle-root", required=True, type=Path)
    parser.add_argument("--timing-review", required=True, type=Path)
    parser.add_argument("--timing-protocol", required=True, type=Path)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--timing-report", required=True, type=Path)
    parser.add_argument("--timing-plan", required=True, type=Path)
    parser.add_argument("--fallback-bundle-root", required=True, type=Path)
    parser.add_argument("--fallback-review", required=True, type=Path)
    parser.add_argument("--localizer-run", required=True, type=Path)
    parser.add_argument("--input-manifest", required=True, type=Path)
    parser.add_argument("--input-root", required=True, type=Path)
    parser.add_argument("--registration-root", required=True, type=Path)
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument("--expected-source-case-count", type=int, default=88)
    parser.add_argument("--expected-case-count", type=int, default=87)
    args = parser.parse_args()
    try:
        result = build_candidate_volume_full87_gallery(
            timing_bundle_root=args.timing_bundle_root,
            timing_review_path=args.timing_review,
            timing_protocol_path=args.timing_protocol,
            config_path=args.config,
            timing_report_path=args.timing_report,
            timing_plan_path=args.timing_plan,
            fallback_bundle_root=args.fallback_bundle_root,
            fallback_review_path=args.fallback_review,
            localizer_run=args.localizer_run,
            input_manifest=args.input_manifest,
            input_root=args.input_root,
            registration_root=args.registration_root,
            output_root=args.output_root,
            expected_source_case_count=args.expected_source_case_count,
            expected_case_count=args.expected_case_count,
        )
    except PipelineError as exc:
        print(f"[ABORTADO] {exc}")
        return 1
    print(json.dumps({
        "case_count": result["case_count"],
        "candidate_stack_count": result["candidate_stack_count"],
        "registered_case_count": result["registered_case_count"],
        "fallback_case_count": result["unregistered_approved_fallback_case_count"],
        "gallery_page_count": len(result["gallery_pages"]),
        "gallery_signature": result["gallery_signature"],
        "technical_review_status": result["technical_review_status"],
        "ground_truth_read": result["ground_truth_read"],
        "holdout_opened": result["holdout_opened"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
