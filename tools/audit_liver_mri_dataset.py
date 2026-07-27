#!/usr/bin/env python3
"""CLI para auditoria técnica segura dos lotes DICOM hepáticos."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from dtwin.benchmark.dataset_audit import audit_dataset_roots


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Audita séries DICOM positivas/negativas sem persistir PHI ou UIDs brutos."
    )
    parser.add_argument("--positive-root", type=Path, required=True)
    parser.add_argument("--negative-root", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    result = audit_dataset_roots(
        {"positive": args.positive_root, "negative": args.negative_root}
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.out.with_name(f".{args.out.name}.tmp")
    temporary.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    temporary.replace(args.out)
    print(
        json.dumps(
            {
                "schema": result["schema"],
                "case_count": result["case_count"],
                "label_counts": result["label_counts"],
                "warnings": result["warnings"],
                "output": str(args.out),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

