#!/usr/bin/env python3
"""Audit a prepared OpenSwissHCC holdout without reading ground truth."""
from __future__ import annotations

import argparse
import json
import os
import uuid
from pathlib import Path

from dtwin.benchmark.openswisshcc_holdout import audit_prepared_holdout_label_blind


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepared", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    result = audit_prepared_holdout_label_blind(args.prepared)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.out.with_name(f".{args.out.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_text(
            json.dumps(result, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, args.out)
    finally:
        temporary.unlink(missing_ok=True)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
