#!/usr/bin/env python3
"""Prepare the public Gd-EOB HBP cohort without reading labels or masks."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from urllib.request import urlopen

from dtwin.benchmark.gd_eob_hcc_external import (
    ZENODO_API_URL,
    build_label_blind_readiness,
    extract_label_blind_images,
    freeze_hcc_hbp_contract,
    inventory_archive,
    validate_zenodo_metadata,
    verify_label_blind_images,
)
from dtwin.core import PipelineError


def _common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--baseline-lock",
        type=Path,
        default=Path("configs/benchmark/openswisshcc_v23_baseline_lock_v1.json"),
    )
    parser.add_argument("--workspace", type=Path, default=Path("."))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    freeze = commands.add_parser("freeze-contract")
    _common(freeze)
    freeze.add_argument("--out", type=Path, required=True)

    metadata = commands.add_parser("verify-metadata")
    metadata.add_argument("--metadata-json", type=Path)

    inventory = commands.add_parser("inventory-archive")
    inventory.add_argument("--archive", type=Path, required=True)
    inventory.add_argument("--out", type=Path)

    extract = commands.add_parser("extract-image-only")
    _common(extract)
    extract.add_argument("--contract", type=Path, required=True)
    extract.add_argument("--archive", type=Path, required=True)
    extract.add_argument("--out", type=Path, required=True)

    verify = commands.add_parser("verify-image-only")
    _common(verify)
    verify.add_argument("--contract", type=Path, required=True)
    verify.add_argument("--image-root", type=Path, required=True)

    ready = commands.add_parser("freeze-pilot-readiness")
    _common(ready)
    ready.add_argument("--contract", type=Path, required=True)
    ready.add_argument("--image-root", type=Path, required=True)
    ready.add_argument("--out", type=Path, required=True)

    args = parser.parse_args()
    try:
        if args.command == "freeze-contract":
            result = freeze_hcc_hbp_contract(
                baseline_lock_path=args.baseline_lock,
                workspace_root=args.workspace,
                output_path=args.out,
            )
        elif args.command == "verify-metadata":
            if args.metadata_json:
                payload = json.loads(args.metadata_json.read_text(encoding="utf-8"))
            else:
                with urlopen(ZENODO_API_URL, timeout=30) as response:
                    payload = json.load(response)
            result = validate_zenodo_metadata(payload)
        elif args.command == "inventory-archive":
            result = inventory_archive(args.archive)
            if args.out:
                args.out.parent.mkdir(parents=True, exist_ok=True)
                args.out.write_text(
                    json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True)
                    + "\n",
                    encoding="utf-8",
                )
        elif args.command == "extract-image-only":
            result = extract_label_blind_images(
                archive_path=args.archive,
                contract_path=args.contract,
                baseline_lock_path=args.baseline_lock,
                workspace_root=args.workspace,
                output_root=args.out,
                progress=lambda index, total, case_id: print(
                    json.dumps(
                        {"extracted_cases": index, "total_cases": total, "case_id": case_id},
                        sort_keys=True,
                    ),
                    flush=True,
                ),
            )
        elif args.command == "verify-image-only":
            result = verify_label_blind_images(
                image_root=args.image_root,
                contract_path=args.contract,
                baseline_lock_path=args.baseline_lock,
                workspace_root=args.workspace,
            )
        else:
            result = build_label_blind_readiness(
                image_root=args.image_root,
                contract_path=args.contract,
                baseline_lock_path=args.baseline_lock,
                workspace_root=args.workspace,
                output_path=args.out,
            )
    except (PipelineError, OSError, json.JSONDecodeError) as exc:
        print(f"[ABORTADO] {exc}")
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
