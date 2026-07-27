#!/usr/bin/env python3
"""Align all prepared OpenSwissHCC holdout cases without opening labels."""
from __future__ import annotations

import argparse
import json
import os
import uuid
from pathlib import Path

from dtwin.benchmark.openswisshcc_alignment import (
    AlignmentGateError,
    _sha256,
    align_holdout_case_label_blind,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs", required=True, type=Path)
    parser.add_argument("--transforms", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--summary", required=True, type=Path)
    parser.add_argument("--minimum-dice", type=float, default=0.80)
    parser.add_argument("--allow-technical-fallback", action="store_true")
    args = parser.parse_args(argv)
    rows = [
        json.loads(line)
        for line in (args.inputs / "manifests" / "holdout_inputs.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if line.strip()
    ]
    results = []
    fallbacks = []
    for index, row in enumerate(rows, start=1):
        case_id = str(row["case_id"])
        try:
            result = align_holdout_case_label_blind(
                case_id=case_id,
                input_root=args.inputs,
                registration_root=args.transforms,
                output_root=args.out,
                minimum_dice=args.minimum_dice,
            )
        except AlignmentGateError:
            if not args.allow_technical_fallback:
                raise
            fallback = {
                "case_id": case_id,
                "reason": "alignment_gate_below_frozen_minimum",
                "fallback": "venous_single_phase",
            }
            fallbacks.append(fallback)
            print(
                json.dumps(
                    {"case": index, "total": len(rows), "status": "technical_fallback", **fallback},
                    ensure_ascii=False,
                ),
                flush=True,
            )
            continue
        results.append(result)
        print(
            json.dumps(
                {
                    "case": index,
                    "total": len(rows),
                    "case_id": case_id,
                    "cache_reused": result["cache_reused"],
                    "elapsed_seconds": result["elapsed_seconds"],
                },
                ensure_ascii=False,
            ),
            flush=True,
        )
    if len(results) + len(fallbacks) != len(rows):
        raise RuntimeError("Alignment accounting is incomplete")
    manifests = []
    for result in results:
        case_id = str(result["case_id"])
        path = args.out / case_id / "alignment_manifest.json"
        manifests.append({"case_id": case_id, "sha256": _sha256(path)})
    summary = {
        "schema": "argos-openswisshcc-holdout-alignment-summary-v1",
        "status": "complete_label_blind_alignment_with_declared_fallbacks",
        "case_count": len(rows),
        "aligned_case_count": len(results),
        "venous_fallback_case_count": len(fallbacks),
        "minimum_dice": args.minimum_dice,
        "alignments": manifests,
        "technical_fallbacks": fallbacks,
        "input_manifest_sha256": _sha256(
            args.inputs / "manifests" / "holdout_inputs.jsonl"
        ),
        "registration_manifest_sha256": _sha256(
            args.transforms / "registration_manifest.json"
        ),
        "holdout_images_prepared": True,
        "holdout_ground_truth_opened": False,
        "labels_read": False,
        "lesion_masks_read": 0,
        "research_only": True,
        "clinical_use_allowed": False,
        "requires_human_review": True,
    }
    if args.summary.exists():
        raise RuntimeError(f"Refusing to overwrite summary: {args.summary}")
    args.summary.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.summary.with_name(f".{args.summary.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_text(
            json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, args.summary)
    finally:
        temporary.unlink(missing_ok=True)
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
