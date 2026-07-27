"""Create the protected LiverHccSeg tumor-positive registry for v21."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from dtwin.datasets.liverhccseg_labels import filter_liverhccseg_tumor_positive_registry


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--registry", type=Path, required=True)
    parser.add_argument("--metadata", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--audit", type=Path, required=True)
    args = parser.parse_args(argv)
    result = filter_liverhccseg_tumor_positive_registry(
        registry_path=args.registry,
        metadata_path=args.metadata,
        output_registry_path=args.out,
        protected_audit_path=args.audit,
    )
    print(json.dumps({
        "status": result["status"],
        "documented_subject_count": result["documented_subject_count"],
        "included_tumor_subject_count": result["included_tumor_subject_count"],
        "excluded_non_tumor_subject_count": result["excluded_non_tumor_subject_count"],
        "excluded_subjects_not_assumed_negative": result["excluded_subjects_not_assumed_negative"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

