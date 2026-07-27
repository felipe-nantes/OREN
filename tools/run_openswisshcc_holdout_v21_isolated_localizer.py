#!/usr/bin/env python3
"""Run the holdout localizer with an isolated TotalSegmentator config."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from dtwin.benchmark.openswisshcc_holdout_signals import (
    verify_holdout_v21_signal_context,
)
from dtwin.benchmark.openswisshcc_lesion_localizer import (
    TotalSegmentatorMRLesionLocalizer,
    run_localizer_scores,
)
from dtwin.benchmark.totalsegmentator_runtime import (
    configure_isolated_totalsegmentator_runtime,
)
from dtwin.benchmark.windows_spawn_guard import (
    PYARROW_GUARD_ID,
    block_optional_module_for_spawn,
)
from dtwin.core import PipelineError


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--panels", type=Path, required=True)
    parser.add_argument("--gallery", type=Path, required=True)
    parser.add_argument("--review", type=Path, required=True)
    parser.add_argument("--prepared", type=Path, required=True)
    parser.add_argument("--prepared-audit", type=Path, required=True)
    parser.add_argument("--multiphase-config", type=Path, required=True)
    parser.add_argument("--fallback-config", type=Path, required=True)
    parser.add_argument("--medsiglip-config", type=Path, required=True)
    parser.add_argument("--calibrator", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--totalseg-home", type=Path, required=True)
    parser.add_argument("--totalseg-weights", type=Path, required=True)
    args = parser.parse_args()
    try:
        context = verify_holdout_v21_signal_context(
            panel_root=args.panels,
            gallery_root=args.gallery,
            review_path=args.review,
            prepared_root=args.prepared,
            prepared_audit_path=args.prepared_audit,
            multiphase_config_path=args.multiphase_config,
            fallback_config_path=args.fallback_config,
            medsiglip_config_path=args.medsiglip_config,
            calibrator_path=args.calibrator,
            expected_case_count=44,
        )
        runtime = configure_isolated_totalsegmentator_runtime(
            home_dir=args.totalseg_home,
            weights_dir=args.totalseg_weights,
            runtime_id=f"argos_holdout_v21_{context['review_signature'][:12]}",
        )
        with block_optional_module_for_spawn("pyarrow") as guarded:
            model = TotalSegmentatorMRLesionLocalizer()
            result = run_localizer_scores(
                manifest_path=args.manifest,
                input_root=Path(args.prepared).resolve() / "inputs",
                output_root=args.out,
                case_ids=context["case_ids"],
                localizer=model,
                expected_source_case_count=44,
                max_localizer_seconds=90.0,
                selection_signature=context["review_signature"],
                runtime_guard=";".join(
                    value
                    for value in (
                        PYARROW_GUARD_ID if guarded else None,
                        runtime["runtime_guard"],
                    )
                    if value
                ),
                progress=lambda item: print(json.dumps(item, sort_keys=True), flush=True),
            )
    except PipelineError as exc:
        print(f"[ABORTADO] {exc}")
        return 1
    print(json.dumps(result, ensure_ascii=True, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
