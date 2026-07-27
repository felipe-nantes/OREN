#!/usr/bin/env python3
"""Freeze, run, verify and render the label-blind Gd-EOB HBP pilot."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from dtwin.benchmark.gd_eob_hbp_pilot import (
    build_hbp_pilot_gallery,
    freeze_hbp_pilot_protocol,
    run_hbp_pilot,
    verify_hbp_pilot_run,
)
from dtwin.core import PipelineError


def _common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--readiness",
        type=Path,
        default=Path(
            "casos/qualification/gd_eob_hcc_external_v1/"
            "technical_pilot_readiness_v1.json"
        ),
    )
    parser.add_argument(
        "--image-root",
        type=Path,
        default=Path(
            "casos/qualification/gd_eob_hcc_external_v1/"
            "acquisition_v1/image_only"
        ),
    )
    parser.add_argument(
        "--contract",
        type=Path,
        default=Path("configs/benchmark/v23_external_hcc_hbp_contract_v1.json"),
    )
    parser.add_argument(
        "--baseline-lock",
        type=Path,
        default=Path("configs/benchmark/openswisshcc_v23_baseline_lock_v1.json"),
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path(
            "configs/medgemma_local_4b_gd_eob_hbp_liver_enriched_pilot.yaml"
        ),
    )
    parser.add_argument("--workspace", type=Path, default=Path("."))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    freeze = commands.add_parser("freeze")
    _common(freeze)
    freeze.add_argument("--out", type=Path, required=True)
    run = commands.add_parser("run")
    _common(run)
    run.add_argument("--protocol", type=Path, required=True)
    run.add_argument("--out", type=Path, required=True)
    verify = commands.add_parser("verify")
    _common(verify)
    verify.add_argument("--protocol", type=Path, required=True)
    verify.add_argument("--run-root", type=Path, required=True)
    gallery = commands.add_parser("gallery")
    gallery.add_argument("--run-root", type=Path, required=True)
    gallery.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == "freeze":
            result = freeze_hbp_pilot_protocol(
                readiness_path=args.readiness,
                image_root=args.image_root,
                contract_path=args.contract,
                baseline_lock_path=args.baseline_lock,
                workspace_root=args.workspace,
                config_path=args.config,
                output_path=args.out,
            )
        elif args.command == "run":
            result = run_hbp_pilot(
                protocol_path=args.protocol,
                readiness_path=args.readiness,
                image_root=args.image_root,
                contract_path=args.contract,
                baseline_lock_path=args.baseline_lock,
                workspace_root=args.workspace,
                config_path=args.config,
                output_root=args.out,
                progress=lambda index, total, case_id: print(
                    json.dumps(
                        {"case": index, "total": total, "case_id": case_id},
                        sort_keys=True,
                    ),
                    flush=True,
                ),
            )
        elif args.command == "verify":
            result = verify_hbp_pilot_run(
                run_root=args.run_root,
                protocol_path=args.protocol,
                readiness_path=args.readiness,
                image_root=args.image_root,
                contract_path=args.contract,
                baseline_lock_path=args.baseline_lock,
                workspace_root=args.workspace,
                config_path=args.config,
            )
        else:
            result = build_hbp_pilot_gallery(
                run_root=args.run_root,
                output_root=args.out,
            )
    except (PipelineError, OSError) as exc:
        print(f"[ABORTADO] {exc}")
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
