"""Create the label-blind TCGA raw-DICOM phase review gallery."""
from __future__ import annotations

import argparse
from pathlib import Path

import yaml

from dtwin.learning.raw_phase_review import build_raw_phase_review_gallery


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--labels", type=Path, required=True, help="YAML used only to project case_id + inference.dicom_dir")
    parser.add_argument("--source-root", action="append", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    payload = yaml.safe_load(args.labels.read_text(encoding="utf-8")) or {}
    # Deliberately discard every protected field before entering the gallery builder.
    cases = [
        {"case_id": str(item["case_id"]), "source_name": str(item["inference"]["dicom_dir"])}
        for item in payload.get("cases", [])
    ]
    result = build_raw_phase_review_gallery(
        cases=cases, source_roots=args.source_root, output_dir=args.out
    )
    print(f"Galeria: {args.out.resolve()}")
    print(f"Elegíveis: {result['eligible_cases']}/{result['requested_cases']}")
    print(f"Assinatura: {result['protocol_signature']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
