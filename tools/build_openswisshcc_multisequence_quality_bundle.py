"""Build atomic primary and stress v9 cohorts from signed blind quality decisions."""
import argparse
import json
from pathlib import Path

from dtwin.benchmark.openswisshcc_multisequence_quality_cohort import (
 build_quality_bundle,
)


def main():
 p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);p.add_argument('--quality-review',type=Path,required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--expected-source-count',type=int,default=88);a=p.parse_args()
 r=build_quality_bundle(source_root=a.source,quality_review_path=a.quality_review,output_root=a.out,expected_source_count=a.expected_source_count);print(json.dumps(r,sort_keys=True));return 0
if __name__=='__main__':raise SystemExit(main())
