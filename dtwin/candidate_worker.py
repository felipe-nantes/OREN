"""Minimal subprocess entrypoint for post-inference candidate localization."""
from __future__ import annotations

import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 4:
        print("CANDIDATE_FAIL: argumentos inválidos")
        return 64
    repo, case_dir, device, request_path = args
    sys.path.insert(0, repo)
    try:
        from dtwin.candidate_region import generate_candidate_region
        generate_candidate_region(
            Path(case_dir), device=device, request_path=Path(request_path)
        )
        print("CANDIDATE_OK")
        return 0
    except Exception as exc:  # noqa: BLE001 - process boundary
        print(f"CANDIDATE_FAIL: {type(exc).__name__}: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

