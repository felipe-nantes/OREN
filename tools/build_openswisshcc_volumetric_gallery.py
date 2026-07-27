"""Build a local review gallery for all OpenSwissHCC volumetric panels."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from dtwin.benchmark.openswisshcc_volumetric_gallery import (
    build_volumetric_review_gallery,
)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--panels", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--expected-case-count", type=int, default=88)
    args = parser.parse_args(argv)
    result = build_volumetric_review_gallery(
        panel_root=args.panels,
        output_dir=args.out,
        expected_case_count=args.expected_case_count,
    )
    print(json.dumps({
        "case_count": result["case_count"],
        "panel_image_count": result["panel_image_count"],
        "gallery_signature": result["gallery_signature"],
        "authoritative_approval": False,
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

