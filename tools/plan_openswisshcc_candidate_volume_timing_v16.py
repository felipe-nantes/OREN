from __future__ import annotations

import argparse
import json
from pathlib import Path

from dtwin.benchmark.openswisshcc_candidate_volume_timing import build_timing_selection_plan
from dtwin.core import PipelineError


def main() -> int:
    parser = argparse.ArgumentParser(description="Congela casos criticos cegos para o piloto temporal v16.")
    parser.add_argument("--localizer-root", required=True, type=Path)
    parser.add_argument("--alignment-root", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    try:
        plan = build_timing_selection_plan(localizer_root=args.localizer_root, alignment_root=args.alignment_root, out_path=args.out)
    except PipelineError as exc:
        print(f"[ABORTADO] {exc}")
        return 1
    print(json.dumps({"status": plan["status"], "plan_signature": plan["plan_signature"], "selected_cases": [{"scenario": item["scenario"], "case_id": item["case_id"], "candidate_stack_count": item["candidate_stack_count"]} for item in plan["selected_cases"]], "ground_truth_read": plan["ground_truth_read"], "holdout_opened": plan["holdout_opened"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

