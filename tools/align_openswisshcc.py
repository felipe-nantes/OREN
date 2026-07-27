"""CLI do alinhamento T1 seguro do desenvolvimento OpenSwissHCC."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from dtwin.benchmark.openswisshcc_alignment import align_development_case


def main() -> int:
    parser = argparse.ArgumentParser(description="Alinha um caso OpenSwissHCC à fase venosa.")
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--inputs", required=True, type=Path)
    parser.add_argument("--transforms", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--minimum-dice", type=float, default=0.80)
    args = parser.parse_args()
    result = align_development_case(
        case_id=args.case_id,
        input_root=args.inputs,
        registration_root=args.transforms,
        output_root=args.out,
        minimum_dice=args.minimum_dice,
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

