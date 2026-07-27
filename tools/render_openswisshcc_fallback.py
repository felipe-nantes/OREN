"""CLI do fallback venoso OpenSwissHCC."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from dtwin.benchmark.openswisshcc_fallback import (
    ALLOWED_FALLBACK_REASONS,
    FALLBACK_REASON,
    render_venous_fallback_candidate,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Renderiza fallback venoso research-only.")
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--inputs", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("configs/medgemma_local_4b_venous_fallback_pathology.yaml"),
    )
    parser.add_argument("--profile", type=Path, default=Path("profiles/figado.yaml"))
    parser.add_argument(
        "--fallback-reason",
        choices=sorted(ALLOWED_FALLBACK_REASONS),
        default=FALLBACK_REASON,
    )
    args = parser.parse_args()
    result = render_venous_fallback_candidate(
        case_id=args.case_id,
        input_root=args.inputs,
        output_root=args.out,
        config_path=args.config,
        profile_path=args.profile,
        fallback_reason=args.fallback_reason,
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
