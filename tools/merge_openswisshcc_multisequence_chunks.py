"""Merge complete signed v9 chunks into one blind run."""
import argparse
import json
from pathlib import Path

from dtwin.benchmark.openswisshcc_multisequence_chunks import merge_chunk_runs


def main():
 p=argparse.ArgumentParser();p.add_argument('--chunks',type=Path,required=True);p.add_argument('--plan',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args();r=merge_chunk_runs(chunks_root=a.chunks,plan_path=a.plan,output_root=a.out);print(json.dumps(r,sort_keys=True));return 0
if __name__=='__main__':raise SystemExit(main())
