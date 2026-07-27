"""Freeze or independently verify the ARGOS hybrid-v1 research protocol."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from dtwin.learning.protocol import freeze_protocol, verify_protocol


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("freeze", "verify"))
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("configs/training/hybrid_v1_protocol.yaml"),
    )
    parser.add_argument(
        "--protocol",
        type=Path,
        default=Path("configs/training/hybrid_v1_protocol.lock.json"),
    )
    parser.add_argument(
        "--splits",
        type=Path,
        default=Path("configs/training/hybrid_v1_nested_splits.json"),
    )
    parser.add_argument("--workspace-root", type=Path, default=Path.cwd())
    return parser


def main() -> int:
    args = _parser().parse_args()
    kwargs = {
        "config_path": args.config,
        "workspace_root": args.workspace_root,
        "protocol_path": args.protocol,
        "splits_path": args.splits,
    }
    result = (
        freeze_protocol(**kwargs)
        if args.command == "freeze"
        else verify_protocol(**kwargs)
    )
    print(
        json.dumps(
            {
                "status": "ok",
                "protocol_signature": result["protocol_signature"],
                "aggregate_case_count": result["aggregate_case_count"],
                "aggregate_label_counts": result["aggregate_label_counts"],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
