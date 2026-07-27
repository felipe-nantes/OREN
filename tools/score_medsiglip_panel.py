#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Pontua um painel ARGOS com MedSigLIP sem emitir classificação final."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from dtwin.medsiglip_zero_shot import MedSigLIPScorer, load_medsiglip_config


def _write_json_atomic(path: Path, payload: dict) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--panel", type=Path, required=True)
    parser.add_argument(
        "--config", type=Path, default=Path("configs/medsiglip_liver_zero_shot.yaml")
    )
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--device", choices=("cpu", "cuda"), default="cpu")
    parser.add_argument(
        "--allow-download",
        action="store_true",
        help="Permite acesso ao Hugging Face somente após aceite dos termos pelo usuário.",
    )
    args = parser.parse_args(argv)
    scorer = MedSigLIPScorer(
        load_medsiglip_config(args.config),
        local_files_only=not args.allow_download,
        device=args.device,
    )
    result = scorer.score_panel(args.panel)
    _write_json_atomic(args.out, result)
    print(json.dumps({"status": "scores_only", "out": str(args.out), "final_decision": None}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
