from __future__ import annotations

import argparse
import json
from pathlib import Path

from dtwin.learning.localized_candidate_features import build_fused_localized_embeddings


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--geometry", type=Path, default=Path("casos/qualification/hybrid_v1/localized_candidate_geometry_top8_v1"))
    parser.add_argument("--images", type=Path, default=Path("casos/qualification/hybrid_v1/localized_candidate_images_top8_v1"))
    parser.add_argument("--medsiglip", type=Path, default=Path("casos/qualification/hybrid_v1/localized_candidate_embeddings_top8_v1"))
    parser.add_argument("--inputs", type=Path, default=Path("casos/qualification/openswisshcc_v1/prepared/development_v1/inputs"))
    parser.add_argument("--alignment", type=Path, default=Path("casos/qualification/openswisshcc_v1/prepared/development_alignment_v1"))
    parser.add_argument("--out", type=Path, default=Path("casos/qualification/hybrid_v1/localized_candidate_fused_embeddings_top8_v1"))
    parser.add_argument("--dynamic-only", action="store_true")
    args = parser.parse_args()
    result = build_fused_localized_embeddings(
        geometry_root=args.geometry, image_dataset_root=args.images,
        medsiglip_root=args.medsiglip, inputs_root=args.inputs,
        alignment_root=args.alignment, output_root=args.out,
        include_visual_embedding=not args.dynamic_only,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
