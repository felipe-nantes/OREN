"""Print a read-only preflight report for the hybrid training environment."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from dtwin.learning.environment import (
    build_environment_report,
    require_training_ready,
)
from dtwin.learning.protocol import atomic_write_json


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace-root", type=Path, default=Path.cwd())
    parser.add_argument("--out", type=Path)
    parser.add_argument("--require-training-ready", action="store_true")
    args = parser.parse_args()
    report = build_environment_report(args.workspace_root)
    if args.out:
        atomic_write_json(args.out, report)
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    if args.require_training_ready:
        require_training_ready(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
