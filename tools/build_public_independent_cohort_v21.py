"""Build the label-isolated v21 public independent cohort."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from dtwin.benchmark.public_independent_cohort import (
    build_public_independent_cohort,
    load_public_cohort_config,
    verify_public_independent_cohort,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--verify-only", action="store_true")
    parser.add_argument("--expected-signature")
    parser.add_argument("--skip-source-rehash", action="store_true")
    args = parser.parse_args(argv)
    cohort_id, sources, minimums = load_public_cohort_config(args.config)
    if args.verify_only:
        result = verify_public_independent_cohort(
            bundle_dir=args.out,
            sources=sources,
            expected_protocol_signature=args.expected_signature,
            recompute_source_hashes=not args.skip_source_rehash,
        )
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0
    result = build_public_independent_cohort(
        cohort_id=cohort_id,
        sources=sources,
        output_dir=args.out,
        minimum_subjects_per_role=minimums,
    )
    print(json.dumps({
        "cohort_id": result["cohort_id"],
        "case_count": result["case_count"],
        "role_counts": result["role_counts"],
        "domain_confounding": result["domain_confounding"],
        "protocol_signature": result["protocol_signature"],
        "holdout_opened": result["holdout_opened"],
    }, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
