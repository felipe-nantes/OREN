#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""FASE 2.2 do plano de fragmentacao: testa fechamento morfologico como
segunda tentativa SOMENTE para o caso em que a guarda de isolamento bloqueou
mesmo depois da uniao de 3 fases (Fase 1: anon-lld-7ef3b5abe1ee4cd8,
fracao=0,5025 apos incluir a tardia).

Gate pre-especificado (escrito antes de rodar): so vale a pena implementar em
producao se ALGUM raio de fechamento (a) levar fracao_componente_principal
para >=0.90 E (b) inflar o volume em menos de 3%.

Uso:
    .venv-win/Scripts/python.exe tools/test_morphological_closing_gate.py
"""
from __future__ import annotations

import sys
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")
REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

import shutil

import numpy as np
from scipy import ndimage

from dtwin.core import array_from, read_image
from dtwin.learning.multiphase_ingest import ARTERIAL, DELAYED
from dtwin.stages import _isolar_orgao_para_visualizacao, _refine_mask
from webapp.server import _build_union_liver_mask

CASO = REPO / "casos/qualification/lld_mmri_v23/analise_10_melhores_10_piores_v1/10_piores/anon-lld-7ef3b5abe1ee4cd8"
ENTRADAS = REPO / "casos/qualification/lld_mmri_v23/prepared/external_inputs_v1/inputs/anon-lld-7ef3b5abe1ee4cd8"
WORK = REPO / "experiments/best_worst_gallery_v1/_work/10_piores/anon-lld-7ef3b5abe1ee4cd8"

GATE_FRACAO_MINIMA = 0.90
GATE_INFLACAO_MAXIMA = 0.03


def main() -> int:
    WORK.mkdir(parents=True, exist_ok=True)
    venosa_src = CASO / "mask_organ_venosa.nii.gz"
    shutil.copyfile(venosa_src, WORK / "mask_organ.nii.gz")
    uniao_path = WORK / "mask_organ_union.nii.gz"
    if not uniao_path.is_file():
        _build_union_liver_mask(WORK, {ARTERIAL: ENTRADAS / "t1_arterial.nii.gz",
                                        DELAYED: ENTRADAS / "t1_delayed.nii.gz"})

    imagem = read_image(uniao_path)
    bruta = array_from(imagem) > 0
    refinada = _refine_mask(bruta, True, 2, 300).astype(bool)
    spacing = np.array(imagem.GetSpacing())
    voxel_ml = float(np.prod(spacing)) / 1000.0

    _, base_diag = _isolar_orgao_para_visualizacao(refinada.copy())
    volume_base_ml = float(refinada.sum()) * voxel_ml
    print("=" * 78)
    print(f"BASE (sem fechamento): fracao={base_diag['fracao_componente_principal']:.4f}  "
          f"componentes={base_diag['componentes']}  volume={volume_base_ml:.1f} mL")
    print("=" * 78)
    print(f"gate: fracao >= {GATE_FRACAO_MINIMA}  E  inflacao de volume < {100*GATE_INFLACAO_MAXIMA:.0f}%\n")

    passou_algum = False
    for raio_mm in (1.0, 2.0, 3.0, 4.0, 5.0):
        raio_vox = np.maximum(1, np.round(raio_mm / spacing[::-1])).astype(int)  # spacing eh (x,y,z); mascara e' (z,y,x)
        estrutura = ndimage.generate_binary_structure(3, 1)
        iteracoes = int(max(1, round(raio_mm / float(np.mean(spacing)))))
        fechada = ndimage.binary_closing(refinada, structure=estrutura, iterations=iteracoes)
        volume_fechado_ml = float(fechada.sum()) * voxel_ml
        inflacao = (volume_fechado_ml - volume_base_ml) / volume_base_ml
        _, diag = _isolar_orgao_para_visualizacao(fechada.copy())
        passou = diag["fracao_componente_principal"] >= GATE_FRACAO_MINIMA and inflacao < GATE_INFLACAO_MAXIMA
        passou_algum = passou_algum or passou
        print(f"raio~{raio_mm:.0f}mm (iter={iteracoes}): fracao={diag['fracao_componente_principal']:.4f}  "
              f"componentes={diag['componentes']}  volume={volume_fechado_ml:.1f} mL  "
              f"inflacao={100*inflacao:.1f}%  {'PASSOU' if passou else 'reprovado'}")

    print()
    if passou_algum:
        print("GATE PASSA em algum raio -- considerar implementar em producao.")
    else:
        print("GATE FALHA em todos os raios testados -- fechamento morfologico nao resolve "
              "este caso com seguranca. Documentar como negativo: a fragmentacao aqui e' "
              "sintoma de segmentacao ruim (fracao 0,50, volume bem abaixo do normal), nao "
              "algo que pos-processamento deva esconder.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
