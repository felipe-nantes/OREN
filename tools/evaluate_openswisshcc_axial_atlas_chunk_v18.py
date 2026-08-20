#!/usr/bin/env python3
"""Avalia o scorer em blocos v18 no desenvolvimento protegido."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dtwin.benchmark.openswisshcc_axial_atlas_chunk_evaluation import (
    evaluate_chunk_development,
)
from dtwin.core import PipelineError


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scores", required=True, type=Path)
    parser.add_argument("--protocol", required=True, type=Path)
    parser.add_argument("--labels", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--allow-protected-development-labels", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = evaluate_chunk_development(score_root=args.scores, protocol_path=args.protocol, labels_path=args.labels, output_dir=args.out, allow_protected_development_labels=args.allow_protected_development_labels)
    except PipelineError as exc:
        print(f"[ABORTADO] {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
