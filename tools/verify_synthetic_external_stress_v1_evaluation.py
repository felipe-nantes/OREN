#!/usr/bin/env python3
"""Verify every signed record and metric of the synthetic stress evaluation."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from dtwin.benchmark.synthetic_external_stress_v1_eval import verify_evaluation
from dtwin.core import PipelineError


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evaluation", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = verify_evaluation(args.evaluation)
    except (PipelineError, OSError, ValueError) as exc:
        print(f"[ABORTED] {exc}")
        return 1
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
