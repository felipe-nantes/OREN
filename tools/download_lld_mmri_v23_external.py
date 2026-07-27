#!/usr/bin/env python3
"""Download only selected LLD-MMRI images; never lesion labels or masks."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from huggingface_hub import hf_hub_download, list_repo_files

from dtwin.benchmark.lld_mmri_v23_download import (
    download_lld_mmri_v23_images,
    validate_lld_mmri_v23_download,
)
from dtwin.benchmark.lld_mmri_v23_external import REPO_ID, REPO_REVISION
from dtwin.core import PipelineError


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol-root", type=Path, required=True)
    parser.add_argument("--destination", type=Path, required=True)
    parser.add_argument("--accept-license", action="store_true")
    parser.add_argument("--verify-only", action="store_true")
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    try:
        if args.verify_only:
            result = validate_lld_mmri_v23_download(
                protocol_root=args.protocol_root,
                destination=args.destination,
            )
        else:
            repo_files = list_repo_files(REPO_ID, repo_type="dataset", revision=REPO_REVISION)
            result = download_lld_mmri_v23_images(
                protocol_root=args.protocol_root,
                destination=args.destination,
                accept_license=args.accept_license,
                repo_files=repo_files,
                downloader=hf_hub_download,
                workers=args.workers,
                progress=lambda index, total, case_id: print(
                    json.dumps(
                        {"downloaded_cases": index, "total_cases": total, "case_id": case_id},
                        sort_keys=True,
                    ),
                    flush=True,
                ),
            )
    except (PipelineError, OSError) as exc:
        print(f"[ABORTADO] {exc}")
        return 1
    print(json.dumps({
        "status": result["status"],
        "case_count": result["case_count"],
        "image_count": result["image_count"],
        "manifest_signature": result["manifest_signature"],
        "verified_only": args.verify_only,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
