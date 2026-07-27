#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from dtwin.benchmark.openswisshcc_v11_v13_complementarity import (
    analyze_v11_v13_complementarity,
)
from dtwin.core import PipelineError


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Tabela cruzada exploratória das decisões v11 e v13."
    )
    parser.add_argument("--v11-bundle-root", required=True, type=Path)
    parser.add_argument("--v11-protocol", required=True, type=Path)
    parser.add_argument("--v13-cases", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        result = analyze_v11_v13_complementarity(
            v11_bundle_root=args.v11_bundle_root,
            v11_protocol_path=args.v11_protocol,
            v13_cases_path=args.v13_cases,
        )
    except PipelineError as exc:
        print(f"[ABORTADO] {exc}", flush=True)
        return 1
    table: dict[str, dict[str, int]] = {}
    for row in result["case_rows"]:
        key = f"v11_{row['v11_loocv_prediction']}__v13_{row['v13_prediction']}"
        group = "positive" if row["truth"] == "POSITIVE" else "negative"
        entry = table.setdefault(key, {"positive": 0, "negative": 0, "total": 0})
        entry[group] += 1
        entry["total"] += 1
    print(json.dumps({
        "schema": "argos-openswisshcc-v11-v13-cross-tab-v1",
        "status": "development_exploratory_only",
        "decision_cross_tab": dict(sorted(table.items())),
        "rule_selected": False,
        "holdout_opened": False,
    }, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

