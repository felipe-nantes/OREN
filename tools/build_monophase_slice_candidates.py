from __future__ import annotations

import argparse
import json
from pathlib import Path

from dtwin.learning.monophase_slice_candidates import build_monophase_slice_candidates


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--inputs-root", type=Path, required=True)
    parser.add_argument("--protocol", type=Path, default=Path("configs/training/hybrid_v1_protocol.lock.json"))
    parser.add_argument("--splits", type=Path, default=Path("configs/training/hybrid_v1_nested_splits.json"))
    parser.add_argument("--workspace-root", type=Path, default=Path.cwd())
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--limit-cases", type=int)
    parser.add_argument("--dataset-id", default="lld_mmri")
    parser.add_argument("--manifest-only-universe", action="store_true")
    args = parser.parse_args()
    result = build_monophase_slice_candidates(
        input_manifest_path=args.manifest,
        input_files_root=args.inputs_root,
        protocol_path=args.protocol,
        splits_path=args.splits,
        workspace_root=args.workspace_root,
        output_root=args.out,
        limit_cases=args.limit_cases,
        dataset_id=args.dataset_id,
        manifest_only_universe=args.manifest_only_universe,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
