from __future__ import annotations

import argparse
import json
from pathlib import Path

from dtwin.learning.filter_embedding_dataset import rebind_embedding_dataset


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-candidates", type=Path, required=True)
    parser.add_argument("--source-embeddings", type=Path, required=True)
    parser.add_argument("--target-candidates", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    result = rebind_embedding_dataset(
        source_candidate_root=args.source_candidates,
        source_embedding_root=args.source_embeddings,
        target_candidate_root=args.target_candidates,
        output_embedding_root=args.out,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
