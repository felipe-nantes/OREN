"""CLI para finalizar uma variante técnica aprovada na coorte OpenSwissHCC."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from dtwin.benchmark.openswisshcc_finalize import finalize_candidate_variant


def main() -> int:
    parser = argparse.ArgumentParser(description="Finaliza uma variante sem acessar labels.")
    parser.add_argument("--source-panels", required=True, type=Path)
    parser.add_argument("--source-freeze", required=True, type=Path)
    parser.add_argument("--replacement-root", required=True, type=Path)
    parser.add_argument("--replacement-case-id", required=True)
    parser.add_argument("--replacement-config", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--multiphase-config", required=True, type=Path)
    parser.add_argument("--fallback-config", required=True, type=Path)
    parser.add_argument("--expected-case-count", type=int, default=88)
    args = parser.parse_args()
    result = finalize_candidate_variant(
        source_panel_root=args.source_panels,
        source_freeze_path=args.source_freeze,
        replacement_root=args.replacement_root,
        replacement_case_id=args.replacement_case_id,
        replacement_config=args.replacement_config,
        output_root=args.out,
        multiphase_config=args.multiphase_config,
        fallback_config=args.fallback_config,
        expected_case_count=args.expected_case_count,
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
