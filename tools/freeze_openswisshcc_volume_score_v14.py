#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from dtwin.benchmark.openswisshcc_volume_score import freeze_volume_score_protocol
from dtwin.core import PipelineError


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Congela o protocolo cego v14 antes da pontuação.")
    parser.add_argument("--bundle-root", required=True, type=Path)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        protocol = freeze_volume_score_protocol(
            bundle_root=args.bundle_root,
            config_path=args.config,
            out_path=args.out,
        )
    except PipelineError as exc:
        print(f"[ABORTADO] {exc}", flush=True)
        return 1
    print(
        json.dumps(
            {
                "protocol_signature": protocol["protocol_signature"],
                "case_count": protocol["case_count"],
                "contract": protocol["contract"],
                "ground_truth_read": protocol["ground_truth_read"],
                "holdout_opened": protocol["holdout_opened"],
            },
            sort_keys=True,
        ),
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

