from __future__ import annotations

import argparse
import json
from pathlib import Path

from dtwin.benchmark.openswisshcc_enhancement_timing_projection import (
    project_enhancement_top5_timing,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--historical-score-root", type=Path, required=True)
    parser.add_argument("--historical-timing-report", type=Path, required=True)
    parser.add_argument("--proposal-summary", type=Path, required=True)
    parser.add_argument("--preflight", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--expected-historical-case-count", type=int, default=87)
    args = parser.parse_args()
    result = project_enhancement_top5_timing(
        historical_score_root=args.historical_score_root,
        historical_timing_report_path=args.historical_timing_report,
        proposal_summary_path=args.proposal_summary,
        preflight_path=args.preflight,
        output_path=args.out,
        expected_historical_case_count=args.expected_historical_case_count,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
