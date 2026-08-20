#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""A união das TRÊS fases dinâmicas (arterial+venosa+tardia) recupera fígado?

docs/189 mediu venosa+pré-contraste (não são as fases de produção) e validou o
MECANISMO contra referência humana (CHAOS): quando a união acrescenta, 82% do
acréscimo é fígado real. Este script mede a MAGNITUDE com a combinação que de
fato seria usada -- arterial, venosa e tardia, já harmonizadas na mesma grade
(verificado: mesma size/spacing em produção, união é OR voxel a voxel direto).

docs/165 mediu isso num único exame: arterial 122 mL, venosa 486, tardia 607,
união das três 650 mL. Este script escala para uma amostra do LLD.

Gate desta medição, pré-especificado: a união das três precisa recuperar
substancialmente mais que a venosa sozinha para justificar a Trilha B de
docs/188/189. Sem isso, a solução proposta não se sustenta.

Uso:
    .venv-win/Scripts/python.exe tools/measure_three_phase_union_gain.py --limit 20
"""
from __future__ import annotations

import argparse
import json
import random
import sys
import warnings
from pathlib import Path

import numpy as np
import SimpleITK as sitk
from scipy import ndimage

warnings.filterwarnings("ignore")
REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from dtwin.benchmark.lld_mmri_v23_preparation import (
    isolated_total_mr_liver_segmenter,
)

ENTRADAS = REPO / "casos/qualification/lld_mmri_v23/prepared/external_inputs_v1/inputs"
VENOSA = REPO / "casos/qualification/lld_mmri_v23/prepared/external_segmentation_audit335_fullres_v1"
SAIDA = REPO / "experiments/three_phase_union_v1"
FAIXA_ADULTO_ML = (900.0, 2400.0)


def descreve(mask: np.ndarray, spacing) -> dict:
    voxels = int(mask.sum())
    volume = voxels * float(np.prod(spacing)) / 1000.0
    rotulos, n = ndimage.label(mask)
    fracao = float(np.bincount(rotulos.ravel())[1:].max() / voxels) if voxels else 0.0
    return {"volume_ml": round(volume, 1), "componentes": int(n),
            "fracao_componente_principal": round(fracao, 4)}


def segmentar(fonte: Path, destino: Path) -> np.ndarray | None:
    if not destino.is_file():
        try:
            isolated_total_mr_liver_segmenter(
                fonte, destino, device="gpu", fast=False, timeout_seconds=600
            )
        except Exception as exc:
            print(f"    falhou ({fonte.name}): {exc}", flush=True)
            return None
    return sitk.GetArrayFromImage(sitk.ReadImage(str(destino))) > 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=20)
    args = parser.parse_args()
    SAIDA.mkdir(parents=True, exist_ok=True)
    (SAIDA / "masks").mkdir(exist_ok=True)
    destino_json = SAIDA / "results.json"
    feitos = json.loads(destino_json.read_text("utf-8")) if destino_json.is_file() else {}

    casos = sorted(d.name for d in ENTRADAS.iterdir() if d.is_dir())
    random.seed(20260806)
    casos = random.sample(casos, min(args.limit, len(casos)))

    print("=" * 78)
    print("UNIAO DAS TRES FASES DINAMICAS (arterial+venosa+tardia) -- magnitude real")
    print("=" * 78)
    print(f"casos: {len(casos)}\n")

    for i, case_id in enumerate(casos, 1):
        if case_id in feitos:
            continue
        venosa_mask_path = VENOSA / case_id / "liver_mask_venous.nii.gz"
        arterial_src = ENTRADAS / case_id / "t1_arterial.nii.gz"
        delayed_src = ENTRADAS / case_id / "t1_delayed.nii.gz"
        venosa_src = ENTRADAS / case_id / "t1_venous.nii.gz"
        if not all(p.is_file() for p in (venosa_mask_path, arterial_src, delayed_src, venosa_src)):
            continue
        print(f"[{i}/{len(casos)}] {case_id}", flush=True)

        img_ref = sitk.ReadImage(str(venosa_src))
        venosa = sitk.GetArrayFromImage(sitk.ReadImage(str(venosa_mask_path))) > 0
        arterial = segmentar(arterial_src, SAIDA / "masks" / f"{case_id}_arterial.nii.gz")
        tardia = segmentar(delayed_src, SAIDA / "masks" / f"{case_id}_delayed.nii.gz")
        if arterial is None or tardia is None:
            feitos[case_id] = {"erro": "falha em segmentar arterial ou tardia"}
            destino_json.write_text(json.dumps(feitos, indent=1), encoding="utf-8")
            continue
        if not (venosa.shape == arterial.shape == tardia.shape):
            feitos[case_id] = {"erro": "grades divergentes"}
            destino_json.write_text(json.dumps(feitos, indent=1), encoding="utf-8")
            continue

        uniao = venosa | arterial | tardia
        sp = img_ref.GetSpacing()
        registro = {
            "venosa": descreve(venosa, sp),
            "arterial": descreve(arterial, sp),
            "tardia": descreve(tardia, sp),
            "uniao_tres_fases": descreve(uniao, sp),
        }
        vv = registro["venosa"]["volume_ml"]
        uv = registro["uniao_tres_fases"]["volume_ml"]
        registro["razao_uniao_sobre_venosa"] = round(uv / vv, 3) if vv else None
        feitos[case_id] = registro
        destino_json.write_text(json.dumps(feitos, indent=1), encoding="utf-8")
        print(f"    art {registro['arterial']['volume_ml']:>6.0f}  ven {vv:>6.0f}  "
              f"tard {registro['tardia']['volume_ml']:>6.0f}  ->  uniao {uv:>6.0f} mL "
              f"({registro['razao_uniao_sobre_venosa']}x)", flush=True)

    validos = [v for v in feitos.values() if "erro" not in v]
    if not validos:
        print("\nCONCLUSAO: nenhum caso valido.")
        return 1

    ven = np.array([v["venosa"]["volume_ml"] for v in validos])
    uni = np.array([v["uniao_tres_fases"]["volume_ml"] for v in validos])
    razao = uni / ven
    baixo, alto = FAIXA_ADULTO_ML
    comp_ven = np.array([v["venosa"]["componentes"] for v in validos])
    comp_uni = np.array([v["uniao_tres_fases"]["componentes"] for v in validos])

    print()
    print("=" * 78)
    print("CONCLUSAO")
    print("=" * 78)
    print(f"n={len(validos)}  (erros={len(feitos)-len(validos)})")
    print(f"volume mediano   venosa {np.median(ven):.0f} mL   uniao {np.median(uni):.0f} mL")
    print(f"razao uniao/venosa   mediana {np.median(razao):.2f}x   min {razao.min():.2f}   max {razao.max():.2f}")
    print(f"dentro da faixa adulta ({baixo:.0f}-{alto:.0f} mL):")
    print(f"    venosa  {int(((ven>=baixo)&(ven<=alto)).sum())}/{len(validos)}")
    print(f"    uniao   {int(((uni>=baixo)&(uni<=alto)).sum())}/{len(validos)}")
    print(f"componentes mediana   venosa {np.median(comp_ven):.0f}   uniao {np.median(comp_uni):.0f}")
    ganho_pct = 100.0 * (np.median(razao) - 1.0)
    print()
    if np.median(razao) >= 1.15:
        print(f"GATE PASSA: a uniao das tres fases recupera {ganho_pct:.0f}% de volume a mais "
              "que a venosa sozinha, na mediana. Justifica prosseguir com a Trilha B "
              "(docs/188/189).")
    else:
        print(f"GATE FALHA: a uniao das tres fases recupera apenas {ganho_pct:.0f}% a mais "
              "que a venosa. Ganho insuficiente para justificar o custo/complexidade "
              "da Trilha B nesta forma.")

    payload = {"schema": "oren-three-phase-union-gain-v1", "casos": feitos,
               "research_only": True, "clinical_use_allowed": False}
    destino_json.write_text(json.dumps(payload["casos"], ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\nsalvo em {SAIDA}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
