from __future__ import annotations

import argparse
import json
from pathlib import Path

from dtwin.learning.openswiss_monophase_atlas_candidates import (
    build_openswiss_monophase_atlas_candidates,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--atlas-root", type=Path, required=True)
    parser.add_argument("--workspace-root", type=Path, default=Path.cwd())
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    result = build_openswiss_monophase_atlas_candidates(
        atlas_root=args.atlas_root,
        workspace_root=args.workspace_root,
        output_root=args.out,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
