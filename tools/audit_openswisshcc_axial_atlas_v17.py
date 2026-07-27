#!/usr/bin/env python
"""Congela ou executa a auditoria retrospectiva do atlas axial v17."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from dtwin.benchmark.openswisshcc_axial_atlas_audit import freeze_protocol, run_audit
from dtwin.core import PipelineError


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    freeze = commands.add_parser("freeze")
    freeze.add_argument("--atlas-root", type=Path, required=True)
    freeze.add_argument("--source-panel-root", type=Path, required=True)
    freeze.add_argument("--input-manifest", type=Path, required=True)
    freeze.add_argument("--input-root", type=Path, required=True)
    freeze.add_argument("--out", type=Path, required=True)
    audit = commands.add_parser("audit")
    audit.add_argument("--protocol", type=Path, required=True)
    audit.add_argument("--authorized-mask-root", type=Path, required=True)
    audit.add_argument("--extraction-manifest", type=Path, required=True)
    audit.add_argument("--input-root", type=Path, required=True)
    audit.add_argument("--out", type=Path, required=True)
    return parser


def main() -> int:
    args = _parser().parse_args()
    try:
        if args.command == "freeze":
            result = freeze_protocol(
                atlas_root=args.atlas_root,
                source_panel_root=args.source_panel_root,
                input_manifest_path=args.input_manifest,
                input_root=args.input_root,
                output_path=args.out,
            )
        else:
            result = run_audit(
                protocol_path=args.protocol,
                authorized_mask_root=args.authorized_mask_root,
                extraction_manifest_path=args.extraction_manifest,
                input_root=args.input_root,
                output_root=args.out,
            )
    except PipelineError as exc:
        print(f"[ABORTADO] {exc}")
        return 1
    summary = result.get("summary")
    print(
        json.dumps(
            {
                "schema_version": result["schema_version"],
                "protocol_signature": result["protocol_signature"],
                "summary": summary,
                "safety": result.get("safety"),
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
