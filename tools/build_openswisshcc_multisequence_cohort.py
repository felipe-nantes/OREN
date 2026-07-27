"""Build the blind OpenSwissHCC multisequence v9 development cohort."""
import argparse, json
from pathlib import Path
from dtwin.benchmark.openswisshcc_multisequence_batch import build_multisequence_cohort
def main():
    p=argparse.ArgumentParser(); p.add_argument('--inputs',type=Path,required=True); p.add_argument('--manifest',type=Path,required=True); p.add_argument('--out',type=Path,required=True); p.add_argument('--expected-case-count',type=int,default=88); a=p.parse_args()
    r=build_multisequence_cohort(input_root=a.inputs,manifest_path=a.manifest,output_root=a.out,expected_case_count=a.expected_case_count); print(json.dumps({k:r[k] for k in ('case_count','panel_count','max_panels_per_case','cohort_signature')})); return 0
if __name__=='__main__': raise SystemExit(main())
