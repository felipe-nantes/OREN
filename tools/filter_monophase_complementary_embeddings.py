from __future__ import annotations

import argparse
import json
from pathlib import Path

from dtwin.learning.filter_embedding_dataset import filter_candidate_embedding_dataset


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidates", type=Path, required=True)
    parser.add_argument("--embeddings", type=Path, required=True)
    parser.add_argument("--sequence-role", required=True)
    parser.add_argument("--out-candidates", type=Path, required=True)
    parser.add_argument("--out-embeddings", type=Path, required=True)
    args = parser.parse_args()
    result = filter_candidate_embedding_dataset(
        candidate_root=args.candidates,
        embedding_root=args.embeddings,
        sequence_role=args.sequence_role,
        output_candidate_root=args.out_candidates,
        output_embedding_root=args.out_embeddings,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
