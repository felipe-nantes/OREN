# -*- coding: utf-8 -*-
"""Executa UM TotalSegmentator isolado em subprocesso (RIM-01 fase F).

Mesmo racional do ct01_ts_um_caso.py (CT01-F): subprocesso por caso
devolve memória ao SO; arquivo próprio porque multiprocessing spawn do
Windows reimporta o módulo main. Task parametrizada (total p/ TC dá
kidney_left/right; total_mr p/ RM idem) — mesmos argumentos do stage3 de
produção (device=gpu, fast=False).

Uso: python rim_f_ts_um_caso.py <volume.nii.gz> <dir_saida> <task>
"""
from __future__ import annotations

import sys


def main() -> None:
    volume, saida, task = sys.argv[1], sys.argv[2], sys.argv[3]
    from pathlib import Path

    from totalsegmentator.python_api import totalsegmentator

    marcador = Path(saida) / "kidney_left.nii.gz"
    try:
        totalsegmentator(
            input=volume, output=saida, task=task,
            device="gpu", fast=False, quiet=True,
        )
        return
    except BaseException as exc:  # inclui SystemExit de workers mortos
        if marcador.is_file():
            print(f"aviso: pos-processamento falhou ({type(exc).__name__}); "
                  "artefato presente, prosseguindo", file=sys.stderr)
            return
        print(f"aviso: tentativa padrao falhou ({type(exc).__name__}); "
              "refazendo em modo economico (force_split, 1 thread)",
              file=sys.stderr)
    totalsegmentator(
        input=volume, output=saida, task=task,
        device="gpu", fast=False, quiet=True,
        force_split=True, nr_thr_resamp=1, nr_thr_saving=1,
    )
    (Path(saida) / ".ts_economico").write_text(
        "fallback force_split apos falha de memoria", encoding="utf-8")


if __name__ == "__main__":
    main()
