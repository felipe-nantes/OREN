#!/usr/bin/env python3
"""Verify every image, mask, hash and claim guard in a synthetic stress cohort."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from dtwin.benchmark.synthetic_external_stress_v1 import verify_cohort
from dtwin.core import PipelineError


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cohort", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = verify_cohort(args.cohort)
        (args.cohort / "verification.json").write_text(
            json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        print(json.dumps(report, sort_keys=True))
        return 0
    except (PipelineError, OSError, ValueError, RuntimeError) as exc:
        print(f"[ABORTED] {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
