"""Run one signed blind OpenSwissHCC v10 lesion-localizer chunk."""
import argparse
import json
from pathlib import Path

from dtwin.benchmark.openswisshcc_lesion_localizer import TotalSegmentatorMRLesionLocalizer, run_localizer_scores
from dtwin.benchmark.openswisshcc_lesion_localizer_chunks import load_verified_selection_plan, planned_chunk


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--inputs-root", type=Path, required=True)
    parser.add_argument("--selection-plan", type=Path, required=True)
    parser.add_argument("--chunk-number", type=int, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--expected-source-case-count", type=int, default=88)
    parser.add_argument("--expected-primary-case-count", type=int, default=87)
    parser.add_argument("--max-localizer-seconds", type=float, default=90.0)
    args = parser.parse_args()
    plan = load_verified_selection_plan(args.selection_plan, args.expected_primary_case_count)
    case_ids = planned_chunk(plan, args.chunk_number)
    summary = run_localizer_scores(
        manifest_path=args.manifest,
        input_root=args.inputs_root,
        output_root=args.out,
        case_ids=case_ids,
        localizer=TotalSegmentatorMRLesionLocalizer(),
        expected_source_case_count=args.expected_source_case_count,
        max_localizer_seconds=args.max_localizer_seconds,
        selection_signature=plan["plan_signature"],
        progress=lambda item: print(json.dumps(item, sort_keys=True), flush=True),
    )
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
