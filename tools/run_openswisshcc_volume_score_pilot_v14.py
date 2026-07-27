#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from dtwin.benchmark.openswisshcc_volume_score import run_volume_score_determinism_pilot
from dtwin.core import PipelineError


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Executa o piloto cego determinístico v14.")
    parser.add_argument("--bundle-root", required=True, type=Path)
    parser.add_argument("--protocol", required=True, type=Path)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument("--case-id")
    args = parser.parse_args(argv)
    try:
        result = run_volume_score_determinism_pilot(
            bundle_root=args.bundle_root,
            protocol_path=args.protocol,
            config_path=args.config,
            output_root=args.output_root,
            case_id=args.case_id,
        )
    except PipelineError as exc:
        print(f"[ABORTADO] {exc}", flush=True)
        return 1
    print(
        json.dumps(
            {
                "status": result["status"],
                "case_id": result["case_id"],
                "deterministic": result["deterministic"],
                "all_time_gates_passed": result["all_time_gates_passed"],
                "ground_truth_read": result["ground_truth_read"],
                "holdout_opened": result["holdout_opened"],
            },
            sort_keys=True,
        ),
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

