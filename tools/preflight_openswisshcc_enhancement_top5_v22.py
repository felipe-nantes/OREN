"""Validate the v22 exact-top5 pilot before human review and inference."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from dtwin.benchmark.openswisshcc_enhancement_score_preflight import (
    write_enhancement_top5_preflight,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bundle-root", type=Path, required=True)
    parser.add_argument("--localizer-root", type=Path, required=True)
    parser.add_argument("--audit", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    result = write_enhancement_top5_preflight(
        bundle_root=args.bundle_root,
        localizer_root=args.localizer_root,
        audit_path=args.audit,
        output_path=args.out,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
