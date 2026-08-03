#!/usr/bin/env python3
"""Build a nonclinical 330-case multiphase liver MRI stress cohort."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from huggingface_hub import hf_hub_download

from dtwin.benchmark.synthetic_external_stress_v1 import (
    ALGORITHM_ID,
    DEFAULT_TARGETS,
    build_donor_library,
    build_plan,
    download_required_masks,
    generate_case,
    list_nih_cases,
    load_lld_class_cases,
    write_cohort_manifest,
)
from dtwin.core import PipelineError, sha256_of


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--nih-root", type=Path, required=True)
    parser.add_argument("--lld-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=20260731)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--skip-download", action="store_true")
    parser.add_argument("--plan-only", action="store_true")
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    try:
        output_nonempty = args.output.exists() and any(args.output.iterdir())
        if output_nonempty and not args.resume:
            raise PipelineError(f"refusing nonempty output directory: {args.output}")
        args.output.mkdir(parents=True, exist_ok=True)
        annotation_path = args.lld_root / "LLD_MMRI_Annotation.json"
        plan = build_plan(
            nih_cases=list_nih_cases(args.nih_root),
            lld_cases=load_lld_class_cases(annotation_path),
            seed=args.seed,
            targets=DEFAULT_TARGETS,
        )
        if args.limit is not None:
            if args.limit < 1:
                raise PipelineError("limit must be positive")
            plan = plan[: args.limit]
        plan_path = args.output / "plan.json"
        if output_nonempty:
            if not plan_path.is_file() or json.loads(plan_path.read_text(encoding="utf-8")) != plan:
                raise PipelineError("resume plan does not match the existing frozen plan")
        else:
            plan_path.write_text(
                json.dumps(plan, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
        print(json.dumps({"status": "plan_frozen", "cases": len(plan)}), flush=True)
        if args.plan_only:
            return 0
        if not args.skip_download:
            masks = download_required_masks(
                plan=plan,
                lld_root=args.lld_root,
                downloader=hf_hub_download,
                workers=args.workers,
            )
            print(json.dumps({"status": "masks_ready", "files": len(masks)}), flush=True)
        donor_library = build_donor_library(plan, args.lld_root)
        (args.output / "donor_library.json").write_text(
            json.dumps(donor_library, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        for index, row in enumerate(plan, start=1):
            case_manifest = args.output / "cases" / str(row["case_id"]) / "case_manifest.json"
            if case_manifest.is_file():
                existing = json.loads(case_manifest.read_text(encoding="utf-8"))
                if (
                    existing.get("plan_signature") != row["plan_signature"]
                    or existing.get("synthesis_algorithm") != ALGORITHM_ID
                ):
                    raise PipelineError(f"existing case is from another plan/algorithm: {row['case_id']}")
                artifacts = list(existing["phases"].values())
                artifacts += list(existing["liver_masks"].values())
                artifacts += list(existing["lesion_masks"].values())
                for artifact in artifacts:
                    path = args.output / artifact["relative_path"]
                    if not path.is_file() or sha256_of(path) != artifact["sha256"]:
                        raise PipelineError(f"existing case is incomplete or tampered: {row['case_id']}")
                print(
                    json.dumps(
                        {"status": "case_reused", "index": index, "total": len(plan), "case_id": row["case_id"]}
                    ),
                    flush=True,
                )
                continue
            generate_case(
                row=row,
                nih_root=args.nih_root,
                donor_library=donor_library,
                output_root=args.output,
            )
            print(
                json.dumps(
                    {"status": "case_written", "index": index, "total": len(plan), "case_id": row["case_id"]}
                ),
                flush=True,
            )
        cohort = write_cohort_manifest(
            output_root=args.output,
            plan=plan,
            donor_library=donor_library,
        )
        print(json.dumps({"status": "complete", **cohort}, sort_keys=True))
        return 0
    except (PipelineError, OSError, ValueError, RuntimeError) as exc:
        print(f"[ABORTED] {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
