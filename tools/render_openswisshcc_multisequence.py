"""Render one blind OpenSwissHCC T1/T2/TRACE/ADC 2x2 panel set."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from dtwin.benchmark.openswisshcc_multisequence_panel import (
    generate_multisequence_panel_set,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--inputs", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--tile-size", type=int, default=448)
    args = parser.parse_args()
    result = generate_multisequence_panel_set(
        case_id=args.case_id, input_root=args.inputs, manifest_path=args.manifest,
        output_root=args.out, tile_size=args.tile_size,
    )
    print(json.dumps({
        "case_id": result["case_id"], "panel_count": result["panel_count"],
        "trace_role": result["trace_role"], "t2_role": result["t2_role"],
        "coverage": result["coverage"], "ground_truth_read": result["ground_truth_read"],
        "lesion_mask_used": result["lesion_mask_used"],
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
