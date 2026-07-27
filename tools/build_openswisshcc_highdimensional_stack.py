#!/usr/bin/env python3
"""Constrói uma pilha MRI cega para o endpoint volumétrico do MedGemma."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from dtwin.benchmark.openswisshcc_highdimensional import build_highdimensional_stack
from dtwin.core import PipelineError


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Prepara 5–85 cortes axiais anônimos para MedGemma 1.5 high-dimensional."
    )
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--input-root", required=True, type=Path)
    parser.add_argument("--out-root", required=True, type=Path)
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--max-slices", type=int, default=85)
    args = parser.parse_args(argv)
    try:
        result = build_highdimensional_stack(
            manifest_path=args.manifest,
            input_root=args.input_root,
            out_root=args.out_root,
            case_id=args.case_id,
            maximum_slices=args.max_slices,
        )
    except PipelineError as exc:
        print(f"[ABORTADO] {exc}")
        return 1
    print(
        json.dumps(
            {
                "case_id": result["case_id"],
                "slice_count": result["slice_count"],
                "coverage_fraction": result["liver_mask_audit"]["coverage_fraction"],
                "gate_passed": result["gate"]["passed"],
                "research_only": result["research_only"],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
