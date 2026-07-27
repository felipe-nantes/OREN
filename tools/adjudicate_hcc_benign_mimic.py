#!/usr/bin/env python3
"""Conservative second-stage HCC versus benign-mimic adjudication."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from dtwin.benchmark.benign_mimic_adjudication import adjudicate_hcc_vs_benign_mimic
from dtwin.core import PipelineError


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--first-pass-report", type=Path, required=True)
    parser.add_argument("--discriminator-report", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = adjudicate_hcc_vs_benign_mimic(
            first_pass_path=args.first_pass_report,
            discriminator_path=args.discriminator_report,
            output_path=args.output,
        )
    except PipelineError as exc:
        parser.error(str(exc))
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
