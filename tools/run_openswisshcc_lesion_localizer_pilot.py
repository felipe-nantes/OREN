"""Run a deterministic scores-only OpenSwissHCC MR lesion-localizer pilot."""
import argparse
import json
from pathlib import Path

from dtwin.benchmark.openswisshcc_lesion_localizer import TotalSegmentatorMRLesionLocalizer,run_localizer_scores
from dtwin.benchmark.openswisshcc_multisequence_chunks import verify_chunk_plan


def main() -> int:
    parser=argparse.ArgumentParser();parser.add_argument('--manifest',type=Path,required=True);parser.add_argument('--inputs-root',type=Path,required=True);parser.add_argument('--selection-plan',type=Path,required=True);parser.add_argument('--out',type=Path,required=True);parser.add_argument('--count',type=int,default=10);parser.add_argument('--expected-source-case-count',type=int,default=88);parser.add_argument('--expected-primary-case-count',type=int,default=87);parser.add_argument('--max-localizer-seconds',type=float,default=90.0);args=parser.parse_args()
    raw=json.loads(args.selection_plan.read_text(encoding='utf-8'));plan=verify_chunk_plan(plan_path=args.selection_plan,experiment_signature=raw['experiment_signature'],review_signature=raw['review_signature'],expected_case_count=args.expected_primary_case_count)
    ordered=[case for chunk in plan['chunks'] for case in chunk['case_ids']]
    if not 1<=args.count<=len(ordered):raise SystemExit('count fora da coorte primaria')
    localizer=TotalSegmentatorMRLesionLocalizer();summary=run_localizer_scores(manifest_path=args.manifest,input_root=args.inputs_root,output_root=args.out,case_ids=ordered[:args.count],localizer=localizer,expected_source_case_count=args.expected_source_case_count,max_localizer_seconds=args.max_localizer_seconds,selection_signature=plan['plan_signature'],progress=lambda item:print(json.dumps(item),flush=True));print(json.dumps(summary,sort_keys=True));return 0


if __name__=='__main__':raise SystemExit(main())

