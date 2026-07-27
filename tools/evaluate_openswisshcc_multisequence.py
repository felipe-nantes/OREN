"""Evaluate a complete blind v9 run after all scores are persisted."""
import argparse,json
from pathlib import Path
from dtwin.benchmark.openswisshcc_multisequence_evaluation import evaluate_multisequence_scores
def main():
 p=argparse.ArgumentParser();p.add_argument('--scores',type=Path,required=True);p.add_argument('--labels',type=Path,required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--expected-total',type=int,default=87);p.add_argument('--expected-positive',type=int);p.add_argument('--expected-negative',type=int);p.add_argument('--quality-review',type=Path);a=p.parse_args()
 r=evaluate_multisequence_scores(scores_root=a.scores,labels_path=a.labels,output_dir=a.out,expected_total=a.expected_total,expected_positive=a.expected_positive,expected_negative=a.expected_negative,quality_review_path=a.quality_review);print(json.dumps({"status":r["status"],"qualified":r["qualified"],"primary_feature":r["primary_feature"],"positive_count":r["positive_count"],"negative_count":r["negative_count"],"max_case_seconds":r["observed_max_case_seconds"]}));return 0
if __name__=='__main__':raise SystemExit(main())
