"""Extract or verify frozen MedSigLIP embeddings for hybrid-v1."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from dtwin.learning.medsiglip_embeddings import (
    extract_embeddings,
    verify_embeddings,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("extract", "verify"))
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("configs/training/medsiglip_frozen_v1.yaml"),
    )
    parser.add_argument(
        "--candidates",
        type=Path,
        default=Path(
            "casos/qualification/hybrid_v1/candidate_dataset_stage_a_v1"
        ),
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path(
            "casos/qualification/hybrid_v1/medsiglip_embeddings_stage_a_v1"
        ),
    )
    parser.add_argument("--workspace-root", type=Path, default=Path.cwd())
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()
    if args.command == "extract":
        result = extract_embeddings(
            config_path=args.config,
            candidate_root=args.candidates,
            workspace_root=args.workspace_root,
            output_root=args.out,
            limit=args.limit,
        )
    else:
        result = verify_embeddings(
            candidate_root=args.candidates, output_root=args.out
        )
    print(
        json.dumps(
            {
                "status": "ok",
                "embedding_signature": result["embedding_signature"],
                "embedding_count": result["embedding_count"],
                "backend": result["backend"],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
