"""Create a blind technical-quality decision manifest for v9."""
import argparse,json
from pathlib import Path
from dtwin.benchmark.openswisshcc_multisequence_gate import validate_multisequence_cohort
from dtwin.benchmark.openswisshcc_multisequence_quality import create_quality_review,verify_quality_review,REASONS
def main():
 p=argparse.ArgumentParser();p.add_argument('--panels',type=Path,required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--reviewer',required=True);p.add_argument('--exclude',action='append',default=[],metavar='CASE_ID=REASON');p.add_argument('--expected-case-count',type=int,default=88);a=p.parse_args()
 records=validate_multisequence_cohort(a.panels,a.expected_case_count)["records"];decisions={r["case_id"]:{"status":"approved_primary","reason_code":None} for r in records}
 for raw in a.exclude:
  if '=' not in raw:raise SystemExit("--exclude exige CASE_ID=REASON")
  case,reason=raw.split('=',1)
  if case not in decisions or reason not in REASONS:raise SystemExit("case_id ou reason_code invalido")
  decisions[case]={"status":"technical_quality_exclusion","reason_code":reason}
 r=create_quality_review(panel_root=a.panels,output_path=a.out,reviewer=a.reviewer,decisions=decisions,expected_case_count=a.expected_case_count);verify_quality_review(panel_root=a.panels,review_path=a.out,expected_case_count=a.expected_case_count);print(json.dumps({"approved":r["approved_case_count"],"excluded":r["excluded_case_count"],"quality_review_signature":r["quality_review_signature"]}));return 0
if __name__=='__main__':raise SystemExit(main())
