"""CLI para construir a galeria local de revisão visual OpenSwissHCC."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from dtwin.benchmark.openswisshcc_gallery import build_review_gallery


def main() -> int:
    parser = argparse.ArgumentParser(description="Constrói checklist visual local, sem aprovar inferência.")
    parser.add_argument("--panels", required=True, type=Path)
    parser.add_argument("--freeze", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument(
        "--multiphase-config",
        type=Path,
        default=Path("configs/medgemma_local_4b_multiphase_fast_pathology.yaml"),
    )
    parser.add_argument(
        "--fallback-config",
        type=Path,
        default=Path("configs/medgemma_local_4b_venous_fallback_pathology.yaml"),
    )
    parser.add_argument("--expected-case-count", type=int, default=88)
    args = parser.parse_args()
    result = build_review_gallery(
        panel_root=args.panels,
        freeze_path=args.freeze,
        output_dir=args.out,
        multiphase_config=args.multiphase_config,
        fallback_config=args.fallback_config,
        expected_case_count=args.expected_case_count,
    )
    print(
        json.dumps(
            {
                "case_count": result["case_count"],
                "experiment_signature": result["experiment_signature"],
                "authoritative_approval": result["authoritative_approval"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
