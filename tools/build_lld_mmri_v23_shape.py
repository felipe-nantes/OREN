#!/usr/bin/env python3
"""Build reviewed deterministic t3/top-5 shape signals for LLD-MMRI v23."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from dtwin.benchmark.lld_mmri_v23_shape import build_lld_mmri_v23_shape_branch
from dtwin.benchmark.lld_mmri_v23_signals import verify_lld_mmri_v23_signal_context
from dtwin.core import PipelineError


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol-root", type=Path, required=True)
    parser.add_argument("--panels", type=Path, required=True)
    parser.add_argument("--gallery", type=Path, required=True)
    parser.add_argument("--review", type=Path, required=True)
    parser.add_argument("--prepared", type=Path, required=True)
    parser.add_argument("--medgemma-config", type=Path, required=True)
    parser.add_argument("--medsiglip-config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--expected-case-count", type=int, default=335)
    args = parser.parse_args()
    try:
        context = verify_lld_mmri_v23_signal_context(
            protocol_root=args.protocol_root,
            panel_root=args.panels,
            gallery_root=args.gallery,
            review_path=args.review,
            prepared_root=args.prepared,
            medgemma_config_path=args.medgemma_config,
            medsiglip_config_path=args.medsiglip_config,
            expected_case_count=args.expected_case_count,
        )
        result = build_lld_mmri_v23_shape_branch(
            context=context,
            prepared_root=args.prepared,
            output_root=args.output,
            progress=lambda index, total, case_id, elapsed: print(
                json.dumps({"case": index, "total": total, "case_id": case_id, "elapsed_seconds": elapsed}, sort_keys=True),
                flush=True,
            ),
        )
    except PipelineError as exc:
        print(f"[ABORTADO] {exc}")
        return 1
    print(json.dumps(result, ensure_ascii=True, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
