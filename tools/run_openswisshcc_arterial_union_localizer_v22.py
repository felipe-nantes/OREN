#!/usr/bin/env python3
"""Run a blind registered-arterial union localizer pilot for OpenSwissHCC."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from dtwin.benchmark.openswisshcc_lesion_localizer import (
    TotalSegmentatorMRLesionLocalizer,
)
from dtwin.benchmark.openswisshcc_multiphase_localizer import (
    run_arterial_union_localizer,
)
from dtwin.benchmark.totalsegmentator_runtime import (
    configure_isolated_totalsegmentator_runtime,
)
from dtwin.benchmark.windows_spawn_guard import (
    PYARROW_GUARD_ID,
    block_optional_module_for_spawn,
)
from dtwin.core import PipelineError


def _progress(item: dict) -> None:
    print(
        f"[v22-localizador] {item['sequence']:02d}/{item['case_count']}: "
        f"{item['case_id']} | arterial={item['additional_arterial_seconds']:.1f}s | "
        f"combinado={item['combined_seconds']:.1f}s | "
        f"novos_voxels={item['new_arterial_voxels']}",
        file=sys.stderr,
        flush=True,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--inputs-root", type=Path, required=True)
    parser.add_argument("--alignment-root", type=Path, required=True)
    parser.add_argument("--selection-manifest", type=Path, required=True)
    parser.add_argument("--venous-localizer-root", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--case-id", action="append", required=True)
    parser.add_argument("--max-combined-seconds", type=float, default=150.0)
    parser.add_argument("--totalseg-home", type=Path, required=True)
    parser.add_argument("--totalseg-weights", type=Path, required=True)
    args = parser.parse_args()
    try:
        runtime = configure_isolated_totalsegmentator_runtime(
            home_dir=args.totalseg_home,
            weights_dir=args.totalseg_weights,
            runtime_id="argos_openswiss_v22_arterial_union",
        )
        with block_optional_module_for_spawn("pyarrow") as guarded:
            result = run_arterial_union_localizer(
                input_manifest_path=args.manifest,
                input_root=args.inputs_root,
                alignment_root=args.alignment_root,
                selection_manifest_path=args.selection_manifest,
                venous_localizer_root=args.venous_localizer_root,
                output_root=args.out,
                case_ids=args.case_id,
                localizer=TotalSegmentatorMRLesionLocalizer(),
                max_combined_seconds=args.max_combined_seconds,
                runtime_guard=";".join(
                    value
                    for value in (
                        PYARROW_GUARD_ID if guarded else None,
                        runtime["runtime_guard"],
                    )
                    if value
                ),
                progress=_progress,
            )
    except PipelineError as exc:
        print(f"[ABORTADO] {exc}")
        return 1
    print(json.dumps(result, ensure_ascii=True, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
