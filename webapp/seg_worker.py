#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Launcher isolado da segmentação (fase 1: ingestão + des-identificação + órgão).

Por que existe: o TotalSegmentator (nnU-Net) gera processos de background via
multiprocessing 'spawn'. No Windows, cada filho re-importa o módulo __main__ e
varre o seu diretório (sys.path[0]). Se esse diretório for a raiz do repositório
sob OneDrive/NTFS transacional, a varredura falha com WinError 6714 e os workers
morrem. Solução: este launcher é executado a partir de um diretório TEMPORÁRIO
(fora do OneDrive) e importa o pacote `dtwin` SOMENTE no processo principal
(dentro do guard __main__). Assim os filhos re-importam um __main__ mínimo e nunca
tocam o repositório.

Uso: python seg_worker.py <repo> <profile_abs> <dicom_dir> <case_dir> <device> <fast>
  <fast>: "1"/"true"/"fast" para o modo rápido (3mm, benchmark); qualquer outro
          valor para full-res (~1.5mm, mais fiel — usado no exame individual).
Imprime 'PREP_OK' e sai 0 em sucesso; 'PREP_FAIL: <motivo>' e sai !=0 em falha.
"""
import sys

if __name__ == "__main__":
    if len(sys.argv) != 7:
        print("PREP_FAIL: argumentos inválidos")
        sys.exit(64)
    repo, profile, dicom_dir, case_dir, device, fast_arg = sys.argv[1:7]
    fast = fast_arg.strip().lower() in ("1", "true", "fast", "yes")
    sys.path.insert(0, repo)  # visível só no processo principal
    try:
        from dtwin.engine import Engine
        from dtwin.core import PipelineError
    except Exception as exc:  # noqa: BLE001
        print(f"PREP_FAIL: import do motor falhou: {type(exc).__name__}: {exc}")
        sys.exit(65)
    try:
        Engine(profile).prepare(dicom_dir, case_dir, policy="anonymize", device=device, fast=fast)
        print("PREP_OK")
    except PipelineError as exc:
        print(f"PREP_FAIL: {exc}")
        sys.exit(2)
    except Exception as exc:  # noqa: BLE001
        print(f"PREP_FAIL: {type(exc).__name__}: {exc}")
        sys.exit(3)
