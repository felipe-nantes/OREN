"""Build the blind local review gallery for OpenSwissHCC multisequence v9."""
import argparse
import json
from pathlib import Path

from dtwin.benchmark.openswisshcc_multisequence_batch import build_multisequence_gallery


def main():
    p=argparse.ArgumentParser(); p.add_argument('--panels',type=Path,required=True); p.add_argument('--out',type=Path,required=True); p.add_argument('--expected-case-count',type=int,default=88); a=p.parse_args()
    r=build_multisequence_gallery(panel_root=a.panels,output_dir=a.out,expected_case_count=a.expected_case_count); print(json.dumps({k:r[k] for k in ('case_count','panel_count','gallery_signature','authoritative_approval')})); return 0
if __name__=='__main__': raise SystemExit(main())
