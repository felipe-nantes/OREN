"""Merge all validated OpenSwissHCC v10 lesion-localizer chunks."""
import argparse
import json
from pathlib import Path

from dtwin.benchmark.openswisshcc_lesion_localizer_chunks import merge_localizer_chunks


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--chunks", type=Path, required=True)
    parser.add_argument("--selection-plan", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--expected-case-count", type=int, default=87)
    args = parser.parse_args()
    result = merge_localizer_chunks(
        chunks_root=args.chunks,
        selection_plan_path=args.selection_plan,
        output_root=args.out,
        expected_case_count=args.expected_case_count,
    )
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
