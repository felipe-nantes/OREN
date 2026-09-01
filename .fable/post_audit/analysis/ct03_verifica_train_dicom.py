# -*- coding: utf-8 -*-
"""Verifica a integridade dos DICOMs de treino no D: (janela de corrupção).

Por paciente em TCIA_{HCC,CRLM}_TRAIN: tenta ler a série com SimpleITK.
Falha de leitura => diretório do paciente é APAGADO (o downloader
resumível re-baixa na próxima execução). CPU-only; não toca a GPU nem o
subtree em quarentena.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import SimpleITK as sitk

RAIZ_D = Path(r"C:\datasets_ct")  # fontes de treino em NTFS desde 2026-08-28


def main() -> None:
    ok = ruim = 0
    for pasta in ("TCIA_HCC_TRAIN", "TCIA_CRLM_TRAIN"):
        base = RAIZ_D / pasta
        if not base.is_dir():
            continue
        for pac in sorted(p for p in base.iterdir() if p.is_dir()):
            dcm = sorted(pac.rglob("*.dcm"))
            if not dcm:
                shutil.rmtree(pac, ignore_errors=True)
                ruim += 1
                print(json.dumps({"paciente": pac.name, "status": "vazio_apagado"}),
                      flush=True)
                continue
            try:
                reader = sitk.ImageSeriesReader()
                arquivos = reader.GetGDCMSeriesFileNames(str(dcm[0].parent))
                if not arquivos:
                    raise RuntimeError("serie vazia")
                reader.SetFileNames(arquivos)
                img = reader.Execute()
                if img.GetSize()[2] < 5:
                    raise RuntimeError("serie curta demais")
                ok += 1
            except Exception as exc:
                shutil.rmtree(pac, ignore_errors=True)
                ruim += 1
                print(json.dumps({"paciente": pac.name,
                                  "status": "corrompido_apagado",
                                  "erro": str(exc)[:120]}), flush=True)
    print(f"VERIFICACAO_TRAIN_COMPLETA ok={ok} apagados={ruim}", flush=True)


if __name__ == "__main__":
    main()
