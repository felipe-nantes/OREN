#!/usr/bin/env python3
"""Launcher mínimo copiado para %TEMP% antes de iniciar o nnU-Net no Windows."""
import sys

if __name__ == "__main__":
    if len(sys.argv) != 7:
        print("PREP_FAIL: argumentos inválidos")
        raise SystemExit(64)
    repo, profile, dicom_dir, case_dir, device, fast_arg = sys.argv[1:7]
    fast = fast_arg.strip().lower() in {"1", "true", "fast", "yes"}
    sys.path.insert(0, repo)
    try:
        from dtwin.core import PipelineError
        from dtwin.engine import Engine
    except Exception as exc:
        print(f"PREP_FAIL: import do motor falhou: {type(exc).__name__}: {exc}")
        raise SystemExit(65)
    try:
        Engine(profile).prepare(
            dicom_dir, case_dir, policy="anonymize", device=device, fast=fast
        )
        print("PREP_OK")
    except PipelineError as exc:
        print(f"PREP_FAIL: {exc}")
        raise SystemExit(2)
    except Exception as exc:
        print(f"PREP_FAIL: {type(exc).__name__}: {exc}")
        raise SystemExit(3)
