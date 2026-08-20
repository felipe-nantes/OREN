"""Run one signed blind v9 chunk with local MedGemma 1.5 4B."""
import argparse
import json
from pathlib import Path

from dtwin.benchmark.openswisshcc_multisequence_chunks import verify_chunk_plan
from dtwin.benchmark.openswisshcc_multisequence_freeze import (
 verify_multisequence_freeze,
)
from dtwin.benchmark.openswisshcc_multisequence_inference import (
 run_multisequence_scores,
)
from tools.run_openswisshcc_volumetric_pairwise import LocalPairwiseScorer


def main():
 p=argparse.ArgumentParser();p.add_argument('--panels',type=Path,required=True);p.add_argument('--review',type=Path,required=True);p.add_argument('--freeze',type=Path,required=True);p.add_argument('--config',type=Path,required=True);p.add_argument('--plan',type=Path,required=True);p.add_argument('--chunk-number',type=int,required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--expected-case-count',type=int,default=87);a=p.parse_args()
 f=verify_multisequence_freeze(panel_root=a.panels,review_path=a.review,config_path=a.config,freeze_path=a.freeze,expected_case_count=a.expected_case_count);plan=verify_chunk_plan(plan_path=a.plan,experiment_signature=f["experiment_signature"],review_signature=f["review_signature"],expected_case_count=a.expected_case_count)
 if not 1<=a.chunk_number<=plan["chunk_count"]:raise SystemExit("chunk-number invalido")
 scorer=LocalPairwiseScorer(a.config)
 try:r=run_multisequence_scores(panel_root=a.panels,review_path=a.review,freeze_path=a.freeze,config_path=a.config,output_root=a.out,scorer=scorer,expected_case_count=a.expected_case_count,case_ids=plan["chunks"][a.chunk_number-1]["case_ids"],progress=lambda x:print(json.dumps(x),flush=True))
 finally:scorer.close()
 print(json.dumps(r,sort_keys=True));return 0
if __name__=='__main__':raise SystemExit(main())
