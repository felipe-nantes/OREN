"""Freeze, extract and run the authorized retrospective v16 localization audit."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from dtwin.benchmark.openswisshcc_candidate_localization_audit import (
    extract_authorized_venous_masks,
    freeze_protocol,
    run_audit,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    freeze = sub.add_parser("freeze")
    freeze.add_argument("--archive", type=Path, required=True)
    freeze.add_argument("--cohort-manifest", type=Path, required=True)
    freeze.add_argument("--scores-csv", type=Path, required=True)
    freeze.add_argument("--source-map", type=Path, required=True)
    freeze.add_argument("--input-manifest", type=Path, required=True)
    freeze.add_argument("--localizer-root", type=Path, required=True)
    freeze.add_argument("--out", type=Path, required=True)
    extract = sub.add_parser("extract")
    extract.add_argument("--archive", type=Path, required=True)
    extract.add_argument("--protocol", type=Path, required=True)
    extract.add_argument("--out", type=Path, required=True)
    audit = sub.add_parser("audit")
    audit.add_argument("--protocol", type=Path, required=True)
    audit.add_argument("--extraction-root", type=Path, required=True)
    audit.add_argument("--cohort-root", type=Path, required=True)
    audit.add_argument("--localizer-root", type=Path, required=True)
    audit.add_argument("--input-manifest", type=Path, required=True)
    audit.add_argument("--input-root", type=Path, required=True)
    audit.add_argument("--scores-csv", type=Path, required=True)
    audit.add_argument("--out", type=Path, required=True)
    return parser


def main() -> int:
    args = _parser().parse_args()
    if args.command == "freeze":
        result = freeze_protocol(
            archive_path=args.archive,
            cohort_manifest_path=args.cohort_manifest,
            scores_csv_path=args.scores_csv,
            source_map_path=args.source_map,
            input_manifest_path=args.input_manifest,
            localizer_root=args.localizer_root,
            output_path=args.out,
        )
    elif args.command == "extract":
        result = extract_authorized_venous_masks(
            archive_path=args.archive, protocol_path=args.protocol, output_root=args.out
        )
    else:
        result = run_audit(
            protocol_path=args.protocol,
            extraction_root=args.extraction_root,
            cohort_root=args.cohort_root,
            localizer_root=args.localizer_root,
            input_manifest_path=args.input_manifest,
            input_root=args.input_root,
            scores_csv_path=args.scores_csv,
            output_root=args.out,
        )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
