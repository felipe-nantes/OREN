"""CLI for the retrospective development-only v22 enhancement audit."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from dtwin.benchmark.openswisshcc_enhancement_localizer_audit import (
    audit_enhancement_localizer,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--proposal-root", type=Path, required=True)
    parser.add_argument("--labels", type=Path, required=True)
    parser.add_argument("--authorized-extraction-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--expected-case-count", type=int, default=87)
    args = parser.parse_args()
    result = audit_enhancement_localizer(
        proposal_root=args.proposal_root,
        labels_path=args.labels,
        authorized_extraction_root=args.authorized_extraction_root,
        output_root=args.output_root,
        expected_case_count=args.expected_case_count,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
