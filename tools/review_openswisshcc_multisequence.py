"""Record and verify immutable human approval of the multisequence v9 cohort."""
import argparse, json
from pathlib import Path
from dtwin.benchmark.openswisshcc_multisequence_gate import create_multisequence_review, verify_multisequence_review
def main():
    p=argparse.ArgumentParser(); p.add_argument('--panels',type=Path,required=True); p.add_argument('--out',type=Path,required=True); p.add_argument('--reviewer',required=True); p.add_argument('--expected-case-count',type=int,default=88)
    for flag in ('no-visible-phi','all-panels','cross-sequence-anatomy','liver-framing-contrast','out-of-fov-tiles'): p.add_argument('--confirm-'+flag,action='store_true')
    a=p.parse_args(); confirmations={"no_visible_phi":a.confirm_no_visible_phi,"all_panels_open_and_uncorrupted":a.confirm_all_panels,"cross_sequence_anatomy_acceptable":a.confirm_cross_sequence_anatomy,"liver_framing_and_contrast_acceptable":a.confirm_liver_framing_contrast,"out_of_fov_tiles_reviewed":a.confirm_out_of_fov_tiles}
    r=create_multisequence_review(panel_root=a.panels,output_path=a.out,reviewer=a.reviewer,confirmations=confirmations,expected_case_count=a.expected_case_count); verify_multisequence_review(panel_root=a.panels,review_path=a.out,expected_case_count=a.expected_case_count); print(json.dumps({"case_count":r["case_count"],"panel_count":r["panel_count"],"review_signature":r["review_signature"],"verified":True})); return 0
if __name__=='__main__': raise SystemExit(main())
