from __future__ import annotations

import argparse
import json
from pathlib import Path

from dtwin.benchmark.openswisshcc_candidate_volume_score import (
    freeze_candidate_volume_score_protocol,
)
from dtwin.core import PipelineError


def main() -> int:
    parser = argparse.ArgumentParser(description="Congela o scorer focal cego OpenSwissHCC v16.")
    parser.add_argument("--bundle-root", required=True, type=Path)
    parser.add_argument("--review", required=True, type=Path)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    try:
        result = freeze_candidate_volume_score_protocol(bundle_root=args.bundle_root, review_path=args.review, config_path=args.config, out_path=args.out)
    except PipelineError as exc:
        print(f"[ABORTADO] {exc}")
        return 1
    print(json.dumps({"status": result["status"], "protocol_signature": result["protocol_signature"], "case_count": result["case_count"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

