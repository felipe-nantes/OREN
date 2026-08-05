from __future__ import annotations

import argparse
import json
from pathlib import Path

from dtwin.learning.monophase_complementary_candidates import build_complementary_candidates


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--inputs-root", type=Path, required=True)
    parser.add_argument("--workspace-root", type=Path, default=Path.cwd())
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--limit-cases", type=int)
    parser.add_argument("--allow-rigid-fallback", action="store_true")
    parser.add_argument("--dataset-id", default="openswisshcc_development")
    args = parser.parse_args()
    result = build_complementary_candidates(
        input_manifest_path=args.manifest,
        input_files_root=args.inputs_root,
        workspace_root=args.workspace_root,
        output_root=args.out,
        limit_cases=args.limit_cases,
        allow_rigid_fallback=args.allow_rigid_fallback,
        dataset_id=args.dataset_id,
        progress_callback=lambda event: print(
            json.dumps(event, ensure_ascii=False, sort_keys=True), flush=True
        ),
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
