#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from dtwin.benchmark.openswisshcc_highdimensional_inference import (
    freeze_highdimensional_protocol,
)
from dtwin.core import PipelineError


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Congela o piloto MedGemma high-dimensional.")
    parser.add_argument("--stack-dir", required=True, type=Path)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        protocol = freeze_highdimensional_protocol(
            stack_dir=args.stack_dir,
            config_path=args.config,
            out_path=args.out,
        )
    except PipelineError as exc:
        print(f"[ABORTADO] {exc}")
        return 1
    print(json.dumps({
        "case_id": protocol["case_id"],
        "slice_count": protocol["slice_count"],
        "protocol_signature": protocol["protocol_signature"],
        "holdout_opened": protocol["holdout_opened"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
