#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from dtwin.benchmark.openswisshcc_candidate_volume_evaluation import evaluate_development
from dtwin.core import PipelineError


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Avalia o leitor focal v16 com labels autorizados.")
    parser.add_argument("--bundle-root", required=True, type=Path)
    parser.add_argument("--run-root", required=True, type=Path)
    parser.add_argument("--score-protocol", required=True, type=Path)
    parser.add_argument("--evaluation-protocol", required=True, type=Path)
    parser.add_argument("--development-labels", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--expected-case-count", type=int, default=87)
    parser.add_argument("--allow-protected-development-labels", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = evaluate_development(
            bundle_root=args.bundle_root,
            run_root=args.run_root,
            score_protocol_path=args.score_protocol,
            evaluation_protocol_path=args.evaluation_protocol,
            labels_path=args.development_labels,
            output_dir=args.output_dir,
            allow_protected_development_labels=args.allow_protected_development_labels,
            expected_case_count=args.expected_case_count,
        )
    except PipelineError as exc:
        print(f"[ABORTADO] {exc}", flush=True)
        return 1
    print(json.dumps(result, ensure_ascii=False, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
