"""CLI da rodada sequencial MedGemma 4B sobre OpenSwissHCC revisado."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from dtwin.benchmark.openswisshcc_configs import parse_extra_configs
from dtwin.benchmark.openswisshcc_inference_batch import run_reviewed_inference_batch


def main() -> int:
    parser = argparse.ArgumentParser(description="Executa o lote OpenSwissHCC revisado.")
    parser.add_argument("--panels", required=True, type=Path)
    parser.add_argument("--review", required=True, type=Path)
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
    parser.add_argument("--case-id", action="append")
    parser.add_argument("--extra-config", action="append", default=[])
    parser.add_argument("--expected-case-count", type=int, default=88)
    parser.add_argument("--case-timeout-seconds", type=float, default=180.0)
    args = parser.parse_args()
    additional_configs = parse_extra_configs(args.extra_config)
    summary = run_reviewed_inference_batch(
        panel_root=args.panels,
        review_path=args.review,
        freeze_path=args.freeze,
        output_root=args.out,
        multiphase_config=args.multiphase_config,
        fallback_config=args.fallback_config,
        additional_configs=additional_configs,
        case_ids=args.case_id,
        expected_case_count=args.expected_case_count,
        case_timeout_seconds=args.case_timeout_seconds,
    )
    print(json.dumps({"status_counts": summary["status_counts"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
