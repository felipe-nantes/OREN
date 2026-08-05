#!/usr/bin/env python3
"""Run the non-decisional delayed MedSigLIP reader on a prepared research case."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from webapp.server import _run_delayed_medsiglip_advisory


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--case-dir",
        required=True,
        type=Path,
        help="Prepared case containing volume.nii.gz and mask_organ.nii.gz.",
    )
    parser.add_argument("--case-id", default="anon-monophase-advisory-smoke")
    parser.add_argument(
        "--primary-prediction",
        choices=("POSITIVA", "NEGATIVA", "INCONCLUSIVA"),
        default="INCONCLUSIVA",
    )
    args = parser.parse_args()
    result = _run_delayed_medsiglip_advisory(
        case_dir=args.case_dir.resolve(),
        case_id=args.case_id,
        input_assessment={
            "mode": "single_phase",
            "monophase_sequence_contract": {
                "source_phase_key": "t1_delayed",
                "sequence_specific_medsiglip_bundle_allowed": True,
            },
        },
        primary_prediction=args.primary_prediction,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result.get("status") == "completed" else 2


if __name__ == "__main__":
    raise SystemExit(main())

