"""Create the signed blind v9 chunk plan."""
import argparse
import json
from pathlib import Path

from dtwin.benchmark.openswisshcc_multisequence_chunks import create_chunk_plan


def main():
 p=argparse.ArgumentParser();p.add_argument('--panels',type=Path,required=True);p.add_argument('--review',type=Path,required=True);p.add_argument('--freeze',type=Path,required=True);p.add_argument('--config',type=Path,required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--expected-case-count',type=int,default=87);p.add_argument('--chunk-size',type=int,default=8);a=p.parse_args()
 r=create_chunk_plan(panel_root=a.panels,review_path=a.review,freeze_path=a.freeze,config_path=a.config,output_path=a.out,expected_case_count=a.expected_case_count,chunk_size=a.chunk_size);print(json.dumps({"chunk_count":r["chunk_count"],"case_count":r["case_count"],"plan_signature":r["plan_signature"]}));return 0
if __name__=='__main__':raise SystemExit(main())
