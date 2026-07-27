#!/usr/bin/env python3
"""Safely extract only the MRI train arm from the verified CHAOS v1.03 ZIP."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from dtwin.core import PipelineError
from dtwin.datasets.chaos_download import extract_chaos_mri_train


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--download-root", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--expected-subject-count", type=int, default=20)
    args = parser.parse_args()
    try:
        result = extract_chaos_mri_train(
            download_root=args.download_root,
            output_dir=args.out,
            expected_subject_count=args.expected_subject_count,
        )
    except PipelineError as exc:
        print(f"[ABORTADO] {exc}")
        return 1
    print(json.dumps(result, ensure_ascii=True, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

