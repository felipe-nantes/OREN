"""CLI para renderizar o candidato multifásico OpenSwissHCC."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from dtwin.benchmark.openswisshcc_candidate import render_aligned_multiphase_candidate


def main() -> int:
    parser = argparse.ArgumentParser(description="Renderiza o painel RGB OpenSwissHCC.")
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--inputs", required=True, type=Path)
    parser.add_argument("--alignments", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--config", type=Path, default=Path("configs/medgemma_local_4b_multiphase_fast_pathology.yaml"))
    parser.add_argument("--profile", type=Path, default=Path("profiles/figado.yaml"))
    parser.add_argument("--visible-phi-confirmed", action="store_true")
    args = parser.parse_args()
    result = render_aligned_multiphase_candidate(
        case_id=args.case_id,
        input_root=args.inputs,
        alignment_root=args.alignments,
        output_root=args.out,
        config_path=args.config,
        profile_path=args.profile,
        visible_phi_confirmed=args.visible_phi_confirmed,
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

