"""Audit blind OpenSwissHCC ADC/high-b DWI/T2 geometry and availability."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from dtwin.benchmark.openswisshcc_multisequence_audit import audit_multisequence_inputs


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--expected-case-count", type=int, default=88)
    args = parser.parse_args()
    result = audit_multisequence_inputs(
        input_root=args.inputs, manifest_path=args.manifest,
        output_path=args.out, expected_case_count=args.expected_case_count,
    )
    print(json.dumps({key: result[key] for key in (
        "status", "case_count", "availability", "physical_fov_inside_fraction",
        "orientation_same_axis_abs_cosine", "trace_order_support", "ground_truth_read",
    )}, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
