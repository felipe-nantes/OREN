#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Bootstrap compatível do gateway MedGemma.

Mantém ``python tools/medgemma_server.py`` (usado por ``run_win.ps1``) e a
importação ``tools.medgemma_server`` apontando para a implementação v14.
"""
from __future__ import annotations

import sys
from pathlib import Path


_REPOSITORY_ROOT = Path(__file__).resolve().parent.parent
if str(_REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPOSITORY_ROOT))

import tools.medgemma_server_v14 as _impl
from tools.medgemma_server_v14 import *  # noqa: F401,F403


_build_volume_messages = _impl._build_volume_messages
_build_runtime = _impl._build_runtime


def create_app(config_path: Path):
    """Preserva monkeypatches no módulo público e delega ao servidor v14."""

    original_loader = _impl.load_screening_config
    _impl.load_screening_config = load_screening_config
    try:
        return _impl.create_app(config_path)
    finally:
        _impl.load_screening_config = original_loader


def main(argv=None) -> int:
    return _impl.main(argv)


if __name__ == "__main__":
    raise SystemExit(main())

