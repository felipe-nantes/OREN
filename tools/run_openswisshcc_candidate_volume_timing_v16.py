from __future__ import annotations

import argparse
import json
from pathlib import Path

from dtwin.benchmark.openswisshcc_candidate_volume_timing_run import run_candidate_volume_timing_pilot
from dtwin.core import PipelineError


def main() -> int:
    parser = argparse.ArgumentParser(description="Executa o preflight ou piloto temporal focal v16.")
    parser.add_argument("--bundle-root", required=True, type=Path)
    parser.add_argument("--review", required=True, type=Path)
    parser.add_argument("--protocol", required=True, type=Path)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--timing-plan", required=True, type=Path)
    parser.add_argument("--localizer-run", required=True, type=Path)
    parser.add_argument("--input-manifest", required=True, type=Path)
    parser.add_argument("--input-root", required=True, type=Path)
    parser.add_argument("--registration-root", required=True, type=Path)
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument("--work-root", type=Path, default=Path(".timing-v16-work"))
    parser.add_argument("--expected-source-case-count", type=int, default=88)
    parser.add_argument("--preflight-only", action="store_true")
    args = parser.parse_args()
    try:
        result = run_candidate_volume_timing_pilot(
            bundle_root=args.bundle_root,
            review_path=args.review,
            protocol_path=args.protocol,
            config_path=args.config,
            timing_plan_path=args.timing_plan,
            localizer_run=args.localizer_run,
            input_manifest=args.input_manifest,
            input_root=args.input_root,
            registration_root=args.registration_root,
            output_root=args.output_root,
            work_root=args.work_root,
            expected_source_case_count=args.expected_source_case_count,
            preflight_only=args.preflight_only,
        )
    except PipelineError as exc:
        print(f"[ABORTADO] {exc}")
        return 1
    print(json.dumps({
        "status": result["status"],
        "case_count": result["case_count"],
        "candidate_request_count": result["candidate_request_count"],
        "pilot_wall_seconds": result["pilot_wall_seconds"],
        "full87_authorized_by_timing": result["full87_authorized_by_timing"],
        "inference_executed": result["inference_executed"],
        "ground_truth_read": result["ground_truth_read"],
        "holdout_opened": result["holdout_opened"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
