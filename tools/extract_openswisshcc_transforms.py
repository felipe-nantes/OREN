"""CLI para extrair somente transforms T1 permitidos do desenvolvimento."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from dtwin.benchmark.openswisshcc_registration import (
    extract_development_registration_transforms,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Extrai transforms T1 OpenSwissHCC sem anotações de lesão."
    )
    parser.add_argument("--derivatives-zip", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    manifest = extract_development_registration_transforms(
        args.derivatives_zip,
        args.out,
    )
    print(
        json.dumps(
            {
                "case_count": manifest["case_count"],
                "files_per_case": manifest["files_per_case"],
                "holdout_subjects_extracted": 0,
                "manual_or_lesion_files_extracted": 0,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

