"""CLI para gerar a coorte OpenSwissHCC remediada após triagem técnica."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from dtwin.benchmark.openswisshcc_remediation import build_remediated_candidates


def main() -> int:
    parser = argparse.ArgumentParser(description="Remedia candidatos sem acessar labels.")
    parser.add_argument("--source-panels", required=True, type=Path)
    parser.add_argument("--source-freeze", required=True, type=Path)
    parser.add_argument("--inputs", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--triage", required=True, type=Path)
    parser.add_argument(
        "--multiphase-config",
        type=Path,
        default=Path("configs/medgemma_local_4b_multiphase_fast_pathology.yaml"),
    )
    parser.add_argument(
        "--original-fallback-config",
        type=Path,
        default=Path("configs/medgemma_local_4b_venous_fallback_pathology.yaml"),
    )
    parser.add_argument(
        "--review-fallback-config",
        type=Path,
        default=Path("configs/medgemma_local_4b_venous_review_fallback_pathology.yaml"),
    )
    parser.add_argument("--profile", type=Path, default=Path("profiles/figado.yaml"))
    parser.add_argument("--expected-case-count", type=int, default=88)
    args = parser.parse_args()
    result = build_remediated_candidates(
        source_panel_root=args.source_panels,
        source_freeze_path=args.source_freeze,
        input_root=args.inputs,
        output_root=args.out,
        triage_path=args.triage,
        multiphase_config=args.multiphase_config,
        original_fallback_config=args.original_fallback_config,
        review_fallback_config=args.review_fallback_config,
        profile_path=args.profile,
        expected_case_count=args.expected_case_count,
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
