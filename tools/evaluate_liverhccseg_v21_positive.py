#!/usr/bin/env python3
"""Evaluate the frozen LiverHccSeg v21 positive arm after explicit authorization."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from dtwin.benchmark.public_independent_v21_evaluation import (
    evaluate_liverhccseg_v21_positive_arm,
)
from dtwin.core import PipelineError


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scores", type=Path, required=True)
    parser.add_argument("--calibrator", type=Path, required=True)
    parser.add_argument("--prepared", type=Path, required=True)
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--authorized-protocol-signature", required=True)
    parser.add_argument("--protected-selection-audit", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--expected-case-count", type=int, default=14)
    parser.add_argument("--allow-protected-public-ground-truth", action="store_true")
    args = parser.parse_args()
    try:
        result = evaluate_liverhccseg_v21_positive_arm(
            scored_root=args.scores, calibrator_path=args.calibrator, prepared_root=args.prepared,
            protocol_path=args.protocol, authorized_protocol_signature=args.authorized_protocol_signature,
            protected_selection_audit_path=args.protected_selection_audit, output_dir=args.out,
            allow_protected_public_ground_truth=args.allow_protected_public_ground_truth,
            expected_case_count=args.expected_case_count,
        )
    except PipelineError as exc:
        print(f"[ABORTADO] {exc}")
        return 1
    print(json.dumps(result, ensure_ascii=True, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
