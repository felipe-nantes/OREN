"""Executa um caso OpenSwissHCC já aprovado e pertencente ao experimento congelado."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from dtwin.benchmark.openswisshcc_configs import parse_extra_configs
from dtwin.benchmark.openswisshcc_freeze import verify_experiment_freeze
from dtwin.benchmark.openswisshcc_inference import infer_reviewed_candidate


def main() -> int:
    parser = argparse.ArgumentParser(description="Infere um candidato OpenSwissHCC revisado.")
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--panels", required=True, type=Path)
    parser.add_argument("--review", required=True, type=Path)
    parser.add_argument("--freeze", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--config", required=True, type=Path)
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
    parser.add_argument("--extra-config", action="append", default=[])
    parser.add_argument("--max-case-seconds", type=float, default=180.0)
    args = parser.parse_args()
    additional_configs = parse_extra_configs(args.extra_config)
    verify_experiment_freeze(
        freeze_path=args.freeze,
        panel_root=args.panels,
        multiphase_config=args.multiphase_config,
        fallback_config=args.fallback_config,
        expected_case_count=args.expected_case_count,
        additional_configs=additional_configs,
    )
    result = infer_reviewed_candidate(
        case_id=args.case_id,
        panel_root=args.panels,
        review_path=args.review,
        output_root=args.out,
        config_path=args.config,
        max_case_seconds=args.max_case_seconds,
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
