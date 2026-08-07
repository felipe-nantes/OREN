#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Worker isolado (um tiro, killable) para o modelo dedicado de figado.

Chama liver_segments_mr_union_segmenter SEM MODIFICA-LO -- a funcao ja existe
em dtwin/benchmark/lld_mmri_v23_preparation.py:338 e continua congelada; este
arquivo so' a executa num subprocesso proprio, para que um travamento do
modelo nao contamine o processo que mede.

Faz parte do teste isolado descrito em
tools/measure_liver_segments_mr_vs_chaos_reference.py. Nao toca em producao.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from dtwin.benchmark.lld_mmri_v23_preparation import (  # noqa: E402
    liver_segments_mr_union_segmenter,
)
from dtwin.benchmark.windows_spawn_guard import block_optional_module_for_spawn  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--device", default="gpu")
    args = parser.parse_args()

    with block_optional_module_for_spawn("pyarrow"):
        receipt = liver_segments_mr_union_segmenter(
            args.source, args.output, device=args.device
        )
    args.receipt.write_text(
        json.dumps(receipt, ensure_ascii=False, sort_keys=True, default=str),
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
