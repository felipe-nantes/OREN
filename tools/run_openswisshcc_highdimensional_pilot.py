#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from dtwin.benchmark.openswisshcc_highdimensional_inference import (
    run_highdimensional_pilot,
)
from dtwin.core import PipelineError


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Executa um piloto cego MedGemma high-dimensional.")
    parser.add_argument("--stack-dir", required=True, type=Path)
    parser.add_argument("--protocol", required=True, type=Path)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        result = run_highdimensional_pilot(
            stack_dir=args.stack_dir,
            protocol_path=args.protocol,
            config_path=args.config,
            out_path=args.out,
        )
    except PipelineError as exc:
        print(f"[ABORTADO] {exc}")
        return 1
    print(json.dumps({
        "status": result["status"],
        "classification": result["classification"],
        "request_elapsed_seconds": result["request_elapsed_seconds"],
        "time_gate_passed": result["time_gate_passed"],
        "holdout_opened": result["holdout_opened"],
    }, sort_keys=True))
    return 0 if result["status"] == "technical_passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
