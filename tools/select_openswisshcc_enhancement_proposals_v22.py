#!/usr/bin/env python3
"""Select blind t3 top-5 enhancement proposals as a compatible localizer run."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from dtwin.benchmark.openswisshcc_enhancement_proposal_selection import (
    build_selected_enhancement_localizer,
)
from dtwin.core import PipelineError


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--proposal-root", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--inputs-root", type=Path, required=True)
    parser.add_argument("--selection-manifest", type=Path, required=True)
    parser.add_argument("--venous-fallback-localizer-root", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = build_selected_enhancement_localizer(
            proposal_root=args.proposal_root,
            input_manifest_path=args.manifest,
            input_root=args.inputs_root,
            selection_manifest_path=args.selection_manifest,
            venous_fallback_localizer_root=args.venous_fallback_localizer_root,
            output_root=args.out,
        )
    except PipelineError as exc:
        print(f"[ABORTADO] {exc}")
        return 1
    print(json.dumps(result, ensure_ascii=True, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
