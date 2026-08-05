from __future__ import annotations

import argparse
import json
from pathlib import Path

from dtwin.learning.localized_candidate_supervision import (
    build_localized_candidate_geometry,
    build_localized_image_dataset,
    build_protected_localized_targets,
    select_label_blind_candidates,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build label-blind localized candidates and protected development targets."
    )
    parser.add_argument(
        "--proposal-root",
        type=Path,
        default=Path("casos/qualification/openswisshcc_v1/calibration/dev_v22_enhancement_localizer_full87_v1"),
    )
    parser.add_argument(
        "--candidate-root",
        type=Path,
        default=Path("casos/qualification/hybrid_v1/localized_candidate_geometry_v1"),
    )
    parser.add_argument(
        "--authorized-mask-root",
        type=Path,
        default=Path("casos/qualification/openswisshcc_v1/authorized_ground_truth_v16/venous_masks_v1"),
    )
    parser.add_argument(
        "--audit-protocol",
        type=Path,
        default=Path("casos/qualification/openswisshcc_v1/authorized_ground_truth_v16/audit_protocol_v1.json"),
    )
    parser.add_argument(
        "--target-root",
        type=Path,
        default=Path("casos/qualification/hybrid_v1/localized_candidate_targets_v1"),
    )
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument("--crop-mm", type=float, default=64.0)
    parser.add_argument("--visible-slices", type=int, default=7)
    parser.add_argument("--targets-only", action="store_true")
    parser.add_argument("--select-top-per-case", type=int)
    parser.add_argument("--selected-root", type=Path)
    parser.add_argument("--image-root", type=Path)
    parser.add_argument("--workspace-root", type=Path, default=Path.cwd())
    parser.add_argument(
        "--inputs-root",
        type=Path,
        default=Path("casos/qualification/openswisshcc_v1/prepared/development_v1/inputs"),
    )
    parser.add_argument(
        "--alignment-root",
        type=Path,
        default=Path("casos/qualification/openswisshcc_v1/prepared/development_alignment_v1"),
    )
    args = parser.parse_args()

    if not args.targets_only:
        geometry = build_localized_candidate_geometry(
            proposal_root=args.proposal_root,
            output_root=args.candidate_root,
            top_k_components=args.top_k,
            crop_mm=args.crop_mm,
            visible_slices=args.visible_slices,
        )
        print(json.dumps(geometry, ensure_ascii=False, indent=2))
    active_root = args.candidate_root
    if args.select_top_per_case:
        if args.selected_root is None:
            parser.error("--selected-root is required with --select-top-per-case")
        selected = select_label_blind_candidates(
            source_root=args.candidate_root,
            output_root=args.selected_root,
            maximum_per_case=args.select_top_per_case,
        )
        print(json.dumps(selected, ensure_ascii=False, indent=2))
        active_root = args.selected_root
    if args.image_root is not None:
        images = build_localized_image_dataset(
            geometry_root=active_root,
            proposal_root=args.proposal_root,
            inputs_root=args.inputs_root,
            alignment_root=args.alignment_root,
            workspace_root=args.workspace_root,
            output_root=args.image_root,
        )
        print(json.dumps(images, ensure_ascii=False, indent=2))
    targets = build_protected_localized_targets(
        candidate_root=active_root,
        authorized_mask_root=args.authorized_mask_root,
        audit_protocol_path=args.audit_protocol,
        output_root=args.target_root,
    )
    print(json.dumps(targets, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
