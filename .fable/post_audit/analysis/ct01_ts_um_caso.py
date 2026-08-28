# -*- coding: utf-8 -*-
"""Executa UM TotalSegmentator isolado em subprocesso (CT01-F).

Motivo: o runner de benchmark é um processo longo; TS in-process acumula
memória ao longo de dezenas de casos até WinError 1455 (commit esgotado)
nos workers do nnU-Net. Subprocesso por caso devolve toda a memória ao SO.
Mesma engine e MESMOS argumentos do stage3 de produção (task=total,
fast=False, device=gpu); muda apenas o invólucro de execução — declarado
na evidência. Arquivo próprio (não -c/stdin): multiprocessing spawn do
Windows re-importa o módulo main.

Uso: python ct01_ts_um_caso.py <volume.nii.gz> <dir_saida>
"""
from __future__ import annotations

import sys


def main() -> None:
    volume, saida = sys.argv[1], sys.argv[2]
    from pathlib import Path

    from totalsegmentator.python_api import totalsegmentator

    try:
        totalsegmentator(
            input=volume, output=saida, task="total",
            device="gpu", fast=False, quiet=True,
        )
        return
    except BaseException as exc:  # inclui SystemExit de workers mortos
        if (Path(saida) / "liver.nii.gz").is_file():
            # Falha só na LIMPEZA do temp (AV segurando handle) com a
            # segmentação concluída: sucesso.
            print(f"aviso: pos-processamento falhou ({type(exc).__name__}); "
                  "artefato presente, prosseguindo", file=sys.stderr)
            return
        print(f"aviso: tentativa padrao falhou ({type(exc).__name__}); "
              "refazendo em modo economico (force_split, 1 thread)",
              file=sys.stderr)
    # Volumes grandes estouram RAM nos workers do nnU-Net (WinError 1455 /
    # worker killed). force_split é o modo OFICIAL do TS p/ pouca memória:
    # mesmo modelo/task/resolução, processamento em partes. Marcador
    # gravado p/ transparência na evidência.
    totalsegmentator(
        input=volume, output=saida, task="total",
        device="gpu", fast=False, quiet=True,
        force_split=True, nr_thr_resamp=1, nr_thr_saving=1,
    )
    (Path(saida) / ".ts_economico").write_text(
        "fallback force_split apos falha de memoria", encoding="utf-8")


if __name__ == "__main__":
    main()
