"""Freeze reviewed OpenSwissHCC multisequence v9 experiment."""
import argparse,json
from pathlib import Path
from dtwin.benchmark.openswisshcc_multisequence_freeze import create_multisequence_freeze,verify_multisequence_freeze
def main():
 p=argparse.ArgumentParser(); p.add_argument('--panels',type=Path,required=True); p.add_argument('--review',type=Path,required=True); p.add_argument('--config',type=Path,required=True); p.add_argument('--out',type=Path,required=True); p.add_argument('--experiment-version',required=True); p.add_argument('--expected-case-count',type=int,default=88); a=p.parse_args()
 r=create_multisequence_freeze(panel_root=a.panels,review_path=a.review,config_path=a.config,output_path=a.out,experiment_version=a.experiment_version,expected_case_count=a.expected_case_count); verify_multisequence_freeze(panel_root=a.panels,review_path=a.review,config_path=a.config,freeze_path=a.out,expected_case_count=a.expected_case_count); print(json.dumps({"experiment_signature":r["experiment_signature"],"max_case_seconds":r["max_case_seconds"],"verified":True})); return 0
if __name__=='__main__': raise SystemExit(main())
