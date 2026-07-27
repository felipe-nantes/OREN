#!/usr/bin/env python3
"""Verify the frozen, development-only OpenSwissHCC v23 baseline."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from dtwin.benchmark.openswisshcc_v23_baseline import verify_v23_baseline_lock
from dtwin.core import PipelineError


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--lock",
        type=Path,
        default=Path("configs/benchmark/openswisshcc_v23_baseline_lock_v1.json"),
    )
    parser.add_argument("--workspace", type=Path, default=Path("."))
    args = parser.parse_args()
    try:
        result = verify_v23_baseline_lock(
            lock_path=args.lock,
            workspace_root=args.workspace,
        )
    except PipelineError as exc:
        print(f"[ABORTADO] {exc}")
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
