#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Gera um painel spotlight experimental a partir de artefatos já anonimizados."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from dtwin.medgemma_spotlight import render_uniform_spotlight_panel


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Renderiza painel hepático spotlight sem máscara de lesão."
    )
    parser.add_argument("--volume", type=Path, required=True)
    parser.add_argument("--liver-mask", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--outside-fraction", type=float, default=0.15)
    args = parser.parse_args(argv)
    result = render_uniform_spotlight_panel(
        volume_path=args.volume,
        liver_mask_path=args.liver_mask,
        output_path=args.out,
        outside_fraction=args.outside_fraction,
    )
    print(
        json.dumps(
            {
                "status": "complete",
                "research_only": True,
                "lesion_mask_used": False,
                "panel_sha256": result.panel_sha256,
                "axial_indices": list(result.axial_indices),
                "outside_mask_intensity_fraction": result.outside_mask_intensity_fraction,
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
